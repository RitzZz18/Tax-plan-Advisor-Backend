from django.urls import path
from .views import (
    GSTR1ReconciliationAPIView,
    GSTR1ExcelDownloadAPIView
)

urlpatterns = [
    # Reconciliation endpoints (authentication via gst_auth session)
    path('reconcile/', GSTR1ReconciliationAPIView.as_view(), name='gstr1-reconciliation'),
    path('download-excel/', GSTR1ExcelDownloadAPIView.as_view(), name='gstr1-download-excel'),
]