import uuid
from django.db import models
from django.utils import timezone
from datetime import timedelta


class UnifiedGSTSession(models.Model):
    """
    Unified session model for all GST services.
    Stores authentication state after OTP verification.
    """
    session_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=100)
    gstin = models.CharField(max_length=15)
    
    # Tokens from Sandbox API
    access_token = models.TextField(blank=True, null=True, help_text="Initial sandbox access token")
    taxpayer_token = models.TextField(blank=True, null=True, help_text="Token after OTP verification")
    transaction_id = models.CharField(max_length=255, blank=True, null=True)
    
    # Session state
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()
    
    class Meta:
        db_table = 'unified_gst_session'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['session_id']),
            models.Index(fields=['gstin', 'is_verified']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.expires_at:
            # Default expiry: 6 hours from creation
            self.expires_at = timezone.now() + timedelta(hours=6)
        super().save(*args, **kwargs)
    
    def is_expired(self):
        return timezone.now() > self.expires_at
    
    def is_valid(self):
        return self.is_verified and not self.is_expired() and self.taxpayer_token
    
    def __str__(self):
        return f"{self.gstin} - {self.username} ({'verified' if self.is_verified else 'pending'})"


class SandboxAccessToken(models.Model):
    """
    Stores the Sandbox API access token with expiry.
    Only ONE active token should exist at a time.
    Token is valid for 24 hours from Sandbox API.
    """
    token = models.TextField(help_text="Sandbox API access token")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(help_text="Token expiry time (24 hours from creation)")
    
    class Meta:
        db_table = 'sandbox_access_token'
    
    def is_expired(self):
        """Check if token has expired."""
        return timezone.now() > self.expires_at
    
    def is_valid(self):
        """Check if token is still valid."""
        return not self.is_expired()
    
    def __str__(self):
        status = "valid" if self.is_valid() else "expired"
        return f"Sandbox Token ({status}) - expires {self.expires_at}"

