from django.urls import path
from .views import ChatbotView, ClearChatView, SaveUserContactView, GetUserContactsView

urlpatterns = [
    path('chat/', ChatbotView.as_view(), name='chat'),
    path('chat/clear/', ClearChatView.as_view()),
    path('save-contact/', SaveUserContactView.as_view()),
    path('contacts/', GetUserContactsView.as_view()),
]