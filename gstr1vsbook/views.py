from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status
from django.http import HttpResponse
from django.conf import settings
import pandas as pd
import io
import requests

from .models import GSTSession
from .serializers import GSTR1ReconciliationRequestSerializer
from .services import GSTR1ReconciliationService


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


class GSTR1GenerateOTPAPIView(APIView):
    """
    POST: Generate OTP for GST portal authentication.
    """
    
    def post(self, request, *args, **kwargs):
        username = request.data.get('username')
        gstin = request.data.get('gstin')
        
        if not username or not username.strip():
            return Response({"error": "Username required"}, status=400)
        
        if not gstin or len(gstin) != 15:
            return Response({"error": "GSTIN must be 15 characters"}, status=400)
        
        # Step 1 → Authenticate with Sandbox
        status_code, auth_data = safe_api_call(
            "POST",
            "https://api.sandbox.co.in/authenticate",
            headers={
                "x-api-key": settings.SANDBOX_API_KEY,
                "x-api-secret": settings.SANDBOX_API_SECRET
            }
        )
        
        if status_code != 200:
            return Response({
                "error": f"Authentication failed: {auth_data}"
            }, status=500)
        
        access_token = auth_data.get("access_token")
        if not access_token:
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
        
        # Step 3 → Save session to database
        gst_session = GSTSession.objects.create(
            username=username,
            gstin=gstin,
            access_token=access_token,
            is_verified=False
        )
        
        return Response({
            "success": True,
            "message": "OTP sent successfully",
            "session_id": str(gst_session.session_id)
        }, status=200)


class GSTR1VerifyOTPAPIView(APIView):
    """
    POST: Verify OTP for GST portal authentication.
    """
    
    def post(self, request, *args, **kwargs):
        otp = request.data.get('otp')
        session_id = request.data.get('session_id')
        
        if not otp or not otp.strip():
            return Response({"error": "OTP required"}, status=400)
        
        if not session_id:
            return Response({"error": "Session ID required"}, status=400)
        
        # Get session from database
        gst_session = GSTSession.get_valid_session(session_id)
        if not gst_session:
            return Response({"error": "Session expired or invalid"}, status=400)
        
        # Verify OTP with Sandbox API
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
            return Response({
                "error": data.get("message", "OTP verification failed")
            }, status=400)
        
        # Update session with taxpayer token
        gst_session.taxpayer_token = taxpayer_token
        gst_session.is_verified = True
        gst_session.save()
        
        return Response({
            "success": True,
            "message": "OTP verified successfully"
        }, status=200)


class GSTR1ReconciliationAPIView(APIView):
    """
    POST: Upload Excel file and get GSTR-1 reconciliation results.
    """
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request, *args, **kwargs):
        serializer = GSTR1ReconciliationRequestSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        file = data["file"]
        file_bytes = file.read()
        session_id = data.get("session_id")
        
        # Get session from database
        gst_session = GSTSession.get_valid_session(session_id)
        if not gst_session or not gst_session.is_verified:
            return Response({
                "success": False,
                "error": "Session not verified. Please complete OTP verification."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Initialize service with credentials from session
            service = GSTR1ReconciliationService(
                api_key=settings.SANDBOX_API_KEY,
                access_token=gst_session.taxpayer_token
            )
            
            results = service.run(
                file_bytes=file_bytes,
                session_id=str(session_id),
                reco_type=data["reco_type"],
                year=data["year"],
                month=data.get("month"),
                quarter=data.get("quarter")
            )
            
            # Convert DataFrames to JSON-serializable dicts
            response_data = {}
            for section, df in results.items():
                if df.empty:
                    response_data[section] = []
                else:
                    response_data[section] = df.to_dict(orient="records")
            
            return Response({
                "success": True,
                "data": response_data
            }, status=status.HTTP_200_OK)
        
        except ValueError as e:
            return Response({
                "success": False,
                "error": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            return Response({
                "success": False,
                "error": f"Internal error: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GSTR1ExcelDownloadAPIView(APIView):
    """
    POST: Download reconciliation results as Excel file.
    """
    
    def post(self, request, *args, **kwargs):
        try:
            data = request.data.get('results', {})
            username = request.data.get('username', 'User')
            gstin = request.data.get('gstin', '')
            year = request.data.get('year', '')
            
            # Create Excel file in memory
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                for section, records in data.items():
                    if records:
                        df = pd.DataFrame(records)
                        df.to_excel(writer, sheet_name=section[:31], index=False)
            
            output.seek(0)
            
            # Create HTTP response
            response = HttpResponse(
                output.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="GSTR1_Reconciliation_{gstin}_{year}.xlsx"'
            
            return response
            
        except Exception as e:
            return Response({
                "success": False,
                "error": f"Download failed: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)