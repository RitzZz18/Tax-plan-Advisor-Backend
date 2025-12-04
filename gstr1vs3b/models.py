from django.db import models

class ReconciliationReport(models.Model):
    username = models.CharField(max_length=255)
    gstin = models.CharField(max_length=15)
    fy_year = models.IntegerField()
    report_data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
