from django.urls import path
from . import views

urlpatterns = [
    path('generate-otp/', views.generate_otp),
    path('verify-otp/', views.verify_otp),
    path('reconcile/', views.reconcile),
]
