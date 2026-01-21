import uuid
from datetime import timedelta
from django.db import models
from django.utils import timezone

class GSTReport(models.Model):
    """
    Unified model to store all types of GST reconciliation reports.
    """
    REPORT_TYPES = (
        ('GSTR1_VS_3B', 'GSTR-1 vs GSTR-3B'),
        ('GSTR1_VS_BOOK', 'GSTR-1 vs Books'),
        ('GSTR3B_VS_BOOK', 'GSTR-3B vs Books'),
        ('GSTR2B_VS_BOOK', 'GSTR-2B vs Books'),
        ('GSTR1_3B_2B_COMPREHENSIVE', 'GSTR-1 vs 3B vs 2B Comprehensive'),
    )
    
    report_type = models.CharField(max_length=50, choices=REPORT_TYPES, db_index=True)
    username = models.CharField(max_length=255)
    gstin = models.CharField(max_length=15, db_index=True)
    reco_type = models.CharField(max_length=20, null=True, blank=True) # MONTHLY, QUARTERLY, FY
    year = models.IntegerField(db_index=True)
    month = models.IntegerField(null=True, blank=True, db_index=True)
    quarter = models.CharField(max_length=5, null=True, blank=True, db_index=True)
    
    report_data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'gst_unified_reports'
        ordering = ['-created_at']
        verbose_name = "GST Unified Report"
        verbose_name_plural = "GST Unified Reports"

    def __str__(self):
        period = f"{self.month}/{self.year}" if self.month else (self.quarter or f"FY {self.year}")
        return f"{self.gstin} - {self.report_type} ({period})"


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


class CachedGSTResponse(models.Model):
    """
    Stores raw API responses from Sandbox GST API.
    Used to avoid redundant API calls for the same GSTIN/period/return_type.
    """
    gstin = models.CharField(max_length=15, db_index=True)
    return_type = models.CharField(
        max_length=20, 
        db_index=True,
        help_text="e.g., GSTR1, GSTR3B, GSTR2B"
    )
    section = models.CharField(
        max_length=50, 
        blank=True, 
        default="",
        help_text="e.g., b2b, summary, auto-liability-calc"
    )
    year = models.IntegerField(db_index=True)
    month = models.IntegerField(db_index=True)
    
    raw_json = models.JSONField(help_text="Raw API response from Sandbox")
    
    fetched_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'cached_gst_responses'
        unique_together = ('gstin', 'return_type', 'section', 'year', 'month')
        ordering = ['-fetched_at']
        indexes = [
            models.Index(fields=['gstin', 'return_type', 'year', 'month']),
        ]
    
    def __str__(self):
        return f"{self.gstin} | {self.return_type}/{self.section} | {self.month:02d}-{self.year}"
