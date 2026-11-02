from django.contrib import admin
from .models import Load, Offer, Payment


@admin.register(Load)
class LoadAdmin(admin.ModelAdmin):
    list_display = ('title', 'pickup', 'destination', 'weight_tonnes',
                    'offered_price', 'status', 'pickup_date', 'shipper')
    list_editable = ('status', 'pickup_date')
    list_filter = ('status',)
    search_fields = ('title', 'pickup', 'destination')


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ('load', 'transporter', 'price', 'status')
    list_filter = ('status',)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('offer', 'payer', 'payer_role', 'amount', 'phone', 'status', 'created_at')
    list_filter = ('status', 'payer_role')