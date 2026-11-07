from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import Truck, TruckPhoto


@admin.register(Truck)
class TruckAdmin(admin.ModelAdmin):
    list_display = ('registration_number', 'truck_type', 'capacity_tonnes', 'owner',
                    'current_location', 'heading_to', 'is_available')
    list_filter = ('truck_type', 'is_available')
    search_fields = ('registration_number', 'current_location', 'heading_to')


@admin.register(TruckPhoto)
class TruckPhotoAdmin(admin.ModelAdmin):
    """Staff can look at photos and delete any that are not suitable. Deleting also removes the files."""
    list_display = ('truck', 'kind', 'created_at', 'open_photo')
    list_filter = ('kind',)
    fields = ('truck', 'kind', 'open_photo')
    readonly_fields = ('truck', 'kind', 'open_photo')

    def has_add_permission(self, request):
        return False

    @admin.display(description='Photo')
    def open_photo(self, obj):
        if not obj.pk:
            return '-'
        return format_html('<a href="{}" target="_blank">Open photo</a>',
                           reverse('truck_photo_file', args=[obj.pk, 'full']))