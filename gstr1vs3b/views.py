import uuid
import requests
from datetime import datetime, timedelta

from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from io import BytesIO
from django.http import HttpResponse
import calendar
from datetime import datetime, date

from .models import GSTSession, ReconciliationReport


# ---------------------------------------------------------
# 🔧 Utility: Safe API request wrapper
# ---------------------------------------------------------
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


# ---------------------------------------------------------
# 🔹 1. GENERATE OTP
# ---------------------------------------------------------
@api_view(['POST'])
@permission_classes([AllowAny])
def generate_otp(request):
    username = request.data.get("username")
    gstin = request.data.get("gstin")

    # Input Validation
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


# ---------------------------------------------------------
# 🔹 2. VERIFY OTP
# ---------------------------------------------------------
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


# =====================================================
# 🔧 HELPER: SAFE VALUE EXTRACTOR
# =====================================================
def get_val(source_dict, key, field):
    """
    Tries to fetch value from:
    1. source_dict[key]['subtotal'][field] (Auto-Pop style)
    2. source_dict[key][field] (Filed style)
    3. Returns 0.0 if not found
    """
    if not source_dict:
        return 0.0
        
    section = source_dict.get(key, {})
    if not section:
        return 0.0

    # Try Auto-Populated Structure (nested in subtotal)
    if "subtotal" in section:
        return float(section["subtotal"].get(field, 0) or 0)
    
    # Try Filed Structure (direct value)
    return float(section.get(field, 0) or 0)


# =====================================================
# 1. FETCH AUTO LIABILITY (The Govt Data)
# =====================================================
def fetch_auto_liability(year, month, headers):
    url = f"https://api.sandbox.co.in/gst/compliance/tax-payer/gstrs/gstr-3b/{year}/{month:02d}/auto-liability-calc"
    status, data = safe_api_call("GET", url, headers=headers)

    if status != 200:
        return None

    # Navigate to sup_details with extreme caution
    # Path: data -> data -> r3bautopop -> liabitc -> sup_details
    try:
        sup_details = (
            data.get("data", {})
                .get("data", {})
                .get("r3bautopop", {})
                .get("liabitc", {})
                .get("sup_details", {})
        )
    except:
        return None

    if not sup_details:
        return None

    # Use the helper to safely grab values regardless of structure
    return {
        # 3.1.a Standard
        "tx": get_val(sup_details, "osup_3_1a", "txval"),
        "igst": get_val(sup_details, "osup_3_1a", "iamt"),
        "cgst": get_val(sup_details, "osup_3_1a", "camt"),
        "sgst": get_val(sup_details, "osup_3_1a", "samt"),
        
        # 3.1.b Exports
        "exp_tx": get_val(sup_details, "osup_3_1b", "txval"),
        "exp_igst": get_val(sup_details, "osup_3_1b", "iamt"),

        # 3.1.c Nil Rated
        "nil_tx": get_val(sup_details, "osup_3_1c", "txval"),

        # 3.1.d RCM (Liability)
        # "rcm_tx": get_val(sup_details, "isup_3_1d", "txval"),
        # "rcm_igst": get_val(sup_details, "isup_3_1d", "iamt"),
        # "rcm_cgst": get_val(sup_details, "isup_3_1d", "camt"),
        # "rcm_sgst": get_val(sup_details, "isup_3_1d", "samt"),

        # 3.1.e Non-GST
        "nongst_tx": get_val(sup_details, "osup_3_1e", "txval"),
    }

