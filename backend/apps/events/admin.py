from django.contrib import admin

from .models import Device, LoginEvent


@admin.register(LoginEvent)
class LoginEventAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "timestamp", "country", "success", "source", "label")
    list_filter = ("success", "source", "label")
    raw_id_fields = ("user", "device")


admin.site.register(Device)
