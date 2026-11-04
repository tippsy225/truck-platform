from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.notify import notify
from trucks.models import Truck
from wallet.models import Dispute, Escrow
from wallet.services import release_escrow

from .forms import CounterForm, LoadForm, OfferForm, PaymentForm
from .models import Load, Offer, OfferEvent, Payment
from .pricing import TOWNS
from .services import deadline_hours, run_housekeeping

DEMO_PREFIX = 'https://demo.local/payment/'


def _role(user):
    profile = getattr(user, 'profile', None)
    return profile.role if profile else None


def _needs_verification(user):
    if not getattr(settings, 'REQUIRE_VERIFICATION', False):
        return False
    if user.is_staff:
        return False
    profile = getattr(user, 'profile', None)
    return not (profile and profile.is_verified)


def _demo_mode():
    return getattr(settings, 'PAYMENT_MODE', 'demo') == 'demo'


def _paynow():
    from paynow import Paynow
    return Paynow(settings.PAYNOW_INTEGRATION_ID, settings.PAYNOW_INTEGRATION_KEY,
                  settings.PAYNOW_RESULT_URL, settings.PAYNOW_RETURN_URL)


def _load_url(load):
    return reverse('load_detail', args=[load.pk])


def load_list(request):
    run_housekeeping()
    selected = {
        'pickup': request.GET.get('pickup', ''),
        'destination': request.GET.get('destination', ''),
        'cargo': request.GET.get('cargo', ''),
        'truck': request.GET.get('truck', ''),
    }
    loads = Load.objects.filter(status='open')
    if selected['pickup']:
        loads = loads.filter(pickup=selected['pickup'])
    if selected['destination']:
        loads = loads.filter(destination=selected['destination'])
    if selected['cargo']:
        loads = loads.filter(cargo_type=selected['cargo'])
    if selected['truck']:
        loads = loads.filter(Q(truck_type_needed='any') | Q(truck_type_needed=selected['truck']))
    loads = sorted(loads, key=lambda l: (l.urgency != 'urgent', -l.created_at.timestamp()))
    return render(request, 'loads/load_list.html', {
        'loads': loads,
        'selected': selected,
        'filtered': any(selected.values()),
        'towns': sorted(TOWNS),
        'cargo_choices': Load.CARGO_CHOICES,
        'truck_choices': Truck.TYPE_CHOICES,
    })


@login_required
def post_load(request):
    if _role(request.user) != 'shipper':
        messages.error(request, 'Only shippers can post loads.')
        return redirect('home')
    if _needs_verification(request.user):
        messages.error(request, 'Verify your identity before you post a load.')
        return redirect('kyc')
    if request.method == 'POST':
        form = LoadForm(request.POST)
        if form.is_valid():
            load = form.save(commit=False)
            load.shipper = request.user
            load.save()
            messages.success(request, 'Load posted.')
            return redirect('my_loads')
    else:
        form = LoadForm()
    return render(request, 'loads/load_form.html', {'form': form})


@login_required
def my_loads(request):
    if _role(request.user) != 'shipper':
        return redirect('home')
    run_housekeeping()
    loads = Load.objects.filter(shipper=request.user).order_by('-created_at')
    return render(request, 'loads/my_loads.html', {'loads': loads})


