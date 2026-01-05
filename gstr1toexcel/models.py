import uuid
from django.db import models
from django.utils import timezone

class GstAuth(models.Model):
    request_id = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False
    )
    gstin = models.CharField(max_length=15)
    username = models.CharField(max_length=100)
    transaction_id = models.CharField(max_length=200, null=True, blank=True)
    access_token = models.TextField(null=True, blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"{self.gstin} - {self.request_id}"
