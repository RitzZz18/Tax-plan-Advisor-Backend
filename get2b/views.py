import json
import os
import requests
from datetime import timedelta
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import GstAuth
from .utils import extract_gstr2b_data, generate_excel_bytes

BASE_URL = os.getenv("GST_BASE_URL")
API_KEY = os.getenv("GST_API_KEY")
INITIAL_AUTH = os.getenv("GST_AUTH_TOKEN")


def get_headers(access_token=None):
    headers = {
        "x-source": "primary",
        "x-api-version": "1.0.0",
        "x-api-key": API_KEY,
        "Content-Type": "application/json",
        "Authorization": access_token or INITIAL_AUTH,
    }
    return headers


# -----------------------------
# STEP 1: GENERATE OTP
# -----------------------------
@csrf_exempt
def generate_otp(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    username = data.get("username")
    gstin = data.get("gstin")

    if not username or not gstin:
        return JsonResponse({"error": "Username and GSTIN are required"}, status=400)

    url = f"{BASE_URL}/otp"
    payload = {"username": username, "gstin": gstin}

    try:
        response = requests.post(url, json=payload, headers=get_headers(), timeout=30)
        res_data = response.json()
    except requests.RequestException as e:
        return JsonResponse({"error": f"API request failed: {str(e)}"}, status=500)

    if response.status_code == 200 and res_data.get("data", {}).get("status_cd") == "1":
        auth = GstAuth.objects.create(
            username=username,
            gstin=gstin,
            transaction_id=res_data.get("transaction_id"),
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        return JsonResponse({
            "success": True,
            "request_id": str(auth.request_id)
        })

    error_msg = res_data.get("error", {}).get("message", "Failed to generate OTP")
    return JsonResponse({"success": False, "error": error_msg}, status=400)


# -----------------------------
# STEP 2: VERIFY OTP
# -----------------------------
@csrf_exempt
def verify_otp(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    request_id = data.get("request_id")
    otp = data.get("otp")

    if not request_id or not otp:
        return JsonResponse({"error": "Request ID and OTP are required"}, status=400)

    auth = GstAuth.objects.filter(request_id=request_id).first()
    if not auth or auth.is_expired():
        return JsonResponse({"error": "Invalid or expired request"}, status=401)

    url = f"{BASE_URL}/otp/verify?otp={otp}"
    payload = {
        "username": auth.username,
        "gstin": auth.gstin,
        "transaction_id": auth.transaction_id,
    }

    try:
        response = requests.post(url, json=payload, headers=get_headers(), timeout=30)
        res_data = response.json()
    except requests.RequestException as e:
        return JsonResponse({"error": f"API request failed: {str(e)}"}, status=500)

    if response.status_code == 200 and res_data.get("data", {}).get("status_cd") == "1":
        auth.access_token = res_data["data"]["access_token"]
        auth.expires_at = timezone.now() + timedelta(hours=6)
        auth.save()

        return JsonResponse({"success": True, "request_id": str(auth.request_id)})

    error_msg = res_data.get("error", {}).get("message", "OTP verification failed")
    return JsonResponse({"success": False, "error": error_msg}, status=400)


# -----------------------------
# STEP 3: DOWNLOAD GSTR-2B
# -----------------------------
@csrf_exempt
def download_gstr2b(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    request_id = data.get("request_id")

    if not request_id:
        return JsonResponse({"error": "Request ID is required"}, status=400)

    auth = GstAuth.objects.filter(request_id=request_id).first()
    if not auth or auth.is_expired():
        return JsonResponse({"error": "Unauthorized or session expired"}, status=401)

    # Check if monthly or quarterly
    month = data.get("month")
    year = data.get("year")
    fy_year = data.get("fy_year")
    quarter = data.get("quarter")

    all_b2b = []
    all_cdnr = []

    try:
        if month and year:
            # Monthly download
            url = f"{BASE_URL}/gstrs/gstr-2b/{year}/{month}"
            response = requests.get(url, headers=get_headers(auth.access_token), timeout=60)

            if response.status_code != 200:
                return JsonResponse({"error": "Failed to fetch GSTR-2B data"}, status=400)

            b2b, cdnr = extract_gstr2b_data(response.json(), f"{month}-{year}")
            all_b2b.extend(b2b)
            all_cdnr.extend(cdnr)

        elif fy_year and quarter:
            # Quarterly download - fetch 3 months
            quarter_months = {
                "Q1": ["04", "05", "06"],
                "Q2": ["07", "08", "09"],
                "Q3": ["10", "11", "12"],
                "Q4": ["01", "02", "03"]
            }

            if quarter not in quarter_months:
                return JsonResponse({"error": "Invalid quarter"}, status=400)

            # Parse FY year (e.g., "2024-2025")
            try:
                start_year, end_year = fy_year.split("-")
                start_year = int(start_year)
                end_year = int(end_year)
            except (ValueError, AttributeError):
                return JsonResponse({"error": "Invalid FY year format"}, status=400)

            months = quarter_months[quarter]

            # Determine which year each month belongs to
            for month in months:
                # Q4 months (Jan, Feb, Mar) belong to the second year of FY
                if month in ["01", "02", "03"]:
                    fetch_year = end_year
                else:
                    fetch_year = start_year

                url = f"{BASE_URL}/gstrs/gstr-2b/{fetch_year}/{month}"
                response = requests.get(url, headers=get_headers(auth.access_token), timeout=60)

                if response.status_code == 200:
                    b2b, cdnr = extract_gstr2b_data(response.json(), f"{month}-{fetch_year}")
                    all_b2b.extend(b2b)
                    all_cdnr.extend(cdnr)
                else:
                    # Log the failure but continue with other months
                    print(f"Failed to fetch data for {month}-{fetch_year}")

        else:
            return JsonResponse({"error": "Either month/year or fy_year/quarter required"}, status=400)

        # Generate Excel file
        excel = generate_excel_bytes(all_b2b, all_cdnr)

        filename = f"GSTR2B_{auth.gstin}"
        if month and year:
            filename += f"_{month}_{year}"
        elif fy_year and quarter:
            filename += f"_{fy_year}_{quarter}"
        filename += ".xlsx"

        res = HttpResponse(
            excel.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        res["Content-Disposition"] = f"attachment; filename={filename}"
        return res

    except requests.RequestException as e:
        return JsonResponse({"error": f"Failed to fetch GST data: {str(e)}"}, status=500)
    except Exception as e:
        return JsonResponse({"error": f"Server error: {str(e)}"}, status=500)
    
    
'''   
GST_API_KEY=
GST_AUTH_TOKEN=
GST_BASE_URL=https://api.sandbox.co.in/gst/compliance/tax-payer
DB_NAME=
DB_USER=
DB_PASSWORD=
DB_HOST=
DB_PORT=
'''