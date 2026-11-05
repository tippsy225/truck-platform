from django.conf import settings
from django.db import models


class Subscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='subscriptions')
    plan_key = models.CharField(max_length=20)
    started_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    price_paid = models.DecimalField(max_digits=8, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.user.username}: {self.plan_key} until {self.expires_at:%d %b %Y}"


class ReferralCode(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='referral_code')
    code = models.CharField(max_length=12, unique=True)

    def __str__(self):
        return f"{self.user.username}: {self.code}"


class Referral(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Waiting for a first delivered job'),
        ('rewarded', 'Rewarded'),
        ('capped', 'Reward limit reached'),
    ]

    referrer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name='referrals_made')
    referred = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                    related_name='referral')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    rewarded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.referrer.username} referred {self.referred.username} ({self.status})"