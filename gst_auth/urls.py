from django.urls import path
from . import views

urlpatterns = [
    path('generate-otp/', views.generate_otp, name='gst_auth_generate_otp'),
    path('verify-otp/', views.verify_otp, name='gst_auth_verify_otp'),
    # path('session-status/', views.session_status, name='gst_auth_session_status'),
]
