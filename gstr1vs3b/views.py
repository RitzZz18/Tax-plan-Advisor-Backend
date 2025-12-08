from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.http import HttpResponse
import requests
from datetime import datetime, timedelta
from .models import ReconciliationReport, GSTSession
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import calendar
from io import BytesIO
import uuid

@api_view(['POST'])
@permission_classes([AllowAny])
def generate_otp(request):
    username = request.data.get('username')
    gstin = request.data.get('gstin')
    
    if not username or not username.strip():
        return Response({'error': 'Username cannot be empty'}, status=400)
    
    if not gstin or len(gstin) != 15:
        return Response({'error': 'GSTIN must be 15 characters'}, status=400)
    
    if not settings.SANDBOX_API_KEY or not settings.SANDBOX_API_SECRET:
        return Response({'error': 'Sandbox API credentials not configured'}, status=500)
    
    try:
        auth_response = requests.post(
            "https://api.sandbox.co.in/authenticate",
            headers={
                "x-api-key": settings.SANDBOX_API_KEY,
                "x-api-secret": settings.SANDBOX_API_SECRET
            }
        )
        
        if auth_response.status_code != 200:
            return Response({'error': f'Authentication failed: {auth_response.text}'}, status=500)
        
        access_token = auth_response.json().get("data", {}).get("access_token")
        
        if not access_token:
            return Response({'error': 'Failed to generate JWT token'}, status=500)
        
        otp_response = requests.post(
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
        
        
        if otp_response.status_code != 200:
            return Response({'error': f'OTP request failed: {otp_response.text}'}, status=400)
        
        data = otp_response.json().get("data", {})
        if data.get("status_cd") == "0":
            error_info = data.get("error", {})
            error_code = error_info.get("error_cd", "")
            error_msg = error_info.get("message", data.get("message", "OTP generation failed"))
            
            user_message = error_msg
            if error_code == "AUTH4037":
                user_message = "API access is not enabled on GST Portal. Please use Test Mode to try the application."
            elif error_code == "AUTH403":
                user_message = "Maximum session limit exceeded for this GSP account. Please try again later or use Test Mode."
            elif error_code == "TEC4001":
                user_message = "OTP server is currently down. Please try again later or use Test Mode."
            
            return Response({
                'error': user_message,
                'error_code': error_code,
                'use_test_mode': True
            }, status=400)
        
        gst_session = GSTSession.objects.create(
            username=username,
            gstin=gstin,
            access_token=access_token
        )
        
        GSTSession.objects.filter(created_at__lt=datetime.now() - timedelta(hours=24)).delete()
        
        return Response({
            'message': 'OTP sent successfully',
            'session_id': str(gst_session.session_id)
        })
    except Exception as e:
        return Response({'error': f'Error: {str(e)}'}, status=500)

@api_view(['POST'])
@permission_classes([AllowAny])
def verify_otp(request):
    otp = request.data.get('otp')
    
    if not otp or not otp.strip():
        return Response({'error': 'OTP cannot be empty'}, status=400)
    
    session_id = request.data.get('session_id')
    if not session_id:
        return Response({'error': 'Session ID required'}, status=400)
    
    try:
        gst_session = GSTSession.objects.get(session_id=session_id)
        username = gst_session.username
        gstin = gst_session.gstin
        access_token = gst_session.access_token
    except GSTSession.DoesNotExist:
        return Response({'error': 'Session expired. Please generate OTP again'}, status=400)
    
    verify_response = requests.post(
        "https://api.sandbox.co.in/gst/compliance/tax-payer/otp/verify",
        json={"username": username, "gstin": gstin},
        params={"otp": otp},
        headers={
            "x-source": "primary",
            "x-api-version": "1.0.0",
            "Authorization": access_token,
            "x-api-key": settings.SANDBOX_API_KEY,
            "Content-Type": "application/json"
        }
    )
    
    data = verify_response.json().get("data", {})
    taxpayer_token = data.get("access_token")
    
    if data.get("status_cd") == "0" or not taxpayer_token:
        return Response({'error': data.get("message", "OTP verification failed")}, status=400)
    
    gst_session.taxpayer_token = taxpayer_token
    gst_session.save(update_fields=['taxpayer_token', 'updated_at'])
    
    return Response({'message': 'OTP verified successfully'})

@api_view(['POST'])
@permission_classes([AllowAny])
def reconcile(request):
    fy_year = request.data.get('fy_year')
    
    if not fy_year or not str(fy_year).isdigit():
        return Response({'error': 'Invalid year'}, status=400)
    
    session_id = request.data.get('session_id')
    if not session_id:
        return Response({'error': 'Session ID required'}, status=400)
    
    try:
        gst_session = GSTSession.objects.get(session_id=session_id)
        taxpayer_token = gst_session.taxpayer_token
        if not taxpayer_token:
            return Response({'error': 'Please verify OTP first'}, status=400)
    except GSTSession.DoesNotExist:
        return Response({'error': 'Session expired. Please generate OTP again'}, status=400)
    
    start_year = int(fy_year)
    end_year = start_year + 1
    all_months = [(start_year, m) for m in range(4, 13)] + [(end_year, m) for m in range(1, 4)]
    current = datetime.now()
    cutoff_month = current.month - 1 if current.day < 20 else current.month
    months = [(y, m) for y, m in all_months if (y < current.year) or (y == current.year and m < cutoff_month)]
    
    if not months:
        return Response({'error': 'No valid months available'}, status=400)
    
    results = []
    for year, month in months:
        result = reconcile_month(year, month, taxpayer_token)
        if result:
            result['year'] = year
            result['month'] = month
            results.append(result)
    
    ReconciliationReport.objects.create(
        username=gst_session.username,
        gstin=gst_session.gstin,
        fy_year=start_year,
        report_data=results
    )
    
    return Response({'results': results})

def reconcile_month(year, month, taxpayer_token):
    base_url = "https://api.sandbox.co.in/gst/compliance/tax-payer/gstrs/gstr-1"
    headers = {
        "x-api-version": "1.0.0",
        "Authorization": taxpayer_token,
        "x-api-key": settings.SANDBOX_API_KEY
    }
    
    try:
        gstr1_data = {}
        for dt in ["b2b", "b2cl", "b2cs", "exp", "cdnr", "b2ba", "b2cla", "b2csa", "cdnra", "nil"]:
            r = requests.get(f"{base_url}/{dt}/{year}/{month:02d}", headers=headers)
            if r.status_code != 200:
                gstr1_data[dt] = None
            else:
                gstr1_data[dt] = r.json().get("data", {}).get("data", {}).get(dt if dt != "nil" else "nil_supplies")
    except Exception:
        return None

    tx1 = ig1 = cg1 = sg1 = 0

    for e in gstr1_data.get("b2b") or []:
        for inv in e.get("inv", []):
            if inv.get("inv_typ") not in ["SEWP", "SEWOP"]:
                for itm in inv.get("itms", []):
                    d = itm.get("itm_det", {})
                    tx1 += float(d.get("txval", 0))
                    ig1 += float(d.get("iamt", 0))
                    cg1 += float(d.get("camt", 0))
                    sg1 += float(d.get("samt", 0))

    for e in gstr1_data.get("b2cl") or []:
        for inv in e.get("inv", []):
            for itm in inv.get("itms", []):
                d = itm.get("itm_det", {})
                tx1 += float(d.get("txval", 0))
                ig1 += float(d.get("iamt", 0))
                cg1 += float(d.get("camt", 0))
                sg1 += float(d.get("samt", 0))

    for e in gstr1_data.get("b2cs") or []:
        tx1 += float(e.get("txval", 0))
        ig1 += float(e.get("iamt", 0))
        cg1 += float(e.get("camt", 0))
        sg1 += float(e.get("samt", 0))

    for e in gstr1_data.get("cdnr") or []:
        for note in e.get("nt", []):
            for itm in note.get("itms", []):
                d = itm.get("itm_det", {})
                tx1 += float(d.get("txval", 0))
                ig1 += float(d.get("iamt", 0))
                cg1 += float(d.get("camt", 0))
                sg1 += float(d.get("samt", 0))

    for e in gstr1_data.get("b2ba") or []:
        for inv in e.get("inv", []):
            if inv.get("inv_typ") not in ["SEWP", "SEWOP"]:
                for itm in inv.get("itms", []):
                    d = itm.get("itm_det", {})
                    od = inv.get("oitms", [{}])[0].get("itm_det", {})
                    tx1 += float(d.get("txval", 0)) - float(od.get("txval", 0))
                    ig1 += float(d.get("iamt", 0)) - float(od.get("iamt", 0))
                    cg1 += float(d.get("camt", 0)) - float(od.get("camt", 0))
                    sg1 += float(d.get("samt", 0)) - float(od.get("samt", 0))

    for e in gstr1_data.get("b2cla") or []:
        for inv in e.get("inv", []):
            for itm in inv.get("itms", []):
                d = itm.get("itm_det", {})
                od = inv.get("oitms", [{}])[0].get("itm_det", {})
                tx1 += float(d.get("txval", 0)) - float(od.get("txval", 0))
                ig1 += float(d.get("iamt", 0)) - float(od.get("iamt", 0))
                cg1 += float(d.get("camt", 0)) - float(od.get("camt", 0))
                sg1 += float(d.get("samt", 0)) - float(od.get("samt", 0))

    for e in gstr1_data.get("b2csa") or []:
        tx1 += float(e.get("txval", 0)) - float(e.get("odtls", {}).get("txval", 0))
        ig1 += float(e.get("iamt", 0)) - float(e.get("odtls", {}).get("iamt", 0))
        cg1 += float(e.get("camt", 0)) - float(e.get("odtls", {}).get("camt", 0))
        sg1 += float(e.get("samt", 0)) - float(e.get("odtls", {}).get("samt", 0))

    for e in gstr1_data.get("cdnra") or []:
        for note in e.get("nt", []):
            for itm in note.get("itms", []):
                d = itm.get("itm_det", {})
                od = note.get("oitms", [{}])[0].get("itm_det", {})
                tx1 += float(d.get("txval", 0)) - float(od.get("txval", 0))
                ig1 += float(d.get("iamt", 0)) - float(od.get("iamt", 0))
                cg1 += float(d.get("camt", 0)) - float(od.get("camt", 0))
                sg1 += float(d.get("samt", 0)) - float(od.get("samt", 0))

    zr1 = 0
    for e in gstr1_data.get("exp") or []:
        for inv in e.get("inv", []):
            zr1 += float(inv.get("val", 0))
    for e in gstr1_data.get("b2b") or []:
        for inv in e.get("inv", []):
            if inv.get("inv_typ") in ["SEWP", "SEWOP"]:
                zr1 += float(inv.get("val", 0))

    ng1 = sum(float(e.get("ngsup_amt", 0)) for e in gstr1_data.get("nil") or [])

    r = requests.get(f"https://api.sandbox.co.in/gst/compliance/tax-payer/gstrs/gstr-3b/{year}/{month:02d}", headers=headers)
    sup = r.json().get("data", {}).get("data", {}).get("sup_details", {})

    od = sup.get("osup_det", {})
    tx3 = float(od.get("txval", 0))
    ig3 = float(od.get("iamt", 0))
    cg3 = float(od.get("camt", 0))
    sg3 = float(od.get("samt", 0))
    zr3 = float(sup.get("osup_zero", {}).get("txval", 0))
    ng3 = float(sup.get("osup_nongst", {}).get("txval", 0))

    return {"tx1": tx1, "ig1": ig1, "cg1": cg1, "sg1": sg1, "zr1": zr1, "ng1": ng1,
            "tx3": tx3, "ig3": ig3, "cg3": cg3, "sg3": sg3, "zr3": zr3, "ng3": ng3}

@api_view(['POST'])
@permission_classes([AllowAny])
def reconcile_test(request):
    fy_year = request.data.get('fy_year', '2024')
    username = request.data.get('username', 'test_user')
    gstin = request.data.get('gstin', 'TEST123456789')
    
    results = [
        {"year": 2024, "month": 4, "tx1": 100000, "ig1": 9000, "cg1": 4500, "sg1": 4500, "cs1": 0, "zr1": 0, "ng1": 0,
         "tx3": 98000, "ig3": 8820, "cg3": 4410, "sg3": 4410, "cs3": 0, "zr3": 0, "ng3": 0},
        {"year": 2024, "month": 5, "tx1": 120000, "ig1": 10800, "cg1": 5400, "sg1": 5400, "cs1": 0, "zr1": 0, "ng1": 0,
         "tx3": 120000, "ig3": 10800, "cg3": 5400, "sg3": 5400, "cs3": 0, "zr3": 0, "ng3": 0},
        {"year": 2024, "month": 6, "tx1": 95000, "ig1": 8550, "cg1": 4275, "sg1": 4275, "cs1": 0, "zr1": 0, "ng1": 0,
         "tx3": 97000, "ig3": 8730, "cg3": 4365, "sg3": 4365, "cs3": 0, "zr3": 0, "ng3": 0},
        {"year": 2024, "month": 7, "tx1": 110000, "ig1": 9900, "cg1": 4950, "sg1": 4950, "cs1": 0, "zr1": 0, "ng1": 0,
         "tx3": 110000, "ig3": 9900, "cg3": 4950, "sg3": 4950, "cs3": 0, "zr3": 0, "ng3": 0},
        {"year": 2024, "month": 8, "tx1": 105000, "ig1": 9450, "cg1": 4725, "sg1": 4725, "cs1": 0, "zr1": 0, "ng1": 0,
         "tx3": 103000, "ig3": 9270, "cg3": 4635, "sg3": 4635, "cs3": 0, "zr3": 0, "ng3": 0},
    ]
    
    ReconciliationReport.objects.create(
        username=username,
        gstin=gstin,
        fy_year=int(fy_year),
        report_data=results
    )
    
    return Response({'results': results})

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
