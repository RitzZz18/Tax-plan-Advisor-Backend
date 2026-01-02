from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import FileResponse
from django.conf import settings

from .utils import generate_excel
from gst_auth.utils import get_valid_session

API_KEY = settings.SANDBOX_API_KEY


class DownloadGSTR1View(APIView):
    """
    Download GSTR-1 data as Excel.
    Uses unified session from gst_auth for authentication.
    """
    def post(self, request):
        session_id = request.data.get('session_id')
        type_val = request.data.get('type', 'month')
        year = request.data.get('year')
        month = request.data.get('month', '01')
        fy = request.data.get('fy')
        quarter = request.data.get('quarter')
        
        if not session_id:
            return Response({"error": "Session ID required"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate session using unified auth
        session, error = get_valid_session(session_id)
        if error:
            return Response({"error": error}, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            if type_val == 'month':
                download_type = 'monthly'
            elif type_val == 'quarter':
                download_type = 'quarterly'
            else:
                download_type = 'fy'
            
            excel_file, filename = generate_excel(
                gstin=session.gstin,
                api_key=API_KEY,
                access_token=session.taxpayer_token,
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