# =====================================================
# 2. FETCH FILED GSTR-3B (The User Data)
# =====================================================
def fetch_filed_3b(year, month, headers):
    url = f"https://api.sandbox.co.in/gst/compliance/tax-payer/gstrs/gstr-3b/{year}/{month:02d}"
    status, data = safe_api_call("GET", url, headers=headers)

    if status != 200:
        return None

    # Navigate to sup_details
    # Path: data -> data -> sup_details
    try:
        sup_details = (
            data.get("data", {})
                .get("data", {})
                .get("sup_details", {})
        )
    except:
        return None
        
    if not sup_details:
        return None

    # MAPPING KEYS:
    # Standard -> osup_det
    # Exports  -> osup_zero
    # Nil      -> osup_nil_exmp
    # RCM      -> isup_rev (Note: Key is distinct from Auto)
    # Non-GST  -> osup_nongst

    return {
        # Standard
        "tx": get_val(sup_details, "osup_det", "txval"),
        "igst": get_val(sup_details, "osup_det", "iamt"),
        "cgst": get_val(sup_details, "osup_det", "camt"),
        "sgst": get_val(sup_details, "osup_det", "samt"),
        
        # Exports
        "exp_tx": get_val(sup_details, "osup_zero", "txval"),
        "exp_igst": get_val(sup_details, "osup_zero", "iamt"),

        # Nil
        "nil_tx": get_val(sup_details, "osup_nil_exmp", "txval"),

        # RCM
        # "rcm_tx": get_val(sup_details, "isup_rev", "txval"),
        # "rcm_igst": get_val(sup_details, "isup_rev", "iamt"),
        # "rcm_cgst": get_val(sup_details, "isup_rev", "camt"),
        # "rcm_sgst": get_val(sup_details, "isup_rev", "samt"),

        # Non-GST
        "nongst_tx": get_val(sup_details, "osup_nongst", "txval"),
    }

# =====================================================
# 3. RECONCILE MONTH (The Logic)
# =====================================================
def reconcile_month(year, month, token):
    headers = {
        "Authorization": token,
        "x-api-key": settings.SANDBOX_API_KEY,
        "x-api-version": "1.0.0"
    }

    auto = fetch_auto_liability(year, month, headers)
    filed = fetch_filed_3b(year, month, headers)

    if not auto or not filed:
        return None

    total_diff = (
        abs(auto["tx"] - filed["tx"]) +
        abs(auto["igst"] - filed["igst"]) +
        abs(auto["cgst"] - filed["cgst"]) +
        abs(auto["sgst"] - filed["sgst"]) +
        abs(auto["exp_tx"] - filed["exp_tx"]) +
        # abs(auto["rcm_tx"] - filed["rcm_tx"]) +
        abs(auto["nongst_tx"] - filed["nongst_tx"])
    )

    return {
        "year": year, "month": month,
        
        "auto_tx": auto["tx"], "g3_tx": filed["tx"],
        "auto_igst": auto["igst"], "g3_igst": filed["igst"],
        "auto_cgst": auto["cgst"], "g3_cgst": filed["cgst"],
        "auto_sgst": auto["sgst"], "g3_sgst": filed["sgst"],
        
        "auto_exp_tx": auto["exp_tx"], "g3_exp_tx": filed["exp_tx"],
        "auto_exp_igst": auto["exp_igst"], "g3_exp_igst": filed["exp_igst"],
        
        "auto_nil_tx": auto["nil_tx"], "g3_nil_tx": filed["nil_tx"],
        
        # "auto_rcm_tx": auto["rcm_tx"], "g3_rcm_tx": filed["rcm_tx"],
        # "auto_rcm_igst": auto["rcm_igst"], "g3_rcm_igst": filed["rcm_igst"],
        # "auto_rcm_cgst": auto["rcm_cgst"], "g3_rcm_cgst": filed["rcm_cgst"],
        # "auto_rcm_sgst": auto["rcm_sgst"], "g3_rcm_sgst": filed["rcm_sgst"],
        
        "auto_nongst_tx": auto["nongst_tx"], "g3_nongst_tx": filed["nongst_tx"],
        
        "status": "MATCH" if total_diff < 5.0 else "MISMATCH"
    }

# =====================================================
# 5. FULL YEAR RECONCILE ENDPOINT (Orchestrator)
# =====================================================
# In views.py

from datetime import datetime, date # Ensure these are imported
# ... other imports ...

