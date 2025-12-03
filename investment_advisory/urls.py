from django.contrib import admin
from django.urls import path, include


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    path('api/', include('gst_recon.urls')),
    path('chatbot/', include('chat_api.urls')),
    path('api/gstr/', include('gstr1vs3b.urls')),
]
