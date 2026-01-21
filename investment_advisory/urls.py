from django.contrib import admin
from django.urls import path, include


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    # path('api/', include('gst_recon.urls')),
    path('api/', include('chat_api.urls')),
    path('api/bot/', include('bot.urls')),
    path('api/gst-reports/', include('gst_reports.urls')),
]

