from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import NotFound

from accounts.notify import notify
from loads.models import Load, Offer, OfferEvent
from loads.services import deadline_hours

from .rules import Conflict


def perform(offer_id, user, action, price=None):
    """Accept, decline, counter or withdraw an offer. Returns the updated offer."""
    outbox = []
    with transaction.atomic():
        offer = (Offer.objects.select_for_update(of=('self',))
                 .select_related('load', 'load__shipper', 'transporter')
                 .filter(pk=offer_id).first())
        if offer is None:
            raise NotFound('Offer not found.')
        load = Load.objects.select_for_update().get(pk=offer.load_id)

        if user.id == load.shipper_id:
            side, other = 'shipper', offer.transporter
        elif user.id == offer.transporter_id:
            side, other = 'transporter', load.shipper
        else:
            # Strangers get the same answer as a missing offer, so offers cannot be probed.
            raise NotFound('Offer not found.')

        your_turn = ((side == 'shipper' and offer.status == 'pending') or
                     (side == 'transporter' and offer.status == 'countered'))
        can_withdraw = side == 'transporter' and offer.status in ('pending', 'countered')
        allowed = can_withdraw if action == 'withdraw' else your_turn
        if load.status != 'open' or not allowed:
            raise Conflict('This offer cannot be changed by you right now.')

        url = reverse('load_detail', args=[load.pk])

        if action == 'counter':
            offer.price = price
            offer.status = 'countered' if side == 'shipper' else 'pending'
            offer.save()
            OfferEvent.objects.create(offer=offer, actor=user, kind='counter', price=price)
            outbox.append((other, f'{user.username} countered with ${price} on "{load.title}". Your move.', url))

        elif action == 'accept':
            offer.status = 'accepted'
            offer.accepted_at = timezone.now()
            offer.save()
            load.status = 'booked'
            load.save()
            OfferEvent.objects.create(offer=offer, actor=user, kind='accept', price=offer.price)
            rivals = (load.offers.exclude(pk=offer.pk)
                      .filter(status__in=['pending', 'countered']).select_related('transporter'))
            for rival in list(rivals):
                rival.status = 'declined'
                rival.save()
                OfferEvent.objects.create(offer=rival, kind='decline', price=rival.price)
                outbox.append((rival.transporter,
                               f'The load "{load.title}" was booked with another transporter.', url))
            outbox.append((other,
                           f'Agreed at ${offer.price} on "{load.title}". Pay your platform fee within '
                           f'{deadline_hours()} hours to unlock contact details.', url))

        elif action == 'decline':
            offer.status = 'declined'
            offer.save()
            OfferEvent.objects.create(offer=offer, actor=user, kind='decline', price=offer.price)
            outbox.append((other, f'{user.username} declined the offer on "{load.title}".', url))

        else:
            offer.status = 'withdrawn'
            offer.save()
            OfferEvent.objects.create(offer=offer, actor=user, kind='withdraw', price=offer.price)
            outbox.append((other, f'{user.username} withdrew their offer on "{load.title}".', url))

    for person, text, link in outbox:
        notify(person, text, link)
    return offer