import logging

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import Notification

from .backends import deliver
from .models import AlertPreference
from .phone import to_e164

log = logging.getLogger(__name__)


@receiver(post_save, sender=Notification)
def phone_alert(sender, instance, created, **kwargs):
    """Copy a new in-app notification to WhatsApp or SMS, for people who opted in."""
    if not created:
        return
    try:
        pref = AlertPreference.objects.filter(user=instance.user).exclude(channel='none').first()
        if pref is None:
            return
        phone = to_e164(pref.phone)
        if phone is None:
            return
        site = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000').rstrip('/')
        link = f' {site}{instance.url}' if instance.url else ''
        deliver(instance.user, pref.channel, phone, f'TruckLink: {instance.message}{link}')
    except Exception:
        log.exception('Could not send a phone alert')