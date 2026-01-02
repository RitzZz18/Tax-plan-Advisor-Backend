from datetime import datetime
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Border, Side, Alignment
from openpyxl.utils import get_column_letter
from io import BytesIO
import calendar

from gst_auth.utils import get_valid_session, safe_api_call


# ---------------------------------------------------------
# 🔹 Utility: Process GSTR1 section safely
# ---------------------------------------------------------
def fetch_gstr1_section(section, year, month, headers):
    url = f"https://api.sandbox.co.in/gst/compliance/tax-payer/gstrs/gstr-1/{section}/{year}/{month:02d}"
    status, data = safe_api_call("GET", url, headers=headers)

    if status != 200:
        return []

    container = data.get("data", {}).get("data", {})
    return container.get(section if section != "nil" else "nil_supplies", [])


# ---------------------------------------------------------
# 🔹 MONTHLY RECONCILE
# ---------------------------------------------------------
def reconcile_month(year, month, token):
    headers = {
        "x-api-version": "1.0.0",
        "Authorization": token,
        "x-api-key": settings.SANDBOX_API_KEY
    }

    sections = ["b2b", "b2cl", "b2cs", "exp", "cdnr", "nil"]
    data = {sec: fetch_gstr1_section(sec, year, month, headers) for sec in sections}

    tx1 = ig1 = cg1 = sg1 = zr1 = ng1 = 0

    # Process core sections
    try:
        # B2B
        for e in data["b2b"]:
            for inv in e.get("inv", []):
                if inv.get("inv_typ") in ["SEWP", "SEWOP"]:
                    zr1 += float(inv.get("val", 0))
                    continue
                for itm in inv.get("itms", []):
                    d = itm.get("itm_det", {})
                    tx1 += float(d.get("txval", 0))
                    ig1 += float(d.get("iamt", 0))
                    cg1 += float(d.get("camt", 0))
                    sg1 += float(d.get("samt", 0))

        # B2CL + B2CS
        for sec in ["b2cl", "b2cs"]:
            for e in data[sec]:
                items = e.get("inv", []) if sec == "b2cl" else [e]
                for inv in items:
                    itms = inv.get("itms", []) if sec == "b2cl" else [inv]
                    for itm in itms:
                        d = itm.get("itm_det", itm)
                        tx1 += float(d.get("txval", 0))
                        ig1 += float(d.get("iamt", 0))
                        cg1 += float(d.get("camt", 0))
                        sg1 += float(d.get("samt", 0))

        # CDN
        for e in data["cdnr"]:
            for nt in e.get("nt", []):
                for itm in nt.get("itms", []):
                    d = itm.get("itm_det", {})
                    tx1 += float(d.get("txval", 0))
                    ig1 += float(d.get("iamt", 0))
                    cg1 += float(d.get("camt", 0))
                    sg1 += float(d.get("samt", 0))

        # EXP
        for e in data["exp"]:
            for inv in e.get("inv", []):
                zr1 += float(inv.get("val", 0))

        # NIL
        ng1 = sum(float(e.get("ngsup_amt", 0)) for e in data["nil"])

    except:
        pass

    # GET GSTR-3B
    status, g3 = safe_api_call(
        "GET",
        f"https://api.sandbox.co.in/gst/compliance/tax-payer/gstrs/gstr-3b/{year}/{month:02d}",
        headers=headers
    )

    if status != 200:
        return None

    sup = g3.get("data", {}).get("data", {}).get("sup_details", {})

    od = sup.get("osup_det", {})
    tx3 = float(od.get("txval", 0))
    ig3 = float(od.get("iamt", 0))
    cg3 = float(od.get("camt", 0))
    sg3 = float(od.get("samt", 0))

    zr3 = float(sup.get("osup_zero", {}).get("txval", 0))
    ng3 = float(sup.get("osup_nongst", {}).get("txval", 0))

    return {
        "tx1": tx1, "ig1": ig1, "cg1": cg1, "sg1": sg1,
        "zr1": zr1, "ng1": ng1,
        "tx3": tx3, "ig3": ig3, "cg3": cg3, "sg3": sg3,
        "zr3": zr3, "ng3": ng3
    }


