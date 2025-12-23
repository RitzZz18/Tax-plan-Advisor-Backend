import uuid
import requests
from datetime import datetime, timedelta

from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Border, Side, Alignment
from openpyxl.utils import get_column_letter
from io import BytesIO

from .models import GSTSession, ReconciliationReport


def safe_api_call(method, url, **kwargs):
    """Unified request handler for cleaner code."""
    try:
        kwargs["timeout"] = 20
        res = requests.request(method, url, **kwargs)
        try:
            data = res.json()
        except:
            data = {}
        return res.status_code, data
    except requests.Timeout:
        return 504, {"error": "timeout"}
    except requests.RequestException:
        return 503, {"error": "connection_failed"}
    except Exception:
        return 500, {"error": "internal_error"}


@api_view(['POST'])
@permission_classes([AllowAny])
def generate_otp(request):
    username = request.data.get("username")
    gstin = request.data.get("gstin")

    if not username or not username.strip():
        return Response({"error": "Username required"}, status=400)

    if not gstin or len(gstin) != 15:
        return Response({"error": "GSTIN must be 15 characters"}, status=400)

    # Step 1 → Authenticate
    status_code, auth_data = safe_api_call(
        "POST",
        "https://api.sandbox.co.in/authenticate",
        headers={
            "x-api-key": settings.SANDBOX_API_KEY,
            "x-api-secret": settings.SANDBOX_API_SECRET
        }
    )

    if status_code != 200:
        return Response({"error": "Failed to authenticate"}, status=500)

    access_token = auth_data.get("data", {}).get("access_token")
    if not access_token:
        return Response({"error": "Invalid token from GST API"}, status=500)

    # Step 2 → Send OTP
    status_code, otp_data = safe_api_call(
        "POST",
        "https://api.sandbox.co.in/gst/compliance/tax-payer/otp",
        json={"username": username, "gstin": gstin},
        headers={
            "x-source": "primary",
            "x-api-version": "1.0.0",
            "Authorization": access_token,
            "x-api-key": settings.SANDBOX_API_KEY,
            "Content-Type": "application/json"
        }
    )

    data = otp_data.get("data", {})

    if data.get("status_cd") == "0":
        return Response({
            "error": data.get("message", "OTP failed"),
            "error_code": data.get("error", {}).get("error_cd", "")
        }, status=400)

    # Create DB session
    gst_session = GSTSession.objects.create(
        session_id=uuid.uuid4(),
        username=username,
        gstin=gstin,
        access_token=access_token
    )

    # Auto-clean old sessions
    GSTSession.objects.filter(
        created_at__lt=datetime.now() - timedelta(hours=24)
    ).delete()

    return Response({
        "message": "OTP sent successfully",
        "session_id": str(gst_session.session_id)
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_otp(request):
    otp = request.data.get("otp")
    session_id = request.data.get("session_id")

    if not otp or not otp.strip():
        return Response({"error": "OTP required"}, status=400)

    if not session_id:
        return Response({"error": "Session ID required"}, status=400)

    try:
        gst_session = GSTSession.objects.get(session_id=session_id)
    except GSTSession.DoesNotExist:
        return Response({"error": "Session expired"}, status=400)

    # Verify OTP
    status_code, verify_data = safe_api_call(
        "POST",
        "https://api.sandbox.co.in/gst/compliance/tax-payer/otp/verify",
        json={"username": gst_session.username, "gstin": gst_session.gstin},
        params={"otp": otp},
        headers={
            "x-source": "primary",
            "x-api-version": "1.0.0",
            "Authorization": gst_session.access_token,
            "x-api-key": settings.SANDBOX_API_KEY,
            "Content-Type": "application/json"
        }
    )

    data = verify_data.get("data", {})
    taxpayer_token = data.get("access_token")

    if data.get("status_cd") == "0" or not taxpayer_token:
        return Response({"error": "OTP verification failed"}, status=400)

    gst_session.taxpayer_token = taxpayer_token
    gst_session.save(update_fields=["taxpayer_token", "updated_at"])

    return Response({
        "message": "OTP verified successfully",
        "session_id": str(gst_session.session_id)
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def reconciliation(request):
    session_id = request.data.get('session_id')
    reco_type = request.data.get('reco_type')
    year = request.data.get('year')
    month = request.data.get('month')
    quarter = request.data.get('quarter')
    
    if not session_id:
        return Response({'error': 'Session ID required'}, status=400)
        
    if not all([reco_type, year]):
        return Response({'error': 'Missing required fields'}, status=400)
    
    try:
        gst_session = GSTSession.objects.get(session_id=session_id)
    except GSTSession.DoesNotExist:
        return Response({'error': 'Session expired'}, status=400)
        
    if not gst_session.taxpayer_token:
        return Response({'error': 'Please verify OTP first'}, status=400)
    
    # Handle file upload
    if 'file' not in request.FILES:
        return Response({'error': 'No file uploaded'}, status=400)
    
    try:
        file = request.FILES['file']
        df = pd.read_excel(file)
        
        # Get months to process
        months = get_months(reco_type, int(year), int(month) if month else None, quarter)
        
        # Process reconciliation
        norm_df = normalize_helper_data(df)
        books_3b = calculate_books_3b(norm_df)
        portal_3b = fetch_portal_3b(months, gst_session.taxpayer_token)
        comparison = compare_data(books_3b, portal_3b)
        
        # Save report
        ReconciliationReport.objects.create(
            username=gst_session.username,
            gstin=gst_session.gstin,
            reco_type=reco_type,
            year=int(year),
            month=int(month) if month else None,
            quarter=quarter,
            report_data=comparison
        )
        
        return Response({
            'status': 'success',
            'message': 'Reconciliation completed',
            'data': comparison,
            'session_info': {
                'username': gst_session.username,
                'gstin': gst_session.gstin,
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


def normalize_helper_data(helper_df):
    normalized_rows = []
    for _, r in helper_df.iterrows():
        if r["Export_Taxable"] > 0:
            sup_cat = "EXPWP" if r["IGST"] > 0 else "EXPWOP"
            taxable = r["Export_Taxable"]
        elif r["SEZ_Taxable"] > 0:
            sup_cat = "SEZWP" if r["IGST"] > 0 else "SEZWOP"
            taxable = r["SEZ_Taxable"]
        elif r["Nil_Rated"] > 0 or r["Exempt"] > 0:
            sup_cat = "NIL"
            taxable = r["Nil_Rated"] + r["Exempt"]
        elif r["Non_GST"] > 0:
            sup_cat = "NON_GST"
            taxable = r["Non_GST"]
        else:
            sup_cat = "DOM"
            taxable = r["Domestic_Taxable"]
        
        normalized_rows.append({
            "SUP_CAT": sup_cat, "Taxable": taxable,
            "IGST": r["IGST"], "CGST": r["CGST"], "SGST": r["SGST"], "Is_RCM": r["Is_RCM"]
        })
    return pd.DataFrame(normalized_rows)


def calculate_books_3b(norm_df):
    books_3b = {k: {"taxable":0,"igst":0,"cgst":0,"sgst":0,"tax":0} for k in ["3.1(a)","3.1(b)","3.1(c)","3.1(d)","3.1(e)"]}
    
    for _, r in norm_df.iterrows():
        tax = r["IGST"] + r["CGST"] + r["SGST"]
        
        if r["Is_RCM"] == "Y":
            key = "3.1(d)"
        elif r["SUP_CAT"] == "DOM":
            key = "3.1(a)"
        elif r["SUP_CAT"] in ("EXPWP","EXPWOP","SEZWP","SEZWOP"):
            key = "3.1(b)"
        elif r["SUP_CAT"] == "NIL":
            key = "3.1(c)"
        elif r["SUP_CAT"] == "NON_GST":
            key = "3.1(e)"
        else:
            continue
        
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
        result[key] = {
            'books': books_3b[key],
            'portal': portal_3b[key],
            'difference': {k: books_3b[key][k] - portal_3b[key][k] for k in ['taxable','igst','cgst','sgst','tax']}
        }
    return result


@api_view(['POST'])
@permission_classes([AllowAny])
def download_excel(request):
    results = request.data.get('results', {})
    username = request.data.get('username', '')
    gstin = request.data.get('gstin', '')
    reco_type = request.data.get('reco_type', '')
    year = request.data.get('year', '')
    month = request.data.get('month', '')
    quarter = request.data.get('quarter', '')
    
    wb = Workbook()
    ws = wb.active
    ws.title = "GSTR-3B Reconciliation"
    
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    diff_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    match_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
    
    # Title
    ws.merge_cells('A1:G1')
    title_cell = ws['A1']
    title_cell.value = "GSTR-3B vs Books Reconciliation Report"
    title_cell.font = Font(bold=True, size=16, color="1F4E78")
    title_cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # Info
    ws['A2'] = f"Username: {username}"
    ws['A2'].font = Font(bold=True, size=11)
    ws['C2'] = f"GSTIN: {gstin}"
    ws['C2'].font = Font(bold=True, size=11)
    ws['E2'] = f"Period: {reco_type} {year} {month or quarter or ''}"
    ws['E2'].font = Font(bold=True, size=11)
    
    # Headers
    headers = ['Section', 'Books Taxable', 'Portal Taxable', 'Taxable Diff', 'Books Tax', 'Portal Tax', 'Tax Diff']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(4, col, header)
        cell.fill = header_fill
        cell.font = header_font
        cell.border = border
        cell.alignment = Alignment(horizontal='center')
    
    # Data
    row = 5
    for section, data in results.items():
        ws.cell(row, 1, section).border = border
        ws.cell(row, 2, round(data['books']['taxable'], 2)).border = border
        ws.cell(row, 3, round(data['portal']['taxable'], 2)).border = border
        
        taxable_diff_cell = ws.cell(row, 4, round(data['difference']['taxable'], 2))
        taxable_diff_cell.border = border
        if abs(data['difference']['taxable']) > 0.01:
            taxable_diff_cell.fill = diff_fill
        else:
            taxable_diff_cell.fill = match_fill
        
        ws.cell(row, 5, round(data['books']['tax'], 2)).border = border
        ws.cell(row, 6, round(data['portal']['tax'], 2)).border = border
        
        tax_diff_cell = ws.cell(row, 7, round(data['difference']['tax'], 2))
        tax_diff_cell.border = border
        if abs(data['difference']['tax']) > 0.01:
            tax_diff_cell.fill = diff_fill
        else:
            tax_diff_cell.fill = match_fill
        
        row += 1
    
    # Column widths
    for col in range(1, 8):
        ws.column_dimensions[get_column_letter(col)].width = 15
    
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    response = HttpResponse(output.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="GSTR3B_Reconciliation_{gstin}_{year}.xlsx"'
    return response
