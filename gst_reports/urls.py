# gst_reports/urls.py

from django.urls import path
from gst_reports.views import reconciliation_views, download_views, cache_views, auth_views

urlpatterns = [
    # Auth
    path('auth/generate-otp/', auth_views.generate_otp, name='gst_generate_otp'),
    path('auth/verify-otp/', auth_views.verify_otp, name='gst_verify_otp'),
    path('auth/session-status/', auth_views.session_status, name='gst_session_status'),

    # Reconciliation
    path('reconcile/1vs3b/', reconciliation_views.reconcile_1_vs_3b, name='reconcile_1_vs_3b'),
    path('reconcile/1vsbooks/', reconciliation_views.reconcile_1_vs_books, name='reconcile_1_vs_books'),
    path('reconcile/3bvsbooks/', reconciliation_views.reconcile_3b_vs_books, name='reconcile_3b_vs_books'),
    path('reconcile/2bvsbooks/', reconciliation_views.reconcile_2b_vs_books, name='reconcile_2b_vs_books'),
    path('reconcile/2b-manual/', reconciliation_views.reconcile_2b_books_manual, name='reconcile_2b_manual'),
    path('reconcile/comprehensive/', reconciliation_views.reconcile_comprehensive_view, name='reconcile_comprehensive'),
    
    # Downloads
    path('download/gstr1/', download_views.download_gstr1, name='download_gstr1'),
    path('download/gstr2b/', download_views.download_gstr2b, name='download_gstr2b'),
    path('download/gstr3b/', download_views.download_gstr3b, name='download_gstr3b'),
    path('download/reco-1vs3b/', download_views.download_reco_1vs3b, name='download_reco_1vs3b'),
    path('download/reco-1vsbooks/', download_views.download_reco_1vsbooks, name='download_reco_1vsbooks'),
    path('download/reco-3bvsbooks/', download_views.download_reco_3bvsbooks, name='download_reco_3bvsbooks'),
    
    # Cache Management
    path('cache/clear/', cache_views.clear_gst_cache, name='clear_gst_cache'),
]
