import json
import os
import requests
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from .utils import extract_gstr2b_data, generate_excel_bytes

# Import unified session utilities
from gst_auth.utils import get_valid_session, get_gst_headers

BASE_URL = os.getenv("GST_BASE_URL", "https://api.sandbox.co.in/gst/compliance/tax-payer")


# -----------------------------
# DOWNLOAD GSTR-2B (Uses unified session)
# -----------------------------
@csrf_exempt
def download_gstr2b(request):
    """
    Download GSTR-2B data as Excel.
    Requires a valid session_id from the unified gst_auth module.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    session_id = data.get("session_id")

    if not session_id:
        return JsonResponse({"error": "Session ID is required"}, status=400)

    # Validate session using unified auth
    session, error = get_valid_session(session_id)
    if error:
        return JsonResponse({"error": error}, status=401)

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
            response = requests.get(url, headers=get_gst_headers(session.taxpayer_token), timeout=60)

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
                response = requests.get(url, headers=get_gst_headers(session.taxpayer_token), timeout=60)

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

        filename = f"GSTR2B_{session.gstin}"
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