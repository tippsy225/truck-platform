from django.contrib import admin

from .models import Referral, ReferralCode, Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan_key', 'started_at', 'expires_at', 'price_paid')
    list_filter = ('plan_key',)


@admin.register(ReferralCode)
class ReferralCodeAdmin(admin.ModelAdmin):
    list_display = ('user', 'code')


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ('referrer', 'referred', 'status', 'created_at', 'rewarded_at')
    list_filter = ('status',)