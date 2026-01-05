from django.http import HttpResponse
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Border, Side, Alignment
from openpyxl.utils import get_column_letter
from io import BytesIO

from gst_auth.utils import get_valid_session, safe_api_call


@api_view(['POST'])
@permission_classes([AllowAny])
def reconciliation(request):
    """
    GSTR-3B vs Books Reconciliation.
    Uses unified session from gst_auth for authentication.
    """
    session_id = request.data.get('session_id')
    reco_type = request.data.get('reco_type')
    year = request.data.get('year')
    month = request.data.get('month')
    quarter = request.data.get('quarter')
    
    if not session_id:
        return Response({'error': 'Session ID required'}, status=400)
        
    if not all([reco_type, year]):
        return Response({'error': 'Missing required fields'}, status=400)
    
    # Validate session using unified auth
    session, error = get_valid_session(session_id)
    if error:
        return Response({'error': error}, status=401)
    
    # Handle file upload
    if 'file' not in request.FILES:
        return Response({'error': 'No file uploaded'}, status=400)
    
    try:
        file = request.FILES['file']
        df = pd.read_excel(file)
        
        # Get months to process
        months = get_months(reco_type, int(year), int(month) if month else None, quarter)
        
        # Process reconciliation
        norm_df = normalize_helper_data(df, months)
        books_3b = calculate_books_3b(norm_df)
        portal_3b = fetch_portal_3b(months, session.taxpayer_token)
        comparison = compare_data(books_3b, portal_3b)
        
        return Response({
            'status': 'success',
            'message': 'Reconciliation completed',
            'data': comparison,
            'session_info': {
                'party_name': session.username, # Changed 'username' to 'party_name'
                'gstin': session.gstin,
                'reco_type': reco_type,
                'year': year,
                'month': month,
                'quarter': quarter
            }
        })
                
    except Exception as e:
        return Response({'error': f'Processing error: {str(e)}'}, status=500)


def get_months(reco_type, year, month=None, quarter=None):
    if reco_type == "MONTHLY":
        return [(year, month)]
    if reco_type == "QUARTERLY":
        q_map = {"Q1": [4,5,6], "Q2": [7,8,9], "Q3": [10,11,12], "Q4": [1,2,3]}
        return [(year if m >= 4 else year + 1, m) for m in q_map[quarter]]
    if reco_type == "FY":
        return [(year, m) for m in range(4,13)] + [(year+1, m) for m in range(1,4)]


