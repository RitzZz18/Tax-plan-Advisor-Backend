from django.urls import path
from .views import (
    GSTR1GenerateOTPAPIView,
    GSTR1VerifyOTPAPIView,
    GSTR1ReconciliationAPIView,
    GSTR1ExcelDownloadAPIView
)

urlpatterns = [
    path('generate-otp/', GSTR1GenerateOTPAPIView.as_view(), name='gstr1-generate-otp'),
    path('verify-otp/', GSTR1VerifyOTPAPIView.as_view(), name='gstr1-verify-otp'),
    path('reconcile/', GSTR1ReconciliationAPIView.as_view(), name='gstr1-reconciliation'),
    path('download-excel/', GSTR1ExcelDownloadAPIView.as_view(), name='gstr1-download-excel'),
]