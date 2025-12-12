from django.db import models

class UploadedFile(models.Model):
    FILE_ROLE_CHOICES = [
        ("GSTR1", "GSTR1"),
        ("GSTR3B", "GSTR3B"),
    ]
    file = models.FileField(upload_to="uploads/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    role = models.CharField(max_length=10, choices=FILE_ROLE_CHOICES)
    metadata = models.JSONField(default=dict)

class ReconciliationJob(models.Model):
    gstin = models.CharField(max_length=15)
    period = models.CharField(max_length=7)  # YYYY-MM or YYYY-MM
    gstr1 = models.ForeignKey(UploadedFile, null=True, blank=True, related_name='job_gstr1', on_delete=models.SET_NULL)
    gstr3b = models.ForeignKey(UploadedFile, null=True, blank=True, related_name='job_gstr3b', on_delete=models.SET_NULL)
    status = models.CharField(max_length=20, default="PENDING")
    result = models.JSONField(null=True, blank=True)
    report_file = models.FileField(upload_to="reports/", null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
