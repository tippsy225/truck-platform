from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from accounts.notify import notify

from .models import Load, Offer, OfferEvent


def deadline_hours():
    return getattr(settings, 'PAYMENT_DEADLINE_HOURS', 24)


def expire_loads():
    """Close open loads whose pickup date has passed."""
    stale = Load.objects.filter(status='open', pickup_date__lt=timezone.localdate())
    for load in stale.select_related('shipper'):
        url = reverse('load_detail', args=[load.pk])
        with transaction.atomic():
            load.status = 'expired'
            load.save()
            open_offers = load.offers.filter(status__in=['pending', 'countered'])
            for offer in list(open_offers.select_related('transporter')):
                offer.status = 'declined'
                offer.save()
                OfferEvent.objects.create(offer=offer, kind='expire', price=offer.price)
                notify(offer.transporter,
                       f'The load "{load.title}" expired, so your offer was closed.', url)
        notify(load.shipper,
               f'Your load "{load.title}" expired because its pickup date passed. Post it again with a new date.',
               reverse('my_loads'))


def release_unpaid_bookings():
    """Cancel bookings where both fees were not paid before the deadline."""
    cutoff = timezone.now() - timedelta(hours=deadline_hours())
    late = (Offer.objects
            .filter(status='accepted', accepted_at__lt=cutoff, load__status='booked')
            .select_related('load', 'load__shipper', 'transporter'))
    for offer in list(late):
        if offer.fee_paid:
            continue
        load = offer.load
        with transaction.atomic():
            offer.status = 'expired'
            offer.save()
            load.status = 'open'
            load.save()
            OfferEvent.objects.create(offer=offer, kind='expire', price=offer.price)
            offer.payments.filter(status='paid').update(status='refund_due')
            offer.payments.filter(status='pending').update(status='failed')
        url = reverse('load_detail', args=[load.pk])
        text = (f'The booking for "{load.title}" was cancelled because both platform fees '
                f'were not paid within {deadline_hours()} hours.')
        notify(load.shipper, text + ' The load is open for offers again. Any fee you paid is marked as refund due.', url)
        notify(offer.transporter, text + ' Any fee you paid is marked as refund due.', url)


def run_housekeeping():
    expire_loads()
    release_unpaid_bookings()