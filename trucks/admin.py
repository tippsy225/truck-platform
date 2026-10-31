from django.contrib import admin
from .models import Truck


@admin.register(Truck)
class TruckAdmin(admin.ModelAdmin):
    list_display = ('registration_number', 'truck_type', 'capacity_tonnes', 'owner',
                    'current_location', 'heading_to', 'is_available')
    list_filter = ('truck_type', 'is_available')
    search_fields = ('registration_number', 'current_location', 'heading_to')