@login_required
def load_detail(request, pk):
    run_housekeeping()
    load = get_object_or_404(Load, pk=pk)
    is_owner = load.shipper_id == request.user.id
    role = _role(request.user)

    my_offer = None
    form = None
    has_trucks = False
    needs_verification = False
    if role == 'transporter' and not is_owner:
        has_trucks = request.user.trucks.exists()
        my_offer = (load.offers.filter(transporter=request.user)
                    .exclude(status__in=['declined', 'withdrawn', 'expired']).first())
        needs_verification = _needs_verification(request.user)
        if load.status == 'open' and my_offer is None and has_trucks and not needs_verification:
            if request.method == 'POST':
                form = OfferForm(request.POST, user=request.user, load=load)
                if form.is_valid():
                    offer = form.save(commit=False)
                    offer.load = load
                    offer.transporter = request.user
                    offer.save()
                    OfferEvent.objects.create(offer=offer, actor=request.user,
                                              kind='offer', price=offer.price)
                    notify(load.shipper,
                           f'{request.user.username} offered ${offer.price} on "{load.title}".',
                           _load_url(load))
                    messages.success(request, 'Offer sent to the shipper.')
                    return redirect('load_detail', pk=load.pk)
            else:
                form = OfferForm(user=request.user, load=load)

    offers = []
    if is_owner:
        offers = (load.offers.select_related('transporter', 'truck')
                  .prefetch_related('events__actor').order_by('-created_at'))

    accepted_offer = (load.offers.filter(status='accepted')
                      .select_related('transporter', 'truck').first())
    my_role = None
    if accepted_offer:
        if is_owner:
            my_role = 'shipper'
        elif accepted_offer.transporter_id == request.user.id:
            my_role = 'transporter'
    is_party = my_role is not None
    fee_paid = bool(accepted_offer) and accepted_offer.fee_paid
    can_see_contacts = is_party and fee_paid

    open_dispute = bool(accepted_offer) and Dispute.objects.filter(
        offer=accepted_offer, status='open').exists()
    escrow_held = bool(accepted_offer) and Escrow.objects.filter(
        offer=accepted_offer, status='held').exists()
    escrow_required = getattr(settings, 'ESCROW_REQUIRED', False)

    my_paid = False
    my_fee = None
    pending_payment = None
    payment_form = None
    deadline = None
    if is_party and not fee_paid:
        deadline = accepted_offer.pay_deadline
        if my_role == 'shipper':
            my_paid = accepted_offer.shipper_paid
            my_fee = accepted_offer.shipper_fee
        else:
            my_paid = accepted_offer.transporter_paid
            my_fee = accepted_offer.transporter_fee
        if not my_paid:
            pending_payment = (accepted_offer.payments
                               .filter(payer=request.user, status='pending')
                               .exclude(poll_url='').first())
            if not pending_payment:
                payment_form = PaymentForm()

    can_deliver = (is_owner and load.status == 'booked' and fee_paid and not open_dispute
                   and (escrow_held or not escrow_required))

    return render(request, 'loads/load_detail.html', {
        'load': load,
        'form': form,
        'has_trucks': has_trucks,
        'needs_verification': needs_verification,
        'is_owner': is_owner,
        'role': role,
        'offers': offers,
        'my_offer': my_offer,
        'accepted_offer': accepted_offer,
        'is_party': is_party,
        'can_see_contacts': can_see_contacts,
        'my_paid': my_paid,
        'my_fee': my_fee,
        'pending_payment': pending_payment,
        'payment_form': payment_form,
        'deadline': deadline,
        'can_deliver': can_deliver,
    })