# ---------------------------------------------------------
# 🔹 RECONCILE MAIN (Uses unified session)
# ---------------------------------------------------------
@api_view(['POST'])
@permission_classes([AllowAny])
def reconcile(request):
    fy_year = request.data.get("fy_year")
    session_id = request.data.get("session_id")

    if not fy_year or not str(fy_year).isdigit():
        return Response({"error": "Invalid FY year"}, status=400)

    if not session_id:
        return Response({"error": "Session ID required"}, status=400)

    # Validate session using unified auth
    session, error = get_valid_session(session_id)
    if error:
        return Response({"error": error}, status=401)

    start_year = int(fy_year)
    end_year = start_year + 1

    all_months = [
        (start_year, m) for m in range(4, 13)
    ] + [
        (end_year, m) for m in range(1, 4)
    ]

    now = datetime.now()
    cutoff = now.month - 1 if now.day < 20 else now.month

    valid_months = [
        (y, m) for y, m in all_months
        if (y < now.year) or (y == now.year and m < cutoff)
    ]

    results = []
    for y, m in valid_months:
        res = reconcile_month(y, m, session.taxpayer_token)
        if res:
            res["year"] = y
            res["month"] = m
            results.append(res)

    return Response({"results": results, "gstin": session.gstin, "username": session.username})