def normalize_helper_data(df, valid_months):
    """
    Normalize the input dataframe (Books) to a standard format.
    Handles columns from the "New Template" (same as GSTR1).
    Filters data by the valid_months list [(year, month), ...].
    """
    # 1. Clean Column Names
    df.columns = df.columns.astype(str).str.strip()
    
    # 2. Date Filtering
    if "Date" in df.columns and valid_months:
        try:
            # Convert to datetime, handling errors gracefully
            df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors='coerce')
            
            # Filter rows where (year, month) matches valid_months
            mask = df["Date"].apply(lambda x: (x.year, x.month) in valid_months if pd.notnull(x) else False)
            df = df[mask].copy()
        except Exception as e:
            # Fallback or log if needed, though 'coerce' handles most
            pass

    if df.empty:
        return pd.DataFrame()
    
    # 3. Ensure Numeric Columns exist and are float
    numeric_cols = ["Taxable", "Export_Taxable", "SEZ_Taxable", "Nil_Rated", 
                    "Exempt", "Non_GST", "IGST", "CGST", "SGST", "Cess"]
    
    for col in numeric_cols:
        if col not in df.columns:
            df[col] = 0.0
        else:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            
    # Handle RCM column
    if "Is_RCM" not in df.columns:
        df["Is_RCM"] = "N"
    df["Is_RCM"] = df["Is_RCM"].fillna("N").astype(str).str.upper().str.strip()

    normalized_rows = []
    
    for _, r in df.iterrows():
        # Logic adapted from gstr1vsbook services
        
        # Calculate derived values
        igst, cgst, sgst = r["IGST"], r["CGST"], r["SGST"]
        tax = igst + cgst + sgst
        
        # Determine Category and specific Taxable Value
        # Priority: RCM > Export > SEZ > Nil/Exempt > Non-GST > Standard (B2B/B2C)
        
        sup_cat = "DOM"
        taxable_val = 0.0
        
        if r["Is_RCM"] == "Y":
            sup_cat = "RCM"
            # In RCM, the 'Taxable' column usually holds the value, or user might put it in others.
            # We'll take the sum of all taxable components to be safe, or just 'Taxable'.
            # gstr1vsbook sums everything:
            taxable_val = r["Taxable"] + r["Export_Taxable"] + r["SEZ_Taxable"] + \
                          r["Nil_Rated"] + r["Exempt"] + r["Non_GST"]
                          
        elif r["Export_Taxable"] > 0:
            sup_cat = "EXPWP" if tax > 0 else "EXPWOP"
            taxable_val = r["Export_Taxable"]
            
        elif r["SEZ_Taxable"] > 0:
            sup_cat = "SEZWP" if tax > 0 else "SEZWOP"
            taxable_val = r["SEZ_Taxable"]
            
        elif r["Nil_Rated"] > 0 or r["Exempt"] > 0:
            sup_cat = "NIL"
            taxable_val = r["Nil_Rated"] + r["Exempt"]
            
        elif r["Non_GST"] > 0:
            sup_cat = "NON_GST"
            taxable_val = r["Non_GST"]
            
        else:
            # Domestic (B2B, B2C, etc.) -> Mapped to 3.1(a)
            sup_cat = "DOM"
            taxable_val = r["Taxable"]

        normalized_rows.append({
            "SUP_CAT": sup_cat,
            "Taxable": taxable_val,
            "IGST": igst,
            "CGST": cgst,
            "SGST": sgst,
            "Is_RCM": r["Is_RCM"]
        })

    return pd.DataFrame(normalized_rows)


def calculate_books_3b(norm_df):
    """
    Aggregate normalized books data into GSTR-3B sections.
    """
    # Initialize 3B structure
    books_3b = {k: {"taxable": 0.0, "igst": 0.0, "cgst": 0.0, "sgst": 0.0, "tax": 0.0} 
                for k in ["3.1(a)", "3.1(b)", "3.1(c)", "3.1(d)", "3.1(e)"]}
    
    if norm_df.empty:
        return books_3b

    for _, r in norm_df.iterrows():
        tax = r["IGST"] + r["CGST"] + r["SGST"]
        
        # Mapping Logic
        key = None
        
        if r["SUP_CAT"] == "RCM":
            key = "3.1(d)"
        elif r["SUP_CAT"] in ("EXPWP", "EXPWOP", "SEZWP", "SEZWOP"):
            key = "3.1(b)"
        elif r["SUP_CAT"] == "NIL":
            key = "3.1(c)"
        elif r["SUP_CAT"] == "NON_GST":
            key = "3.1(e)"
        elif r["SUP_CAT"] == "DOM":
            key = "3.1(a)"
            
        if key:
            books_3b[key]["taxable"] += r["Taxable"]
            books_3b[key]["igst"] += r["IGST"]
            books_3b[key]["cgst"] += r["CGST"]
            books_3b[key]["sgst"] += r["SGST"]
            books_3b[key]["tax"] += tax
    
    return books_3b


