import os
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from .models import UploadedFile, ReconciliationJob
from .serializers import UploadedFileSerializer, ReconciliationJobSerializer

from .recon_engine.parser import parse_file
from .tasks import run_reconciliation_async

class FileUploadViewSet(viewsets.ModelViewSet):
    queryset = UploadedFile.objects.all()
    serializer_class = UploadedFileSerializer
    parser_classes = (MultiPartParser, FormParser)

class ReconciliationViewSet(viewsets.ModelViewSet):
    queryset = ReconciliationJob.objects.all()
    serializer_class = ReconciliationJobSerializer

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        job = self.get_object()
        try:
            run_reconciliation_async(job.id)
            return Response({"status": "started"}, status=status.HTTP_202_ACCEPTED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'])
    def result(self, request, pk=None):
        job = self.get_object()
        return Response({"status": job.status, "result": job.result, "error_message": job.error_message}, status=status.HTTP_200_OK)
