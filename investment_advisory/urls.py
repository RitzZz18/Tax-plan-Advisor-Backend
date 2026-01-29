from django.contrib import admin
from django.urls import path, include


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    # path('api/', include('gst_recon.urls')),
    path('api/', include('chat_api.urls')),
    path('api/gst-auth/', include('gst_auth.urls')),
    path('api/gstr/', include('gstr1vs3b.urls')),
    path('api/gstr3b/', include('gstr3bvsbooks.urls')),
    path('api/bot/', include('bot.urls')),
    path('api/', include('reconciliation.urls')),
    path('api/get2b/', include('get2b.urls')),
    path('api/', include('gstr1toexcel.urls')),
    path('api/gstr1vsbook/', include('gstr1vsbook.urls')),
    path('api/calculator/', include('calculator.urls')),
    path('api/tds/', include('tds_api.urls')),
]
