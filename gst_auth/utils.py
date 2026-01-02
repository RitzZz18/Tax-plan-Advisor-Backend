import requests
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from .models import UnifiedGSTSession, SandboxAccessToken


def safe_api_call(method, url, **kwargs):
    """Unified request handler for Sandbox API calls."""
    try:
        kwargs["timeout"] = kwargs.get("timeout", 20)
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


def get_sandbox_access_token():
    """
    Returns a valid Sandbox access token.
    Flow:
    1. Check DB for existing valid token → return if valid
    2. If expired/missing → fetch new token from Sandbox API
    3. Save new token to DB with 23hr expiry (1hr buffer before 24hr actual expiry)
    4. Return new token
    """
    
    # Step 1: Check for existing valid token in DB
    existing = SandboxAccessToken.objects.first()
    
    if existing and existing.is_valid():
        return existing.token, None  # ✅ Use cached token
    
    # Step 2: Token expired or doesn't exist → Fetch new one
    status_code, auth_data = safe_api_call(
        "POST",
        "https://api.sandbox.co.in/authenticate",
        headers={
            "x-api-key": settings.SANDBOX_API_KEY,
            "x-api-secret": settings.SANDBOX_API_SECRET
        }
    )
    
    if status_code != 200:
        return None, "Failed to authenticate with Sandbox API"
    
    access_token = auth_data.get("data", {}).get("access_token")
    if not access_token:
        return None, "Invalid token from Sandbox API"
    
    # Step 3: Save new token to DB (replace old one)
    SandboxAccessToken.objects.all().delete()  # Remove expired token
    SandboxAccessToken.objects.create(
        token=access_token,
        expires_at=timezone.now() + timedelta(hours=23)  # 23hr buffer before 24hr expiry
    )
    
    # Step 4: Return new token
    return access_token, None


def get_gst_headers(access_token):
    """Get headers for GST API calls."""
    return {
        "x-source": "primary",
        "x-api-version": "1.0.0",
        "Authorization": access_token,
        "x-api-key": settings.SANDBOX_API_KEY,
        "Content-Type": "application/json"
    }


def get_valid_session(session_id):
    """
    Get a valid, verified session by session_id.
    Returns (session, error_message) tuple.
    This is the main utility for other apps to validate sessions.
    """
    try:
        session = UnifiedGSTSession.objects.get(session_id=session_id)
    except UnifiedGSTSession.DoesNotExist:
        return None, "Session not found"
    
    if session.is_expired():
        return None, "Session expired"
    
    if not session.is_verified:
        return None, "Session not verified - please complete OTP verification"
    
    if not session.taxpayer_token:
        return None, "Invalid session - missing taxpayer token"
    
    return session, None


def cleanup_expired_sessions():
    """Remove expired sessions from database."""
    deleted_count, _ = UnifiedGSTSession.objects.filter(
        expires_at__lt=timezone.now()
    ).delete()
    return deleted_count


def cleanup_expired_sandbox_tokens():
    """Remove expired sandbox tokens from database."""
    deleted_count, _ = SandboxAccessToken.objects.filter(
        expires_at__lt=timezone.now()
    ).delete()
    return deleted_count
