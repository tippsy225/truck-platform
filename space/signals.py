import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse

from accounts.notify import notify
from loads.models import Load

from .matching import matches_for_load, matches_for_trip
from .models import Trip

log = logging.getLogger(__name__)


@receiver(post_save, sender=Load)
def alert_trip_owners(sender, instance, created, **kwargs):
    """A new open load: tell transporters whose planned trip fits it."""
    if not created or instance.status != 'open':
        return
    try:
        told = set()
        for match in matches_for_load(instance)[:5]:
            trip = match['trip']
            if trip.owner_id in told:
                continue
            told.add(trip.owner_id)
            notify(trip.owner,
                   f'New load on your route: {instance.pickup} to {instance.destination}, '
                   f'{instance.weight_tonnes} t, ${instance.offered_price}. It fits your trip on '
                   f'{trip.departure_date:%d %b}.',
                   reverse('load_detail', args=[instance.pk]))
    except Exception:
        log.exception('Could not send route alerts for a new load')


@receiver(post_save, sender=Trip)
def alert_shippers(sender, instance, created, **kwargs):
    """A new trip: tell shippers whose open load fits it."""
    if not created or instance.status != 'open':
        return
    try:
        for match in matches_for_trip(instance)[:5]:
            load = match['load']
            notify(load.shipper,
                   f'A truck is heading your way: {instance.origin} to {instance.destination} on '
                   f'{instance.departure_date:%d %b} has {instance.tonnes_left} t free for your '
                   f'load "{load.title}".',
                   reverse('load_matches', args=[load.pk]))
    except Exception:
        log.exception('Could not send route alerts for a new trip')