@api_view(['POST'])
@permission_classes([AllowAny])
def download_excel(request):
    results = request.data.get('results', [])
    username = request.data.get('username', '')
    gstin = request.data.get('gstin', '')
    fy_year = request.data.get('fy_year', '')
    
    wb = Workbook()
    ws = wb.active
    ws.title = "GSTR Reconciliation"
    
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    month_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    month_font = Font(bold=True, color="FFFFFF", size=11)
    diff_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    match_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
    
    total_cols = len(results) * 4 + 1
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
    title_cell = ws['A1']
    title_cell.value = "GSTR-1 vs GSTR-3B Reconciliation Report"
    title_cell.font = Font(bold=True, size=16, color="1F4E78")
    title_cell.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[1].height = 30
    
    ws['A2'] = f"Username: {username}"
    ws['A2'].font = Font(bold=True, size=11)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=3)
    
    ws.cell(2, 4, f"GSTIN: {gstin}").font = Font(bold=True, size=11)
    ws.merge_cells(start_row=2, start_column=4, end_row=2, end_column=6)
    
    ws.cell(2, 7, f"FY: {fy_year}").font = Font(bold=True, size=11)
    ws.merge_cells(start_row=2, start_column=7, end_row=2, end_column=9)
    ws.row_dimensions[2].height = 20
    
    ws['A4'] = "Particular"
    ws['A4'].fill = header_fill
    ws['A4'].font = header_font
    ws['A4'].border = border
    
    col = 2
    for data in results:
        month_name = calendar.month_abbr[data['month']] + " " + str(data['year'])
        ws.merge_cells(start_row=4, start_column=col, end_row=4, end_column=col+2)
        cell = ws.cell(4, col, month_name)
        cell.fill = month_fill
        cell.font = month_font
        cell.alignment = Alignment(horizontal='center')
        cell.border = border
        col += 4
    
    col = 2
    for _ in results:
        for header in ['GSTR-1', 'GSTR-3B', 'Diff']:
            cell = ws.cell(5, col, header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center')
            cell.border = border
            col += 1
        col += 1
    
    particulars = [
        ('Total Taxable Value', 'tx1', 'tx3'),
        ('IGST', 'ig1', 'ig3'),
        ('CGST', 'cg1', 'cg3'),
        ('SGST', 'sg1', 'sg3'),
        ('Exports', 'zr1', 'zr3'),
        ('Non-GST', 'ng1', 'ng3')
    ]
    
    row = 6
    for particular, key1, key3 in particulars:
        ws.cell(row, 1, particular).border = border
        col = 2
        for data in results:
            gstr1 = data.get(key1, 0)
            gstr3 = data.get(key3, 0)
            diff = gstr1 - gstr3
            
            ws.cell(row, col, round(gstr1, 2)).border = border
            ws.cell(row, col).number_format = '#,##0.00'
            ws.cell(row, col).alignment = Alignment(horizontal='right')
            
            ws.cell(row, col+1, round(gstr3, 2)).border = border
            ws.cell(row, col+1).number_format = '#,##0.00'
            ws.cell(row, col+1).alignment = Alignment(horizontal='right')
            
            diff_cell = ws.cell(row, col+2, round(diff, 2))
            diff_cell.border = border
            diff_cell.number_format = '#,##0.00'
            diff_cell.alignment = Alignment(horizontal='right')
            
            if abs(diff) > 0.01:
                diff_cell.fill = diff_fill
                diff_cell.font = Font(bold=True, color="9C0006")
            else:
                diff_cell.fill = match_fill
                diff_cell.font = Font(color="006100")
            
            col += 4
        row += 1
    
    ws.column_dimensions['A'].width = 25
    for i in range(2, col):
        ws.column_dimensions[get_column_letter(i)].width = 14
    
    ws.freeze_panes = 'B6'
    
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    response = HttpResponse(output.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="GSTR_Reconciliation_{gstin}_{fy_year}.xlsx"'
    return response


@api_view(['POST'])
@permission_classes([AllowAny])
def download_excel(request):
    results = request.data.get('results', [])
    username = request.data.get('username', '')
    gstin = request.data.get('gstin', '')
    fy_year = request.data.get('fy_year', '')
    
    wb = Workbook()
    ws = wb.active
    ws.title = "GSTR Reconciliation"
    
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    month_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    month_font = Font(bold=True, color="FFFFFF", size=11)
    diff_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    match_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
    
    total_cols = len(results) * 4 + 1
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
    title_cell = ws['A1']
    title_cell.value = "GSTR-1 vs GSTR-3B Reconciliation Report"
    title_cell.font = Font(bold=True, size=16, color="1F4E78")
    title_cell.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[1].height = 30
    
    ws['A2'] = f"Username: {username}"
    ws['A2'].font = Font(bold=True, size=11)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=3)
    
    ws.cell(2, 4, f"GSTIN: {gstin}").font = Font(bold=True, size=11)
    ws.merge_cells(start_row=2, start_column=4, end_row=2, end_column=6)
    
    ws.cell(2, 7, f"FY: {fy_year}").font = Font(bold=True, size=11)
    ws.merge_cells(start_row=2, start_column=7, end_row=2, end_column=9)
    ws.row_dimensions[2].height = 20
    
    ws['A4'] = "Particular"
    ws['A4'].fill = header_fill
    ws['A4'].font = header_font
    ws['A4'].border = border
    
    col = 2
    for data in results:
        month_name = calendar.month_abbr[data['month']] + " " + str(data['year'])
        ws.merge_cells(start_row=4, start_column=col, end_row=4, end_column=col+2)
        cell = ws.cell(4, col, month_name)
        cell.fill = month_fill
        cell.font = month_font
        cell.alignment = Alignment(horizontal='center')
        cell.border = border
        col += 4
    
    col = 2
    for _ in results:
        for header in ['GSTR-1', 'GSTR-3B', 'Diff']:
            cell = ws.cell(5, col, header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center')
            cell.border = border
            col += 1
        col += 1
    
    particulars = [
        ('Total Taxable Value', 'tx1', 'tx3'),
        ('IGST', 'ig1', 'ig3'),
        ('CGST', 'cg1', 'cg3'),
        ('SGST', 'sg1', 'sg3'),
        ('Exports', 'zr1', 'zr3'),
        ('Non-GST', 'ng1', 'ng3')
    ]
    
    row = 6
    for particular, key1, key3 in particulars:
        ws.cell(row, 1, particular).border = border
        col = 2
        for data in results:
            gstr1 = data.get(key1, 0)
            gstr3 = data.get(key3, 0)
            diff = gstr1 - gstr3
            
            ws.cell(row, col, round(gstr1, 2)).border = border
            ws.cell(row, col).number_format = '#,##0.00'
            ws.cell(row, col).alignment = Alignment(horizontal='right')
            
            ws.cell(row, col+1, round(gstr3, 2)).border = border
            ws.cell(row, col+1).number_format = '#,##0.00'
            ws.cell(row, col+1).alignment = Alignment(horizontal='right')
            
            diff_cell = ws.cell(row, col+2, round(diff, 2))
            diff_cell.border = border
            diff_cell.number_format = '#,##0.00'
            diff_cell.alignment = Alignment(horizontal='right')
            
            if abs(diff) > 0.01:
                diff_cell.fill = diff_fill
                diff_cell.font = Font(bold=True, color="9C0006")
            else:
                diff_cell.fill = match_fill
                diff_cell.font = Font(color="006100")
            
            col += 4
        row += 1
    
    ws.column_dimensions['A'].width = 25
    for i in range(2, col):
        ws.column_dimensions[get_column_letter(i)].width = 14
    
    ws.freeze_panes = 'B6'
    
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    response = HttpResponse(output.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="GSTR_Reconciliation_{gstin}_{fy_year}.xlsx"'
    return response