# =====================================================
# RECONCILE ENDPOINT (With 10th of Month Cutoff)
# =====================================================
@api_view(["POST"])
@permission_classes([AllowAny])
def reconcile(request):
    try:
        fy_year = int(request.data.get("fy_year"))
        session_id = request.data.get("session_id")

        if not session_id:
            return Response({"error": "Session ID required"}, status=400)

        session = GSTSession.objects.filter(session_id=session_id).first()
        if not session or not session.taxpayer_token:
            return Response({"error": "Invalid session"}, status=400)

        # ---------------------------------------------------
        # 🗓️ DATE CUTOFF LOGIC
        # ---------------------------------------------------
        today = date.today()
        
        # If today is 1st-10th: Cutoff is 2 months ago (e.g., On Oct 5, show up to Aug)
        # If today is 11th+: Cutoff is 1 month ago (e.g., On Oct 15, show up to Sep)
        if today.day <= 10:
            # Go back ~60 days to land in the "Month before last"
            cutoff_date = (today.replace(day=1) - timedelta(days=45))
        else:
            # Go back ~20 days to land in the "Previous month"
            cutoff_date = (today.replace(day=1) - timedelta(days=15))
        
        # We only care about Year and Month for comparison
        cutoff_y, cutoff_m = cutoff_date.year, cutoff_date.month
        # ---------------------------------------------------

        months = [(fy_year, m) for m in range(4, 13)] + [(fy_year + 1, m) for m in range(1, 4)]
        results = []

        for y, m in months:
            # 🛑 STOP LOGIC: If the month (y, m) is after our cutoff, skip it
            # Logic: If Year is higher OR (Year is same AND Month is higher)
            if y > cutoff_y or (y == cutoff_y and m > cutoff_m):
                continue 

            res = reconcile_month(y, m, session.taxpayer_token)
            if res:
                results.append(res)
            else:
                # Add placeholder if no data found/fetched
                results.append({
                    "year": y, "month": m, "status": "NO DATA",
                    "auto_tx": 0, "g3_tx": 0, "auto_igst": 0, "g3_igst": 0,
                    "auto_cgst": 0, "g3_cgst": 0, "auto_sgst": 0, "g3_sgst": 0,
                    "auto_exp_tx": 0, "g3_exp_tx": 0, "auto_exp_igst": 0, "g3_exp_igst": 0,
                    "auto_nil_tx": 0, "g3_nil_tx": 0,
                    # "auto_rcm_tx": 0, "g3_rcm_tx": 0, "auto_rcm_igst": 0, "g3_rcm_igst": 0,
                    # "auto_rcm_cgst": 0, "g3_rcm_cgst": 0, "auto_rcm_sgst": 0, "g3_rcm_sgst": 0,
                    "auto_nongst_tx": 0, "g3_nongst_tx": 0,
                })

        # Safe Delete & Update
        ReconciliationReport.objects.filter(
            username=session.username, 
            gstin=session.gstin, 
            fy_year=fy_year
        ).delete()

        ReconciliationReport.objects.create(
            username=session.username,
            gstin=session.gstin,
            fy_year=fy_year,
            report_data=results
        )

        return Response({
            "message": "Reconciliation complete",
            "results": results
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e)}, status=500)


