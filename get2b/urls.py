# api/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Step 1: Request OTP
    path('generate-otp/', views.generate_otp, name='generate_otp'),
    
    # Step 2: Verify OTP & Store Token in Session
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    
    # Step 3: Fetch Data & Return Excel
    path('download-gstr2b/', views.download_gstr2b, name='download_gstr2b'),
]