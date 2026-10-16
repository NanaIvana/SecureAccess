from django.contrib import admin

from .models import Alert


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("id", "severity", "status", "created_at", "handled_by")
    list_filter = ("severity", "status")
    raw_id_fields = ("evaluation", "handled_by")
