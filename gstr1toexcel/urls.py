from django.urls import path
from .views import DownloadGSTR1View

urlpatterns = [
    # Download GSTR-1 (requires session_id from gst_auth)
    path('gstr1/download/', DownloadGSTR1View.as_view(), name='gstr1_download'),
]