def fetch_portal_3b(months, taxpayer_access_token):
    portal_3b = {k: {"taxable":0,"igst":0,"cgst":0,"sgst":0,"tax":0} for k in ["3.1(a)","3.1(b)","3.1(c)","3.1(d)","3.1(e)"]}
    
    for y, m in months:
        status_code, response_data = safe_api_call(
            "GET",
            f"https://api.sandbox.co.in/gst/compliance/tax-payer/gstrs/gstr-3b/{y}/{str(m).zfill(2)}",
            headers={
                "x-api-version": "1.0.0",
                "Authorization": taxpayer_access_token,
                "x-api-key": settings.SANDBOX_API_KEY
            }
        )
        
        if status_code != 200:
            continue
            
        sup = response_data.get("data", {}).get("data", {}).get("sup_details", {})
        
        portal_3b["3.1(a)"]["taxable"] += sup.get("osup_det", {}).get("txval", 0)
        portal_3b["3.1(a)"]["igst"] += sup.get("osup_det", {}).get("iamt", 0)
        portal_3b["3.1(a)"]["cgst"] += sup.get("osup_det", {}).get("camt", 0)
        portal_3b["3.1(a)"]["sgst"] += sup.get("osup_det", {}).get("samt", 0)
        portal_3b["3.1(a)"]["tax"] += sup.get("osup_det", {}).get("iamt", 0) + sup.get("osup_det", {}).get("camt", 0) + sup.get("osup_det", {}).get("samt", 0)
        
        portal_3b["3.1(b)"]["taxable"] += sup.get("osup_zero", {}).get("txval", 0)
        portal_3b["3.1(b)"]["igst"] += sup.get("osup_zero", {}).get("iamt", 0)
        portal_3b["3.1(b)"]["cgst"] += sup.get("osup_zero", {}).get("camt", 0)
        portal_3b["3.1(b)"]["sgst"] += sup.get("osup_zero", {}).get("samt", 0)
        portal_3b["3.1(b)"]["tax"] += sup.get("osup_zero", {}).get("iamt", 0) + sup.get("osup_zero", {}).get("camt", 0) + sup.get("osup_zero", {}).get("samt", 0)
        
        portal_3b["3.1(c)"]["taxable"] += sup.get("osup_nil_exmp", {}).get("txval", 0)
        portal_3b["3.1(d)"]["taxable"] += sup.get("isup_rev", {}).get("txval", 0)
        portal_3b["3.1(d)"]["igst"] += sup.get("isup_rev", {}).get("iamt", 0)
        portal_3b["3.1(d)"]["tax"] += sup.get("isup_rev", {}).get("iamt", 0)
        portal_3b["3.1(e)"]["taxable"] += sup.get("osup_nongst", {}).get("txval", 0)
    
    return portal_3b


def compare_data(books_3b, portal_3b):
    result = {}
    for key in books_3b:
        # Calculate Differences
        diff_taxable = books_3b[key]['taxable'] - portal_3b[key]['taxable']
        diff_igst = books_3b[key]['igst'] - portal_3b[key]['igst']
        diff_cgst = books_3b[key]['cgst'] - portal_3b[key]['cgst']
        diff_sgst = books_3b[key]['sgst'] - portal_3b[key]['sgst']
        diff_tax = books_3b[key]['tax'] - portal_3b[key]['tax']
        
        # Determine Status
        status = "Matched"
        total_diff_abs = abs(diff_taxable) + abs(diff_igst) + abs(diff_cgst) + abs(diff_sgst)
        
        if total_diff_abs > 1.0: # Tolerance of 1 Rupee
            if key == "3.1(d)" and books_3b[key]['taxable'] == 0 and portal_3b[key]['taxable'] > 0:
                 status = "RCM - Purchase Side"
            else:
                 status = "Mismatch"
        
        result[key] = {
            'books': books_3b[key],
            'portal': portal_3b[key],
            'difference': {
                'taxable': diff_taxable,
                'igst': diff_igst,
                'cgst': diff_cgst,
                'sgst': diff_sgst,
                'tax': diff_tax
            },
            'status': status
        }
    return result


