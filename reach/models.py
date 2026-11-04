from django.conf import settings
from django.db import models


class AlertPreference(models.Model):
    CHANNEL_CHOICES = [
        ('none', 'No phone alerts'),
        ('whatsapp', 'WhatsApp'),
        ('sms', 'SMS'),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='alert_pref')
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES, default='none')
    phone = models.CharField(max_length=20, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}: {self.channel}"


class OutboxMessage(models.Model):
    STATUS_CHOICES = [
        ('queued', 'Recorded, not sent'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='outbox')
    channel = models.CharField(max_length=10)
    phone = models.CharField(max_length=20)
    body = models.CharField(max_length=300)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='queued')
    detail = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f"{self.user.username} via {self.channel}: {self.body[:40]}"