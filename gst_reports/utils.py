import requests
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from gst_reports.models import UnifiedGSTSession, SandboxAccessToken


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
    """Returns a valid Sandbox access token."""
    existing = SandboxAccessToken.objects.first()
    
    if existing and existing.is_valid():
        return existing.token, None  
    
    status_code, auth_data = safe_api_call(
        "POST",
        "https://api.sandbox.co.in/authenticate",
        headers={
            "x-api-key": settings.SANDBOX_API_KEY,
            "x-api-secret": settings.SANDBOX_API_SECRET
        }
    )
    
    if status_code != 200:
        error_msg = auth_data.get("error", {}).get("message", "") or auth_data.get("message", "") or str(auth_data)
        return None, f"Failed to authenticate with Sandbox API: {status_code} - {error_msg}"
    
    access_token = auth_data.get("access_token") or auth_data.get("data", {}).get("access_token")
    if not access_token:
        return None, f"Invalid token from Sandbox API: {auth_data}"
    
    SandboxAccessToken.objects.all().delete()
    SandboxAccessToken.objects.create(
        token=access_token,
        expires_at=timezone.now() + timedelta(hours=23)
    )
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
    """Get a valid, verified session by session_id."""
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


def unwrap_sandbox_data(data):
    """
    Recursively unwraps 'data' keys from Sandbox API response 
    until it hits the actual payload.
    """
    if not isinstance(data, dict):
        return data

    if "data" in data and isinstance(data["data"], (dict, list)):
        # If it's a list, we return it as the payload
        if isinstance(data["data"], list):
            return data["data"]
            
        # If it's a dict, check if it's a wrapper by seeing if there are other substantial keys
        meta_keys = {
            "code", "message", "status", "data", "ret_period", "gstin", 
            "timestamp", "transaction_id", "status_cd", "status_desc"
        }
        other_keys = set(data.keys()) - meta_keys
        
        # If no other substantial keys are present, OR if 'data' contains the bulk, unwrap one more level
        if not other_keys:
            return unwrap_sandbox_data(data["data"])
            
    return data
