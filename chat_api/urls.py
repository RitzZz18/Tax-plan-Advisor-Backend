from django.urls import path
from .views import ChatbotView,ClearChatView
urlpatterns = [
    # This creates an endpoint at /api/chat/
    path('chat/', ChatbotView.as_view(), name='chat'),
    path("chat/clear/", ClearChatView.as_view()),

]