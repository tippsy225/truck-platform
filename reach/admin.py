from django.contrib import admin

from .models import AlertPreference, OutboxMessage


@admin.register(AlertPreference)
class AlertPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'channel', 'phone', 'updated_at')
    list_filter = ('channel',)


@admin.register(OutboxMessage)
class OutboxMessageAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'channel', 'status', 'body')
    list_filter = ('status', 'channel')