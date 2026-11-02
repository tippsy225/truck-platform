from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import LoadForm, OfferForm, PaymentForm
from .models import Load, Offer, Payment

DEMO_PREFIX = 'https://demo.local/payment/'


def _role(user):
    profile = getattr(user, 'profile', None)
    return profile.role if profile else None


def _demo_mode():
    return getattr(settings, 'PAYMENT_MODE', 'demo') == 'demo'


def _paynow():
    from paynow import Paynow
    return Paynow(settings.PAYNOW_INTEGRATION_ID, settings.PAYNOW_INTEGRATION_KEY,
                  settings.PAYNOW_RESULT_URL, settings.PAYNOW_RETURN_URL)


def load_list(request):
    loads = Load.objects.filter(status='open').order_by('-created_at')
    return render(request, 'loads/load_list.html', {'loads': loads})


@login_required
def post_load(request):
    if _role(request.user) != 'shipper':
        messages.error(request, 'Only shippers can post loads.')
        return redirect('home')
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
    loads = Load.objects.filter(shipper=request.user).order_by('-created_at')
    return render(request, 'loads/my_loads.html', {'loads': loads})


@login_required
def load_detail(request, pk):
    load = get_object_or_404(Load, pk=pk)
    is_owner = load.shipper_id == request.user.id
    form = None

    if _role(request.user) == 'transporter' and load.status == 'open':
        if request.method == 'POST':
            form = OfferForm(request.POST, user=request.user)
            if form.is_valid():
                offer = form.save(commit=False)
                offer.load = load
                offer.transporter = request.user
                offer.save()
                messages.success(request, 'Offer sent to the shipper.')
                return redirect('my_offers')
        else:
            form = OfferForm(user=request.user)

    offers = load.offers.select_related('transporter', 'truck').order_by('-created_at') if is_owner else []
    accepted_offer = load.offers.filter(status='accepted').select_related('transporter').first()

    my_role = None
    if accepted_offer:
        if is_owner:
            my_role = 'shipper'
        elif accepted_offer.transporter_id == request.user.id:
            my_role = 'transporter'
    is_party = my_role is not None

    fee_paid = bool(accepted_offer) and accepted_offer.fee_paid
    can_see_contacts = is_party and fee_paid

    my_paid = False
    my_fee = None
    pending_payment = None
    payment_form = None
    if is_party and not fee_paid:
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

    return render(request, 'loads/load_detail.html', {
        'load': load,
        'form': form,
        'is_owner': is_owner,
        'offers': offers,
        'accepted_offer': accepted_offer,
        'is_party': is_party,
        'can_see_contacts': can_see_contacts,
        'my_paid': my_paid,
        'my_fee': my_fee,
        'pending_payment': pending_payment,
        'payment_form': payment_form,
    })


@login_required
@require_POST
def respond_offer(request, pk, decision):
    if decision not in ('accept', 'decline'):
        raise Http404
    offer = get_object_or_404(Offer, pk=pk, load__shipper=request.user)
    load = offer.load
    if offer.status != 'pending' or load.status != 'open':
        messages.error(request, 'This offer can no longer be changed.')
        return redirect('load_detail', pk=load.pk)

    if decision == 'accept':
        with transaction.atomic():
            offer.status = 'accepted'
            offer.save()
            load.status = 'booked'
            load.save()
            load.offers.exclude(pk=offer.pk).filter(status='pending').update(status='declined')
        messages.success(request, 'Offer accepted. Both sides now pay a small platform fee to unlock contact details.')
    else:
        offer.status = 'declined'
        offer.save()
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
    if payment.offer.fee_paid:
        messages.success(request, 'Payment received. Both fees are paid, so contact details are now visible.')
    else:
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
    offers = (Offer.objects.filter(transporter=request.user)
              .select_related('load', 'load__shipper').order_by('-created_at'))
    return render(request, 'loads/my_offers.html', {'offers': offers})