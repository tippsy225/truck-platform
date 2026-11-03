from django.contrib import admin
from .models import Load, Offer, OfferEvent, Payment


@admin.register(Load)
class LoadAdmin(admin.ModelAdmin):
    list_display = ('title', 'pickup', 'destination', 'cargo_type', 'weight_tonnes',
                    'offered_price', 'urgency', 'status', 'pickup_date', 'shipper')
    list_editable = ('status', 'pickup_date')
    list_filter = ('status', 'cargo_type', 'urgency')
    search_fields = ('title', 'pickup', 'destination')


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ('load', 'transporter', 'price', 'status', 'accepted_at')
    list_filter = ('status',)


@admin.register(OfferEvent)
class OfferEventAdmin(admin.ModelAdmin):
    list_display = ('offer', 'actor', 'kind', 'price', 'created_at')
    list_filter = ('kind',)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('offer', 'payer', 'payer_role', 'amount', 'phone', 'status', 'created_at')
    list_filter = ('status', 'payer_role')