@api_view(['POST'])
@permission_classes([AllowAny])
def download_excel(request):
    try:
        results = request.data.get('results', {})
        if not results:
            return Response({'error': 'No results data provided'}, status=400)
            
        username = request.data.get('username', '')
        gstin = request.data.get('gstin', '')
        reco_type = request.data.get('reco_type', '')
        year = request.data.get('year', '')
        month = request.data.get('month', '')
        quarter = request.data.get('quarter', '')
        
        wb = Workbook()
        ws = wb.active
        ws.title = "GSTR-3B Reconciliation"
        
        # Styles
        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=10)
        border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
        center_align = Alignment(horizontal='center', vertical='center')
        
        # Title
        ws.merge_cells('A1:N1')
        title_cell = ws['A1']
        title_cell.value = "GSTR-3B vs Books Reconciliation Report"
        title_cell.font = Font(bold=True, size=16, color="1F4E78")
        title_cell.alignment = Alignment(horizontal='center', vertical='center')
        
        # Info
        ws['A2'] = f"Party Name: {username}"
        ws['A2'].font = Font(bold=True, size=11)
        ws['E2'] = f"GSTIN: {gstin}"
        ws['E2'].font = Font(bold=True, size=11)
        ws['I2'] = f"Period: {reco_type} {year} {month or quarter or ''}"
        ws['I2'].font = Font(bold=True, size=11)

        # Headers: Table | Books_Taxable | Books_IGST | Books_CGST | Books_SGST | Portal_Taxable | ... | Status
        headers = [
            "Table", 
            "Books_Taxable", "Books_IGST", "Books_CGST", "Books_SGST",
            "Portal_Taxable", "Portal_IGST", "Portal_CGST", "Portal_SGST",
            "Diff_Taxable", "Diff_IGST", "Diff_CGST", "Diff_SGST",
            "Status"
        ]
        
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=4, column=col_idx, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.border = border
            cell.alignment = center_align
            
        # Data
        row = 5
        # Order of sections
        sections = ["3.1(a)", "3.1(b)", "3.1(c)", "3.1(d)", "3.1(e)"]
        
        for section in sections:
            data = results.get(section, {})
            if not data:
                continue
                
            books = data.get('books', {})
            portal = data.get('portal', {})
            diff = data.get('difference', {})
            
            # Helper to safely get float
            def g(d, k): return float(d.get(k, 0) or 0)
            
            # Values
            b_taxable = g(books, 'taxable')
            b_igst = g(books, 'igst')
            b_cgst = g(books, 'cgst')
            b_sgst = g(books, 'sgst')
            
            p_taxable = g(portal, 'taxable')
            p_igst = g(portal, 'igst')
            p_cgst = g(portal, 'cgst')
            p_sgst = g(portal, 'sgst')
            
            d_taxable = g(diff, 'taxable')
            d_igst = g(diff, 'igst')
            d_cgst = g(diff, 'cgst')
            d_sgst = g(diff, 'sgst')
            
            # Determine Status
            status = "Matched"
            total_diff = abs(d_taxable) + abs(d_igst) + abs(d_cgst) + abs(d_sgst)
            
            if total_diff > 1.0: # Tolerance
                if section == "3.1(d)" and b_taxable == 0 and p_taxable > 0:
                     status = "RCM - Purchase Side"
                else:
                     status = "Mismatch"
            
            # Use existing status if available (preferred)
            if isinstance(data, dict) and 'status' in data:
                status = data['status']

            # Write Row
            vals = [
                section,
                round(b_taxable, 2), round(b_igst, 2), round(b_cgst, 2), round(b_sgst, 2),
                round(p_taxable, 2), round(p_igst, 2), round(p_cgst, 2), round(p_sgst, 2),
                round(d_taxable, 2), round(d_igst, 2), round(d_cgst, 2), round(d_sgst, 2),
                status
            ]
            
            for col_idx, val in enumerate(vals, 1):
                cell = ws.cell(row=row, column=col_idx, value=val)
                cell.border = border
                
                # Highlight Status
                if col_idx == 14: # Status column
                     if status == "Matched":
                         cell.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid") # Green
                     else:
                         cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid") # Red
                
            row += 1

        # Adjust widths
        for col_idx in range(1, 15):
             ws.column_dimensions[get_column_letter(col_idx)].width = 15

        output = BytesIO()
        wb.save(output)
        output.seek(0)
        
        response = HttpResponse(output.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="GSTR3B_Reconciliation_{gstin}_{year}.xlsx"'
        return response

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({'error': f'Export failed: {str(e)}'}, status=500)
