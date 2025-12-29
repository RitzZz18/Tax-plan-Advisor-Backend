from django.urls import path
from .views import GSTR1DownloadView, SendOTPView, VerifyOTPView, DownloadGSTR1View

urlpatterns = [
    path('download-excel/', GSTR1DownloadView.as_view(), name='gstr1-download'),
    path('send-otp/', SendOTPView.as_view(), name='send-otp'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('download-gstr1/', DownloadGSTR1View.as_view(), name='download-gstr1'),
]
