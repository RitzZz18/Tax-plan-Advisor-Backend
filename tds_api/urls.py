"""
URL patterns for TDS API
"""

from django.urls import path
from .views import TDSSectionsView, BulkCalculateView, DownloadTemplateView, DownloadResultsView

urlpatterns = [
    path('sections/', TDSSectionsView.as_view(), name='tds-sections'),
    path('calculate/', BulkCalculateView.as_view(), name='bulk-calculate'),
    path('template/', DownloadTemplateView.as_view(), name='download-template'),
    path('download-results/', DownloadResultsView.as_view(), name='download-results'),
]
