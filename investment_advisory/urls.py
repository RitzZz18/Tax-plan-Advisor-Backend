from django.contrib import admin
from django.urls import path, include
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(
   openapi.Info(
      title="TaxPlan Advisor API",
      default_version='v1',
      description="API documentation for TaxPlan Advisor Consultant & Client Dashboards",
      terms_of_service="https://www.google.com/policies/terms/",
      contact=openapi.Contact(email="contact@taxplanadvisor.in"),
      license=openapi.License(name="BSD License"),
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
)


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
    
    # Swagger
    path('swagger<format>/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    
    # Auth
    path('api/auth/', include('user_management.urls')),
]