# =====================================================
# EXCEL DOWNLOAD (FIXED KEYS)
# =====================================================
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
    
    # --- Styles (Same as before) ---
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    month_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    month_font = Font(bold=True, color="FFFFFF", size=11)
    diff_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    match_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
    
    # --- Headers ---
    total_cols = len(results) * 4 + 1
    # Only merge if we actually have results, else default to 10
    total_cols = max(total_cols, 5) 

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
    ws['A1'] = "GSTR-3B Auto-Liability vs Filed GSTR-3B Reconciliation"
    ws['A1'].font = Font(bold=True, size=16, color="1F4E78")
    ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
    
    ws['A2'] = f"Username: {username} | GSTIN: {gstin} | FY: {fy_year}-{int(fy_year) + 1}"
    ws['A2'].font = Font(bold=True, size=11)
    
    ws['A4'] = "Particular"
    ws['A4'].fill = header_fill
    ws['A4'].font = header_font
    ws['A4'].border = border
    
    # --- Render Month Headers ---
    col = 2
    for data in results:
        month_name = calendar.month_abbr[data['month']] + " " + str(data['year'])
        ws.merge_cells(start_row=4, start_column=col, end_row=4, end_column=col+2)
        cell = ws.cell(4, col, month_name)
        cell.fill = month_fill
        cell.font = month_font
        cell.alignment = Alignment(horizontal='center')
        cell.border = border
        
        ws.cell(5, col, "GSTR-1").font = Font(bold=True, size=9)
        ws.cell(5, col+1, "Filed GSTR-3B").font = Font(bold=True, size=9)
        ws.cell(5, col+2, "Diff").font = Font(bold=True, size=9)
        col += 4
    
    # -----------------------------------------------------
    # 🛠️ FIXED KEY MAPPING (Using Frontend Keys)
    # -----------------------------------------------------
    # The frontend sends: tx1 (Auto), tx3 (Filed)
    # We map them here so Excel gets the correct values.
    particulars = [
        # 3.1.a Standard
        ('3.1.a Taxable Value', 'tx1', 'tx3'),
        ('3.1.a IGST', 'ig1', 'ig3'),
        ('3.1.a CGST', 'cg1', 'cg3'),
        ('3.1.a SGST', 'sg1', 'sg3'),
        
        # 3.1.b Exports
        ('3.1.b Export Taxable', 'exp_tx1', 'exp_tx3'),
        ('3.1.b Export IGST', 'exp_ig1', 'exp_ig3'),

        # 3.1.c Nil
        ('3.1.c Nil/Exempt', 'nil_tx1', 'nil_tx3'),

        # 3.1.d RCM
        # ('3.1.d RCM Taxable', 'rcm_tx1', 'rcm_tx3'),
        # ('3.1.d RCM IGST', 'rcm_ig1', 'rcm_ig3'),
        # ('3.1.d RCM CGST', 'rcm_cg1', 'rcm_cg3'),
        # ('3.1.d RCM SGST', 'rcm_sg1', 'rcm_sg3'),

        # 3.1.e Non-GST
        ('3.1.e Non-GST', 'ng1', 'ng3'),
    ]
    
    row = 6
    for particular, key_auto, key_filed in particulars:
        ws.cell(row, 1, particular).border = border
        col = 2
        for data in results:
            # Using the NEW keys (tx1, tx3) that match frontend
            auto_val = float(data.get(key_auto, 0) or 0)
            filed_val = float(data.get(key_filed, 0) or 0)
            diff = auto_val - filed_val
            
            c1 = ws.cell(row, col, round(auto_val, 2))
            c1.number_format = '#,##0.00'
            c1.border = border
            
            c2 = ws.cell(row, col+1, round(filed_val, 2))
            c2.number_format = '#,##0.00'
            c2.border = border
            
            c3 = ws.cell(row, col+2, round(diff, 2))
            c3.number_format = '#,##0.00'
            c3.border = border
            
            # Conditional Formatting
            if abs(diff) > 1:
                c3.fill = diff_fill
                c3.font = Font(bold=True, color="9C0006")
            else:
                c3.fill = match_fill
                c3.font = Font(color="006100")
            
            col += 4
        row += 1
    
    ws.column_dimensions['A'].width = 30

    # 2. INSERT THIS LOOP: Increase width for all data columns to 22
    for i in range(2, col):
        ws.column_dimensions[get_column_letter(i)].width = 22

    ws.freeze_panes = 'B6'
    
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = (
        f'attachment; filename="GSTR_3B_Reco_{gstin}_{fy_year}.xlsx"'
    )
    return response