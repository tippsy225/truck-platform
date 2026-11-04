from django.contrib import admin

# Register your models here.
from django.contrib import admin

from .models import SpaceRequest, Trip


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ('origin', 'destination', 'departure_date', 'owner', 'truck',
                    'tonnes_available', 'price_per_tonne', 'status')
    list_filter = ('status',)


@admin.register(SpaceRequest)
class SpaceRequestAdmin(admin.ModelAdmin):
    list_display = ('trip', 'shipper', 'tonnes', 'price_per_tonne', 'status', 'created_at')
    list_filter = ('status',)