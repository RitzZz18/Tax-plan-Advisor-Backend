from django.db import models
import uuid

class GSTSession(models.Model):
    session_id = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    username = models.CharField(max_length=255)
    gstin = models.CharField(max_length=15, db_index=True)
    access_token = models.TextField()
    taxpayer_token = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']

class ReconciliationReport(models.Model):
    username = models.CharField(max_length=255)
    gstin = models.CharField(max_length=15)
    fy_year = models.IntegerField()
    report_data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
