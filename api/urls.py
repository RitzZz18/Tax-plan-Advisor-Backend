from django.urls import path
from .views import save_inquiry
from . import views

urlpatterns = [
    path('health/', views.health_check, name='health_check'),
    path('investment-plan/', views.generate_investment_plan, name='generate_investment_plan'),
    path('regenerate-allocation/', views.regenerate_allocation, name='regenerate_allocation'),
    # path('chat/', views.chat_with_ai, name='chat_with_ai'),
    # path('chat/clear/', views.clear_chat, name='clear_chat'),
    # backend/api/urls.py
    path('dubai-inquiry/', save_inquiry),
]
