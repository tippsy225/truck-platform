import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse

from accounts.notify import notify
from loads.models import Load

from .models import Tracking
from .services import end_tracking

log = logging.getLogger(__name__)


@receiver(post_save, sender=Load)
def stop_when_job_ends(sender, instance, **kwargs):
    """Sharing stops by itself as soon as a load is no longer booked."""
    if instance.status == 'booked':
        return
    try:
        for tracking in Tracking.objects.filter(offer__load=instance, active=True).select_related('offer'):
            end_tracking(tracking)
            offer = tracking.offer
            text = f'Location sharing for "{instance.title}" has stopped because the job is no longer in progress.'
            url = reverse('track_page', args=[offer.pk])
            notify(instance.shipper, text, url)
            notify(offer.transporter, text, url)
    except Exception:
        log.exception('Could not end tracking when a load changed status')