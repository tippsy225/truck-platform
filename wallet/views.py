from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.notify import notify
from loads.models import Offer

from .forms import DisputeForm, DisputeMessageForm, TopUpForm, WithdrawForm
from .models import Dispute, DisputeMessage, Escrow, LedgerEntry
from .services import WalletError, balance, fund_escrow, topup, withdraw


def _demo_mode():
    return getattr(settings, 'PAYMENT_MODE', 'demo') == 'demo'


def _total(queryset):
    return Decimal(queryset.aggregate(t=Sum('amount'))['t'] or 0).quantize(Decimal('0.01'))


def _notify_staff(text, url):
    for staff in User.objects.filter(is_staff=True):
        notify(staff, text, url)


@login_required
def wallet_home(request):
    held_by_me = (Escrow.objects.filter(status='held', offer__load__shipper=request.user)
                  .select_related('offer__load'))
    held_for_me = (Escrow.objects.filter(status='held', offer__transporter=request.user)
                   .select_related('offer__load'))
    return render(request, 'wallet/wallet.html', {
        'balance': balance(request.user),
        'entries': LedgerEntry.objects.filter(user=request.user)[:50],
        'held_by_me': held_by_me,
        'held_for_me': held_for_me,
        'held_by_me_total': _total(held_by_me),
        'held_for_me_total': _total(held_for_me),
        'topup_form': TopUpForm(auto_id='topup_%s'),
        'withdraw_form': WithdrawForm(auto_id='withdraw_%s'),
        'demo': _demo_mode(),
    })


@login_required
@require_POST
def wallet_topup(request):
    if not _demo_mode():
        messages.error(request, 'Real top ups through Paynow are not built yet. Use demo mode to practise.')
        return redirect('wallet_home')
    form = TopUpForm(request.POST, auto_id='topup_%s')
    if form.is_valid():
        topup(request.user, form.cleaned_data['amount'])
        messages.success(request, f'${form.cleaned_data["amount"]} added to your wallet (simulated).')
    else:
        messages.error(request, 'Enter an amount between $1 and $5000.')
    return redirect('wallet_home')


@login_required
@require_POST
def wallet_withdraw(request):
    if not _demo_mode():
        messages.error(request, 'Real withdrawals are not built yet. Use demo mode to practise.')
        return redirect('wallet_home')
    form = WithdrawForm(request.POST, auto_id='withdraw_%s')
    if form.is_valid():
        try:
            withdraw(request.user, form.cleaned_data['amount'])
        except WalletError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f'${form.cleaned_data["amount"]} withdrawn (simulated).')
    else:
        messages.error(request, 'Enter an amount of at least $1.')
    return redirect('wallet_home')


@login_required
@require_POST
def escrow_fund(request, offer_pk):
    offer = get_object_or_404(
        Offer.objects.select_related('load', 'load__shipper', 'transporter'),
        pk=offer_pk, status='accepted', load__shipper=request.user)
    load = offer.load
    try:
        fund_escrow(offer)
    except WalletError as exc:
        messages.error(request, str(exc))
    else:
        notify(offer.transporter,
               f'Escrow is funded: ${offer.price} is held for "{load.title}". '
               f'It is paid to your wallet when the shipper confirms delivery.',
               reverse('load_detail', args=[load.pk]))
        messages.success(request,
                         f'${offer.price} moved into escrow. It is paid to the transporter '
                         f'when you mark the load as delivered.')
    return redirect('load_detail', pk=load.pk)


def _party_offer(request, offer_pk):
    offer = get_object_or_404(
        Offer.objects.select_related('load', 'load__shipper', 'transporter'),
        pk=offer_pk, status='accepted')
    if request.user.id not in (offer.load.shipper_id, offer.transporter_id):
        raise Http404
    return offer


@login_required
def dispute_new(request, offer_pk):
    offer = _party_offer(request, offer_pk)
    load = offer.load
    existing = offer.disputes.filter(status='open').first()
    if existing:
        return redirect('dispute_detail', pk=existing.pk)
    if load.status != 'booked' or not offer.fee_paid:
        messages.error(request, 'A dispute can be raised on a booked job once both platform fees are paid.')
        return redirect('load_detail', pk=load.pk)

    if request.method == 'POST':
        form = DisputeForm(request.POST)
        if form.is_valid():
            dispute = Dispute.objects.create(
                offer=offer, raised_by=request.user,
                reason=form.cleaned_data['reason'],
                description=form.cleaned_data['description'].strip())
            other = offer.transporter if request.user.id == load.shipper_id else load.shipper
            notify(other,
                   f'{request.user.username} raised a dispute on "{load.title}". '
                   f'Any escrow payment is paused until a reviewer decides.',
                   reverse('dispute_detail', args=[dispute.pk]))
            _notify_staff(f'New dispute on "{load.title}" from {request.user.username}.',
                          reverse('admin:wallet_dispute_change', args=[dispute.pk]))
            messages.success(request, 'Your dispute was sent to a reviewer. You can add messages below.')
            return redirect('dispute_detail', pk=dispute.pk)
    else:
        form = DisputeForm()
    return render(request, 'wallet/dispute_form.html', {'form': form, 'offer': offer, 'load': load})


@login_required
def dispute_detail(request, pk):
    dispute = get_object_or_404(
        Dispute.objects.select_related('offer', 'offer__load', 'offer__load__shipper',
                                       'offer__transporter', 'raised_by'), pk=pk)
    offer = dispute.offer
    load = offer.load
    is_party = request.user.id in (load.shipper_id, offer.transporter_id)
    if not (is_party or request.user.is_staff):
        raise Http404

    if request.method == 'POST':
        if dispute.status != 'open':
            messages.error(request, 'This dispute is resolved, so no more messages can be added.')
            return redirect('dispute_detail', pk=dispute.pk)
        form = DisputeMessageForm(request.POST)
        if form.is_valid():
            DisputeMessage.objects.create(dispute=dispute, author=request.user,
                                          body=form.cleaned_data['body'].strip())
            url = reverse('dispute_detail', args=[dispute.pk])
            text = f'{request.user.username} added a message to the dispute on "{load.title}".'
            if request.user.is_staff and not is_party:
                notify(load.shipper, text, url)
                notify(offer.transporter, text, url)
            else:
                other = offer.transporter if request.user.id == load.shipper_id else load.shipper
                notify(other, text, url)
                _notify_staff(text, reverse('admin:wallet_dispute_change', args=[dispute.pk]))
            messages.success(request, 'Message added.')
            return redirect('dispute_detail', pk=dispute.pk)
    else:
        form = DisputeMessageForm()

    return render(request, 'wallet/dispute_detail.html', {
        'dispute': dispute,
        'offer': offer,
        'load': load,
        'escrow': Escrow.objects.filter(offer=offer).first(),
        'thread': dispute.thread.select_related('author'),
        'form': form,
    })


@login_required
def dispute_list(request):
    disputes = (Dispute.objects
                .filter(Q(offer__transporter=request.user) | Q(offer__load__shipper=request.user))
                .select_related('offer__load').distinct())
    return render(request, 'wallet/dispute_list.html', {'disputes': disputes})