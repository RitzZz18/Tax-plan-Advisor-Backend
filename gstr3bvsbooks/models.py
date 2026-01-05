import uuid
from django.db import models
from django.utils import timezone


class GSTSession(models.Model):
    session_id = models.UUIDField(unique=True, default=uuid.uuid4)
    username = models.CharField(max_length=100)
    gstin = models.CharField(max_length=15)
    access_token = models.TextField()
    taxpayer_token = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'gst_sessions_3b'


class ReconciliationReport(models.Model):
    username = models.CharField(max_length=100)
    gstin = models.CharField(max_length=15)
    reco_type = models.CharField(max_length=20)
    year = models.IntegerField()
    month = models.IntegerField(null=True, blank=True)
    quarter = models.CharField(max_length=5, null=True, blank=True)
    report_data = models.JSONField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'reconciliation_reports_3b'