@login_required
@require_POST
def offer_action(request, pk, action):
    if action not in ('accept', 'decline', 'counter', 'withdraw'):
        raise Http404
    offer = get_object_or_404(
        Offer.objects.select_related('load', 'load__shipper', 'transporter'), pk=pk)
    load = offer.load
    user = request.user

    if user.id == load.shipper_id:
        side = 'shipper'
        other = offer.transporter
    elif user.id == offer.transporter_id:
        side = 'transporter'
        other = load.shipper
    else:
        raise Http404

    url = _load_url(load)
    your_turn = ((side == 'shipper' and offer.status == 'pending') or
                 (side == 'transporter' and offer.status == 'countered'))
    can_withdraw = side == 'transporter' and offer.status in ('pending', 'countered')
    allowed = can_withdraw if action == 'withdraw' else your_turn
    if load.status != 'open' or not allowed:
        messages.error(request, 'This offer can no longer be changed.')
        return redirect('load_detail', pk=load.pk)

    if action == 'counter':
        form = CounterForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Enter a valid counter price.')
            return redirect('load_detail', pk=load.pk)
        price = form.cleaned_data['price']
        offer.price = price
        offer.status = 'countered' if side == 'shipper' else 'pending'
        offer.save()
        OfferEvent.objects.create(offer=offer, actor=user, kind='counter', price=price)
        notify(other, f'{user.username} countered with ${price} on "{load.title}". Your move.', url)
        messages.success(request, 'Counter-offer sent.')

    elif action == 'accept':
        with transaction.atomic():
            offer.status = 'accepted'
            offer.accepted_at = timezone.now()
            offer.save()
            load.status = 'booked'
            load.save()
            OfferEvent.objects.create(offer=offer, actor=user, kind='accept', price=offer.price)
            rivals = load.offers.exclude(pk=offer.pk).filter(
                status__in=['pending', 'countered']).select_related('transporter')
            for rival in list(rivals):
                rival.status = 'declined'
                rival.save()
                OfferEvent.objects.create(offer=rival, kind='decline', price=rival.price)
                notify(rival.transporter,
                       f'The load "{load.title}" was booked with another transporter.', url)
        notify(other,
               f'Agreed at ${offer.price} on "{load.title}". Pay your platform fee within '
               f'{deadline_hours()} hours to unlock contact details.', url)
        messages.success(request,
                         f'Agreed at ${offer.price}. Both sides now pay a small platform fee '
                         f'within {deadline_hours()} hours to unlock contact details.')

    elif action == 'decline':
        offer.status = 'declined'
        offer.save()
        OfferEvent.objects.create(offer=offer, actor=user, kind='decline', price=offer.price)
        notify(other, f'{user.username} declined the offer on "{load.title}".', url)
        messages.success(request, 'Offer declined.')

    else:
        offer.status = 'withdrawn'
        offer.save()
        OfferEvent.objects.create(offer=offer, actor=user, kind='withdraw', price=offer.price)
        notify(other, f'{user.username} withdrew their offer on "{load.title}".', url)
        messages.success(request, 'Offer withdrawn.')

    return redirect('load_detail', pk=load.pk)


@login_required
@require_POST
def mark_delivered(request, pk):
    load = get_object_or_404(Load, pk=pk, shipper=request.user)
    offer = load.offers.filter(status='accepted').select_related('transporter').first()
    if load.status != 'booked' or not offer or not offer.fee_paid:
        messages.error(request, 'A load can be marked as delivered once it is booked and both fees are paid.')
        return redirect('load_detail', pk=load.pk)
    if Dispute.objects.filter(offer=offer, status='open').exists():
        messages.error(request, 'There is an open dispute on this job. A reviewer must resolve it first.')
        return redirect('load_detail', pk=load.pk)
    escrow = Escrow.objects.filter(offer=offer, status='held').first()
    if escrow is None and getattr(settings, 'ESCROW_REQUIRED', False):
        messages.error(request, 'Fund escrow before you mark this job as delivered.')
        return redirect('load_detail', pk=load.pk)

    with transaction.atomic():
        if escrow is not None:
            release_escrow(offer)
        load.status = 'delivered'
        load.save()

    if escrow is not None:
        notify(offer.transporter,
               f'"{load.title}" was marked as delivered. ${escrow.amount} was paid to your wallet.',
               _load_url(load))
        messages.success(request, f'Load marked as delivered. ${escrow.amount} was released to the transporter.')
    else:
        notify(offer.transporter, f'"{load.title}" was marked as delivered. Well done.', _load_url(load))
        messages.success(request, 'Load marked as delivered.')
    return redirect('load_detail', pk=load.pk)


