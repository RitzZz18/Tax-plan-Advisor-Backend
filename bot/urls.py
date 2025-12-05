from django.urls import path
from . import views

urlpatterns = [
    path('save-lead/', views.save_lead, name='save_lead'),
    path('send-query/', views.send_query, name='send_query'),
]