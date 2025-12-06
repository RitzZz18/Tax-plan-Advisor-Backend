from django.urls import path
from .views import ChatbotView,OnboardingView  # <-- Import OnboardingView

urlpatterns = [
    # Registration/Login endpoint
    path('onboard/', OnboardingView.as_view(), name='onboard'),

    # Chat endpoint
    path('chat/', ChatbotView.as_view(), name='chat'),
    
    # Clear history endpoint
    #path('chat/clear/', ClearChatView.as_view(), name='clear_chat'),
]