from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from accounts.notify import notify
from loads.models import Load, Offer, OfferEvent

from .models import SpaceRequest, Trip


class SpaceError(Exception):
    pass


def expire_trips():
    """Close open trips whose departure date has passed."""
    stale = Trip.objects.filter(status='open', departure_date__lt=timezone.localdate())
    for trip in stale:
        trip.status = 'expired'
        trip.save()
        for req in trip.requests.filter(status='pending').select_related('shipper'):
            req.status = 'declined'
            req.save()
            notify(req.shipper,
                   f'Your space request on the trip {trip.origin} to {trip.destination} closed because the truck has left.',
                   reverse('space_list'))


@transaction.atomic
def accept_request(req):
    trip = Trip.objects.select_for_update().select_related('truck', 'owner').get(pk=req.trip_id)
    req = SpaceRequest.objects.select_for_update().select_related('shipper', 'load').get(pk=req.pk)

    if req.status != 'pending':
        raise SpaceError('This request was already answered.')
    if trip.status != 'open':
        raise SpaceError('This trip is no longer open.')
    if req.tonnes > trip.tonnes_left:
        raise SpaceError(f'Only {trip.tonnes_left} t are still free on this trip.')
    if not trip.truck.documents_ok:
        raise SpaceError("This truck's insurance or roadworthy certificate has expired. Update the truck first.")

    now = timezone.now()
    load = req.load
    if load is not None:
        if load.status != 'open':
            raise SpaceError("The shipper's load is no longer open.")
        load_url = reverse('load_detail', args=[load.pk])
        rivals = load.offers.filter(status__in=['pending', 'countered']).select_related('transporter')
        for rival in list(rivals):
            rival.status = 'declined'
            rival.save()
            OfferEvent.objects.create(offer=rival, kind='decline', price=rival.price)
            notify(rival.transporter,
                   f'The load "{load.title}" was booked on a planned trip instead.', load_url)
        others = (SpaceRequest.objects.filter(load=load, status='pending')
                  .exclude(pk=req.pk).select_related('shipper'))
        for other in list(others):
            other.status = 'declined'
            other.save()
            notify(other.trip.owner, f'A load you were matched with was booked elsewhere.',
                   reverse('space_trip', args=[other.trip_id]))
        load.status = 'booked'
        load.save()
    else:
        load = Load.objects.create(
            shipper=req.shipper, title=req.cargo, pickup=req.pickup, destination=req.dropoff,
            cargo_type=req.cargo_type, weight_tonnes=req.tonnes, truck_type_needed='any',
            offered_price=req.total_price, urgency='scheduled',
            pickup_date=trip.departure_date,
            description=f'Space booked on a planned trip. {req.message}'.strip(),
            status='booked')
        req.load = load

    offer = Offer.objects.create(
        load=load, transporter=trip.owner, truck=trip.truck, price=req.total_price,
        message='Space on a planned trip', status='accepted', accepted_at=now)
    OfferEvent.objects.create(offer=offer, actor=req.shipper, kind='offer', price=offer.price)
    OfferEvent.objects.create(offer=offer, actor=trip.owner, kind='accept', price=offer.price)

    req.status = 'accepted'
    req.save()
    return req, load, offer