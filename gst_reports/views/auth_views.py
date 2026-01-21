from datetime import timedelta
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from gst_reports.models import UnifiedGSTSession
from gst_reports.utils import safe_api_call, get_sandbox_access_token, get_gst_headers, cleanup_expired_sessions


@api_view(['POST'])
@permission_classes([AllowAny])
def generate_otp(request):
    """Step 1: Generate OTP for GST authentication."""
    username = request.data.get("username", "").strip()
    gstin = request.data.get("gstin", "").strip().upper()
    
    if not username:
        return Response({"error": "Username is required"}, status=400)
    
    if not gstin or len(gstin) != 15:
        return Response({"error": "Valid 15-character GSTIN is required"}, status=400)
    
    access_token, error = get_sandbox_access_token()
    if error:
        return Response({"error": error}, status=500)
    
    status_code, otp_data = safe_api_call(
        "POST",
        "https://api.sandbox.co.in/gst/compliance/tax-payer/otp",
        json={"username": username, "gstin": gstin},
        headers=get_gst_headers(access_token)
    )
    
    data = otp_data.get("data", {})
    if data.get("status_cd") == "0":
        return Response({
            "error": data.get("message", "Failed to send OTP"),
            "error_code": data.get("error", {}).get("error_cd", "")
        }, status=400)
    
    session = UnifiedGSTSession.objects.create(
        username=username,
        gstin=gstin,
        access_token=access_token,
        transaction_id=otp_data.get("transaction_id", ""),
        expires_at=timezone.now() + timedelta(minutes=10) 
    )
    cleanup_expired_sessions()
    
    return Response({
        "success": True,
        "message": "OTP sent successfully",
        "session_id": str(session.session_id)
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_otp(request):
    """Step 2: Verify OTP and activate session."""
    session_id = request.data.get("session_id")
    otp = request.data.get("otp", "").strip()
    
    if not session_id:
        return Response({"error": "Session ID is required"}, status=400)
    if not otp:
        return Response({"error": "OTP is required"}, status=400)
    
    try:
        session = UnifiedGSTSession.objects.get(session_id=session_id)
    except UnifiedGSTSession.DoesNotExist:
        return Response({"error": "Invalid session"}, status=400)
    
    if session.is_expired():
        return Response({"error": "Session expired - please request new OTP"}, status=400)
    
    if session.is_verified:
        return Response({
            "success": True,
            "message": "Session already verified",
            "session_id": str(session.session_id)
        })
    
    status_code, verify_data = safe_api_call(
        "POST",
        "https://api.sandbox.co.in/gst/compliance/tax-payer/otp/verify",
        json={"username": session.username, "gstin": session.gstin},
        params={"otp": otp},
        headers=get_gst_headers(session.access_token)
    )
    
    data = verify_data.get("data", {})
    taxpayer_token = data.get("access_token")
    
    if data.get("status_cd") == "0" or not taxpayer_token:
        error_msg = data.get("message", verify_data.get("error", {}).get("message", "OTP verification failed"))
        return Response({"error": error_msg}, status=400)
    
    session.taxpayer_token = taxpayer_token
    session.is_verified = True
    session.expires_at = timezone.now() + timedelta(hours=6)  
    session.save(update_fields=["taxpayer_token", "is_verified", "expires_at", "updated_at"])
    
    return Response({
        "success": True,
        "message": "OTP verified successfully",
        "session_id": str(session.session_id),
        "gstin": session.gstin,
        "username": session.username
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def session_status(request):
    """Check if a session is valid and get remaining time."""
    session_id = request.query_params.get("session_id") 
    if not session_id:
        return Response({"error": "Session ID is required"}, status=400)
    
    try:
        session = UnifiedGSTSession.objects.get(session_id=session_id)
    except UnifiedGSTSession.DoesNotExist:
        return Response({"is_valid": False, "error": "Session not found"})
    
    if session.is_expired():
        return Response({"is_valid": False, "error": "Session expired"})
    
    remaining_seconds = (session.expires_at - timezone.now()).total_seconds()
    return Response({
        "is_valid": session.is_valid(),
        "is_verified": session.is_verified,
        "gstin": session.gstin,
        "username": session.username,
        "expires_in_seconds": int(remaining_seconds),
        "expires_in_minutes": int(remaining_seconds / 60)
    })
