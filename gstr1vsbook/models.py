from django.db import models
import uuid
from datetime import timedelta
from django.utils import timezone


class GSTSession(models.Model):
    """
    Model to store GST API session data.
    Used for OTP flow and API authentication.
    """
    session_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    
    # User credentials
    username = models.CharField(max_length=100)
    gstin = models.CharField(max_length=15)
    
    # Sandbox API tokens
    access_token = models.TextField(blank=True, null=True, help_text="Sandbox auth token")
    taxpayer_token = models.TextField(blank=True, null=True, help_text="Token after OTP verification")
    
    # Status
    is_verified = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "GST Session"
        verbose_name_plural = "GST Sessions"
    
    def __str__(self):
        return f"{self.gstin} - {self.session_id}"
    
    def save(self, *args, **kwargs):
        # Set default expiry to 6 hours from creation
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=6)
        super().save(*args, **kwargs)
    
    @property
    def is_expired(self):
        return timezone.now() > self.expires_at if self.expires_at else True
    
    @classmethod
    def get_valid_session(cls, session_id):
        """Get a valid (non-expired) session by session_id"""
        try:
            session = cls.objects.get(session_id=session_id)
            if session.is_expired:
                return None
            return session
        except cls.DoesNotExist:
            return None
