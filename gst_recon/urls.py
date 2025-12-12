from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import FileUploadViewSet, ReconciliationViewSet

router = DefaultRouter()
router.register("uploadedfiles", FileUploadViewSet, basename="uploadedfile")
router.register("reconciliationjobs", ReconciliationViewSet, basename="reconciliationjob")

urlpatterns = [
    path("", include(router.urls)),
]
