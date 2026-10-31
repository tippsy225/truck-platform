from django.contrib import admin
from .models import Load


@admin.register(Load)
class LoadAdmin(admin.ModelAdmin):
    list_display = ('title', 'pickup', 'destination', 'weight_tonnes',
                    'offered_price', 'status', 'pickup_date')
    list_editable = ('status', 'pickup_date')
    list_filter = ('status',)
    search_fields = ('title', 'pickup', 'destination')