from django.contrib import admin

from .models import LocationPing, Tracking


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Tracking)
class TrackingAdmin(ReadOnlyAdmin):
    list_display = ('offer', 'active', 'started_at', 'ended_at', 'last_at')
    list_filter = ('active',)


@admin.register(LocationPing)
class LocationPingAdmin(ReadOnlyAdmin):
    list_display = ('created_at', 'tracking', 'lat', 'lng', 'accuracy')