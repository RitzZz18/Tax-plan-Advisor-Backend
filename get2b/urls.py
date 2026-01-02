# get2b/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Download GSTR-2B (requires session_id from gst_auth)
    path('download-gstr2b/', views.download_gstr2b, name='get2b_download'),
]