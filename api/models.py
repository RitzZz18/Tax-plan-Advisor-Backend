# backend/api/models.py
from django.db import models

class DubaiInquiry(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    budget = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)




