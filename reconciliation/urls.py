from django.urls import path
from .views import ReconcileView

urlpatterns = [
    path("reconcile/", ReconcileView.as_view(), name="reconcile"),
]
