from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import LoadForm, OfferForm
from .models import Load, Offer


def _role(user):
    profile = getattr(user, 'profile', None)
    return profile.role if profile else None


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
    can_see_contacts = bool(accepted_offer) and (
        is_owner or accepted_offer.transporter_id == request.user.id)

    return render(request, 'loads/load_detail.html', {
        'load': load,
        'form': form,
        'is_owner': is_owner,
        'offers': offers,
        'accepted_offer': accepted_offer,
        'can_see_contacts': can_see_contacts,
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
        messages.success(request, 'Offer accepted. Contact details are now visible.')
    else:
        offer.status = 'declined'
        offer.save()
    return redirect('load_detail', pk=load.pk)


@login_required
def my_offers(request):
    if _role(request.user) != 'transporter':
        return redirect('home')
    offers = (Offer.objects.filter(transporter=request.user)
              .select_related('load', 'load__shipper').order_by('-created_at'))
    return render(request, 'loads/my_offers.html', {'offers': offers})