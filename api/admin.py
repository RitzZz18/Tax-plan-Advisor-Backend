from django.contrib import admin
from .models import DubaiInquiry

@admin.register(DubaiInquiry)
class UserContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'budget', 'created_at')
    search_fields = ('name', 'email', 'phone')
    list_filter = ('created_at',)