@login_required
@require_POST
def pay_fee(request, pk):
    offer = get_object_or_404(Offer.objects.select_related('load'), pk=pk, status='accepted')
    load_pk = offer.load.pk

    if request.user.id == offer.load.shipper_id:
        role = 'shipper'
        amount = offer.shipper_fee
    elif request.user.id == offer.transporter_id:
        role = 'transporter'
        amount = offer.transporter_fee
    else:
        raise Http404

    if offer.payments.filter(status='paid', payer_role=role).exists():
        messages.info(request, 'Your platform fee is already paid.')
        return redirect('load_detail', pk=load_pk)

    form = PaymentForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Enter a valid 10-digit EcoCash number, like 0771234567.')
        return redirect('load_detail', pk=load_pk)

    demo = _demo_mode()
    if not demo and (not settings.PAYNOW_INTEGRATION_ID or not settings.PAYNOW_INTEGRATION_KEY):
        messages.error(request, 'Payments are not set up yet. Check config/local_settings.py.')
        return redirect('load_detail', pk=load_pk)

    payment = Payment.objects.create(
        offer=offer, payer=request.user, payer_role=role, amount=amount,
        phone=form.cleaned_data['phone'])

    if demo:
        if payment.phone == '0774444444':
            payment.status = 'failed'
            payment.save()
            messages.error(request, 'Demo mode: insufficient balance. Try another number.')
        else:
            payment.poll_url = f'{DEMO_PREFIX}{payment.pk}'
            payment.save()
            messages.success(request, 'Demo mode: payment request sent. Click "Check payment" to complete it.')
        return redirect('load_detail', pk=load_pk)

    try:
        paynow = _paynow()
        order = paynow.create_payment(f'Platform fee {payment.pk}', settings.PAYNOW_AUTH_EMAIL)
        order.add(f'Platform fee for {offer.load.title}', float(payment.amount))
        response = paynow.send_mobile(order, payment.phone, 'ecocash')
    except Exception:
        payment.status = 'failed'
        payment.save()
        messages.error(request, 'Could not reach Paynow. Please try again.')
        return redirect('load_detail', pk=load_pk)

    if response.success:
        payment.poll_url = response.poll_url
        payment.save()
        messages.success(request, 'Payment request sent. Enter your EcoCash PIN on your phone, then click "Check payment".')
    else:
        payment.status = 'failed'
        payment.save()
        reason = getattr(response, 'error', 'unknown error')
        messages.error(request, f'Paynow could not start the payment: {reason}')
    return redirect('load_detail', pk=load_pk)


def _mark_paid(request, payment):
    payment.status = 'paid'
    payment.paid_at = timezone.now()
    payment.save()
    offer = payment.offer
    load = offer.load
    url = _load_url(load)
    if offer.fee_paid:
        text = f'Both platform fees are paid for "{load.title}". Contact details are unlocked.'
        notify(offer.transporter, text, url)
        notify(load.shipper, text, url)
        messages.success(request, 'Payment received. Both fees are paid, so contact details are now visible.')
    else:
        other = offer.transporter if payment.payer_role == 'shipper' else load.shipper
        notify(other, f'{payment.payer.username} paid their platform fee for "{load.title}". '
                      f'Pay yours to unlock contact details.', url)
        messages.success(request, 'Payment received. Contact details appear when the other side pays their fee too.')


@login_required
@require_POST
def check_payment(request, pk):
    payment = get_object_or_404(Payment, pk=pk, payer=request.user)
    load_pk = payment.offer.load.pk

    if payment.status == 'pending' and payment.poll_url:
        if payment.poll_url.startswith(DEMO_PREFIX):
            if payment.phone == '0773333333':
                payment.status = 'failed'
                payment.save()
                messages.error(request, 'Demo mode: the payment was cancelled. You can try again.')
            else:
                _mark_paid(request, payment)
            return redirect('load_detail', pk=load_pk)

        try:
            status = _paynow().check_transaction_status(payment.poll_url)
        except Exception:
            messages.error(request, 'Could not check the payment right now. Try again in a moment.')
            return redirect('load_detail', pk=load_pk)

        if status.paid:
            _mark_paid(request, payment)
        elif str(getattr(status, 'status', '')).lower() in ('cancelled', 'failed', 'disputed', 'refunded'):
            payment.status = 'failed'
            payment.save()
            messages.error(request, 'The payment was cancelled or failed. You can try again.')
        else:
            messages.info(request, 'The payment is still pending. Wait a few seconds and check again.')
    return redirect('load_detail', pk=load_pk)


@login_required
def my_offers(request):
    if _role(request.user) != 'transporter':
        return redirect('home')
    run_housekeeping()
    offers = (Offer.objects.filter(transporter=request.user)
              .select_related('load', 'load__shipper').order_by('-created_at'))
    return render(request, 'loads/my_offers.html', {'offers': offers})