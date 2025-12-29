import json
import os
import requests
from datetime import timedelta
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import FileResponse
from .models import GstAuth
from .serializers import GSTR1DownloadSerializer
from .utils import generate_excel
from django.conf import settings

BASE_URL = "https://api.sandbox.co.in/gst/compliance/tax-payer"
API_KEY = settings.SANDBOX_API_KEY
API_SECRET = settings.SANDBOX_API_SECRET

def get_headers(access_token=None):
    headers = {
        "x-source": "primary",
        "x-api-version": "1.0.0",
        "x-api-key": API_KEY,
        "Content-Type": "application/json",
    }
    if access_token:
        headers["Authorization"] = access_token
    return headers

class SendOTPView(APIView):
    def post(self, request):
        username = request.data.get('username')
        gstin = request.data.get('gstin')
        
        if not username or not gstin:
            return Response({"error": "Username and GSTIN required"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Step 1: Get access token
        try:
            auth_response = requests.post(
                "https://api.sandbox.co.in/authenticate",
                headers={"x-api-key": API_KEY, "x-api-secret": API_SECRET},
                timeout=30
            )
            auth_data = auth_response.json()
            access_token = auth_data.get("data", {}).get("access_token")
            
            if not access_token:
                return Response({"error": "Failed to authenticate"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({"error": "Authentication failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Step 2: Send OTP
        try:
            otp_response = requests.post(
                f"{BASE_URL}/otp",
                json={"username": username, "gstin": gstin},
                headers=get_headers(access_token),
                timeout=30
            )
            otp_data = otp_response.json()
        except Exception as e:
            return Response({"error": "Failed to send OTP"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        if otp_response.status_code == 200 and otp_data.get("data", {}).get("status_cd") == "1":
            auth = GstAuth.objects.create(
                username=username,
                gstin=gstin,
                transaction_id=otp_data.get("transaction_id"),
                access_token=access_token,
                expires_at=timezone.now() + timedelta(minutes=10),
            )
            return Response({
                "message": "OTP sent successfully",
                "request_id": str(auth.request_id)
            })
        
        error_msg = otp_data.get("error", {}).get("message", "Failed to send OTP")
        return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)

class VerifyOTPView(APIView):
    def post(self, request):
        request_id = request.data.get('request_id')
        otp = request.data.get('otp')
        
        if not request_id or not otp:
            return Response({"error": "Request ID and OTP required"}, status=status.HTTP_400_BAD_REQUEST)
        
        auth = GstAuth.objects.filter(request_id=request_id).first()
        if not auth or auth.is_expired():
            return Response({"error": "Invalid or expired request"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            verify_response = requests.post(
                f"{BASE_URL}/otp/verify?otp={otp}",
                json={
                    "username": auth.username,
                    "gstin": auth.gstin,
                    "transaction_id": auth.transaction_id,
                },
                headers=get_headers(auth.access_token),
                timeout=30
            )
            verify_data = verify_response.json()
        except Exception as e:
            return Response({"error": "OTP verification failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        if verify_response.status_code == 200 and verify_data.get("data", {}).get("status_cd") == "1":
            auth.access_token = verify_data["data"]["access_token"]
            auth.expires_at = timezone.now() + timedelta(hours=6)
            auth.save()
            return Response({
                "message": "OTP verified successfully",
                "request_id": str(auth.request_id)
            })
        
        error_msg = verify_data.get("error", {}).get("message", "OTP verification failed")
        return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)

class DownloadGSTR1View(APIView):
    def post(self, request):
        request_id = request.data.get('request_id')
        type_val = request.data.get('type', 'month')
        year = request.data.get('year')
        month = request.data.get('month', '01')
        fy = request.data.get('fy')
        quarter = request.data.get('quarter')
        
        if not request_id:
            return Response({"error": "Request ID required"}, status=status.HTTP_400_BAD_REQUEST)
        
        auth = GstAuth.objects.filter(request_id=request_id).first()
        if not auth or auth.is_expired():
            return Response({"error": "Unauthorized or session expired"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            if type_val == 'month':
                download_type = 'monthly'
            elif type_val == 'quarter':
                download_type = 'quarterly'
            else:
                download_type = 'fy'
            
            excel_file, filename = generate_excel(
                gstin=auth.gstin,
                api_key=API_KEY,
                access_token=auth.access_token,
                download_type=download_type,
                fy=fy,
                quarter=quarter,
                year=year,
                month=month
            )
            
            response = FileResponse(
                excel_file,
                as_attachment=True,
                filename=filename,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            return response
            
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class GSTR1DownloadView(APIView):
    def post(self, request):
        serializer = GSTR1DownloadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        
        try:
            excel_file, filename = generate_excel(
                gstin=data['gstin'],
                api_key=data['api_key'],
                access_token=data['access_token'],
                download_type=data['download_type'],
                fy=data.get('fy'),
                quarter=data.get('quarter'),
                year=data.get('year'),
                month=data.get('month')
            )
            
            response = FileResponse(
                excel_file,
                as_attachment=True,
                filename=filename,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            return response
            
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
