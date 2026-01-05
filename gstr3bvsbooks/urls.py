from django.urls import path
from . import views

urlpatterns = [
    # GSTR-3B vs Books Reconciliation (requires session_id from gst_auth)
    path('reconcile/', views.reconciliation, name='gstr3bvsbooks_reconcile'),
    path('download-excel/', views.download_excel, name='gstr3bvsbooks_download'),
]