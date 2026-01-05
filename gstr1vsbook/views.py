from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status
from django.http import HttpResponse
from django.conf import settings
import pandas as pd
import io

from .serializers import GSTR1ReconciliationRequestSerializer
from .services import GSTR1ReconciliationService
from gst_auth.utils import get_valid_session


class GSTR1ReconciliationAPIView(APIView):
    """
    POST: Upload Excel file and get GSTR-1 reconciliation results.
    Uses unified session from gst_auth for authentication.
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
        
        # Validate session using unified auth from gst_auth
        session, error = get_valid_session(session_id)
        if error:
            return Response({
                "success": False,
                "error": error
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            # Initialize service with credentials from session
            service = GSTR1ReconciliationService(
                api_key=settings.SANDBOX_API_KEY,
                access_token=session.taxpayer_token
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