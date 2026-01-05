from django.contrib import admin
from .models import UnifiedGSTSession

@admin.register(UnifiedGSTSession)
class UnifiedGSTSessionAdmin(admin.ModelAdmin):
    list_display = ['session_id', 'username', 'gstin', 'is_verified', 'created_at', 'expires_at']
    list_filter = ['is_verified', 'created_at']
    search_fields = ['username', 'gstin']
    readonly_fields = ['session_id', 'created_at']
