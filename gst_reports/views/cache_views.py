# gst_reports/views/cache_views.py

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from gst_reports.models import CachedGSTResponse
from gst_reports.utils import get_valid_session

@api_view(["POST"])
@permission_classes([AllowAny])
def clear_gst_cache(request):
    """
    Clear all cached responses for a specific GSTIN.
    Requires a valid session for authorization.
    """
    session_id = request.data.get("session_id")
    gstin = request.data.get("gstin")

    if not session_id or not gstin:
        return Response({"error": "Session ID and GSTIN are required"}, status=400)

    session, error = get_valid_session(session_id)
    if error:
        return Response({"error": error}, status=401)

    # For safety, ensure user is clearing cache for the GSTIN they are logged in with
    # Unless they are a superuser (optional check)
    if session.gstin != gstin:
        return Response({"error": "Unauthorized to clear cache for this GSTIN"}, status=403)

    deleted_count, _ = CachedGSTResponse.objects.filter(gstin=gstin).delete()

    return Response({
        "status": "success",
        "message": f"Cleared {deleted_count} cached records for GSTIN {gstin}",
        "gstin": gstin
    })
