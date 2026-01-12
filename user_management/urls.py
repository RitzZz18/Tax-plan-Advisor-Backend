from django.urls import path
from .views import (
    LoginView, 
    ConsultantSignupView, 
    ConsultantClientListView,
    ConsultantClientDetailView,
    ClientDashboardView
)

urlpatterns = [
    # Auth
    path('login/', LoginView.as_view(), name='saas_login'),
    path('consultant/register/', ConsultantSignupView.as_view(), name='consultant_register'),
    
    # Consultant Dashboard
    path('consultant/clients/', ConsultantClientListView.as_view(), name='consultant_client_list'),
    path('consultant/client/<int:client_id>/dashboard/', ConsultantClientDetailView.as_view(), name='consultant_client_detail'),
    
    # Client Dashboard
    path('client/dashboard/', ClientDashboardView.as_view(), name='client_dashboard'),
]
