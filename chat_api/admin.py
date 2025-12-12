from django.contrib import admin
from .models import UserContact

@admin.register(UserContact)
class UserContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'created_at')
    search_fields = ('name', 'phone')
