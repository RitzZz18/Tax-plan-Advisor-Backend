from django.urls import path
from . import views

urlpatterns = [
    # GSTR-1 vs GSTR-3B Reconciliation (requires session_id from gst_auth)
    path('reconcile/', views.reconcile, name='gstr1vs3b_reconcile'),
    path('download-excel/', views.download_excel, name='gstr1vs3b_download'),
]
