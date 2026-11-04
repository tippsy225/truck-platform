from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from accounts.notify import notify
from loads.models import OfferEvent

from .models import Escrow, LedgerEntry

CENT = Decimal('0.01')


class WalletError(Exception):
    pass


def balance(user):
    total = LedgerEntry.objects.filter(user=user).aggregate(total=Sum('amount'))['total']
    return Decimal(total or 0).quantize(CENT)


def _post(user, amount, kind, note, offer=None):
    return LedgerEntry.objects.create(user=user, amount=amount, kind=kind,
                                      note=note[:200], offer=offer)


def topup(user, amount):
    amount = Decimal(amount).quantize(CENT)
    if amount <= 0:
        raise WalletError('Enter an amount above zero.')
    _post(user, amount, 'topup', 'Simulated top up')


@transaction.atomic
def withdraw(user, amount):
    amount = Decimal(amount).quantize(CENT)
    if amount <= 0:
        raise WalletError('Enter an amount above zero.')
    available = balance(user)
    if amount > available:
        raise WalletError(f'You only have ${available} available.')
    _post(user, -amount, 'withdraw', 'Simulated withdrawal')


def _held(offer):
    escrow = Escrow.objects.select_for_update().filter(offer=offer, status='held').first()
    if escrow is None:
        raise WalletError('There is no money held in escrow for this job.')
    return escrow


@transaction.atomic
def fund_escrow(offer):
    from .models import Dispute
    load = offer.load
    if offer.status != 'accepted' or load.status != 'booked':
        raise WalletError('Escrow can be funded on a booked job.')
    if not offer.fee_paid:
        raise WalletError('Both platform fees must be paid before you fund escrow.')
    if Escrow.objects.filter(offer=offer).exists():
        raise WalletError('Escrow is already funded for this job.')
    if Dispute.objects.filter(offer=offer, status='open').exists():
        raise WalletError('This job has an open dispute.')
    amount = Decimal(offer.price).quantize(CENT)
    available = balance(load.shipper)
    if available < amount:
        raise WalletError(f'Your wallet has ${available}, but escrow needs ${amount}. Top up first.')
    Escrow.objects.create(offer=offer, amount=amount)
    _post(load.shipper, -amount, 'escrow_hold', f'Held in escrow for "{load.title}"', offer)


@transaction.atomic
def release_escrow(offer):
    escrow = _held(offer)
    _post(offer.transporter, escrow.amount, 'escrow_release',
          f'Paid for "{offer.load.title}"', offer)
    escrow.status = 'released'
    escrow.resolved_at = timezone.now()
    escrow.save()
    return escrow


@transaction.atomic
def refund_escrow(offer):
    escrow = _held(offer)
    _post(offer.load.shipper, escrow.amount, 'escrow_refund',
          f'Refund for "{offer.load.title}"', offer)
    escrow.status = 'refunded'
    escrow.resolved_at = timezone.now()
    escrow.save()
    return escrow


@transaction.atomic
def split_escrow(offer):
    escrow = _held(offer)
    half = (escrow.amount / 2).quantize(CENT)
    rest = escrow.amount - half
    _post(offer.transporter, half, 'escrow_release',
          f'Half of the payment for "{offer.load.title}" (dispute)', offer)
    _post(offer.load.shipper, rest, 'escrow_refund',
          f'Half refunded for "{offer.load.title}" (dispute)', offer)
    escrow.status = 'split'
    escrow.resolved_at = timezone.now()
    escrow.save()
    return escrow


@transaction.atomic
def resolve_dispute(dispute, resolution, admin_user, note=''):
    if dispute.status != 'open':
        raise WalletError('This dispute is already resolved.')
    offer = dispute.offer
    load = offer.load

    if resolution == 'release':
        release_escrow(offer)
        outcome = 'The money was released to the transporter.'
    elif resolution == 'refund':
        refund_escrow(offer)
        outcome = 'The money was refunded to the shipper.'
    elif resolution == 'split':
        split_escrow(offer)
        outcome = 'The money was split between both sides.'
    elif resolution == 'no_escrow':
        outcome = 'The dispute was closed without moving any money.'
    else:
        raise WalletError('Choose how to resolve this dispute.')

    if resolution in ('release', 'split'):
        load.status = 'delivered'
        load.save()
    elif resolution == 'refund':
        offer.status = 'expired'
        offer.save()
        load.status = 'open'
        load.save()
        OfferEvent.objects.create(offer=offer, kind='expire', price=offer.price)

    dispute.status = 'resolved'
    dispute.resolution = resolution
    dispute.admin_note = note
    dispute.resolved_by = admin_user
    dispute.resolved_at = timezone.now()
    dispute.save()

    text = f'The dispute on "{load.title}" was resolved. {outcome}'
    if note:
        text += f' Reviewer note: {note}'
    url = reverse('dispute_detail', args=[dispute.pk])
    notify(load.shipper, text, url)
    notify(offer.transporter, text, url)