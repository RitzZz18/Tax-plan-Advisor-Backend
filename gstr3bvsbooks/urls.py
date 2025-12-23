from django.urls import path
from . import views

urlpatterns = [
    path('generate-otp/', views.generate_otp, name='gstr3b_generate_otp'),
    path('verify-otp/', views.verify_otp, name='gstr3b_verify_otp'),
    path('reconcile/', views.reconciliation, name='gstr3b_reconcile'),
    path('download-excel/', views.download_excel, name='gstr3b_download_excel'),
]