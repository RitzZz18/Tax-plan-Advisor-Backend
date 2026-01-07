from django.urls import path
from .views import DownloadGSTR1View

urlpatterns = [
    path('gstr1/download/', DownloadGSTR1View.as_view(), name='gstr1_download'),
]
