from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import LocationPing


def retention_days():
    return getattr(settings, 'TRACKING_RETENTION_DAYS', 7)


def purge_old_pings():
    cutoff = timezone.now() - timedelta(days=retention_days())
    deleted, _ = LocationPing.objects.filter(created_at__lt=cutoff).delete()
    return deleted


def can_track(offer):
    """Tracking is allowed while a job is booked and both platform fees are paid."""
    return (offer.status == 'accepted' and offer.load.status == 'booked'
            and offer.fee_paid)


def end_tracking(tracking):
    if tracking.active:
        tracking.active = False
        tracking.ended_at = timezone.now()
    tracking.last_lat = None
    tracking.last_lng = None
    tracking.last_accuracy = None
    tracking.last_at = None
    tracking.save()