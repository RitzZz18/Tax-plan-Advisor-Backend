from django.urls import path
from . import views

urlpatterns = [
    path('generate-otp/', views.generate_otp),
    path('verify-otp/', views.verify_otp),
    path('reconcile/', views.reconcile),
    # path('reconcile-test/', views.reconcile_test),
    path('download-excel/', views.download_excel),
]
