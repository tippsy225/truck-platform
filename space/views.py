from django.shortcuts import render

# Create your views here.
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from accounts.notify import notify
from loads.models import Load
from loads.pricing import TOWNS
from loads.services import deadline_hours

from .forms import SpaceRequestForm, TripForm
from .matching import matches_for_load, matches_for_trip, route_fit
from .models import SpaceRequest, Trip
from .services import SpaceError, accept_request, expire_trips


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


def _decimal(text):
    try:
        return Decimal(text) if text else None
    except InvalidOperation:
        return None


def _date(text):
    try:
        return parse_date(text) if text else None
    except ValueError:
        return None


@login_required
def space_list(request):
    expire_trips()
    selected = {
        'origin': request.GET.get('origin', ''),
        'destination': request.GET.get('destination', ''),
        'date': request.GET.get('date', ''),
        'tonnes': request.GET.get('tonnes', ''),
        'max_price': request.GET.get('max_price', ''),
    }
    origin, dest = selected['origin'], selected['destination']
    date_from = _date(selected['date'])
    min_t = _decimal(selected['tonnes'])
    max_p = _decimal(selected['max_price'])

    results = []
    trips = Trip.objects.filter(status='open').select_related('truck', 'owner')
    for trip in trips:
        stops = trip.stops
        if origin and dest and not route_fit(stops, origin, dest):
            continue
        if origin and not dest and origin not in stops[:-1]:
            continue
        if dest and not origin and dest not in stops[1:]:
            continue
        if date_from and trip.departure_date < date_from:
            continue
        left = trip.tonnes_left
        if left <= 0 or (min_t and left < min_t):
            continue
        if max_p and trip.price_per_tonne > max_p:
            continue
        if not trip.truck.documents_ok:
            continue
        results.append(trip)

    return render(request, 'space/space_list.html', {
        'trips': results,
        'selected': selected,
        'filtered': any(selected.values()),
        'towns': sorted(TOWNS),
    })


@login_required
def trip_new(request):
    if _role(request.user) != 'transporter':
        messages.error(request, 'Only transporters can post trips.')
        return redirect('home')
    if _needs_verification(request.user):
        messages.error(request, 'Verify your identity before you post a trip.')
        return redirect('kyc')
    if not request.user.trucks.exists():
        messages.error(request, 'Register a truck before you post a trip.')
        return redirect('add_truck')
    if request.method == 'POST':
        form = TripForm(request.POST, user=request.user)
        if form.is_valid():
            trip = form.save(commit=False)
            trip.owner = request.user
            trip.save()
            messages.success(request, 'Trip posted. Shippers with matching loads are alerted automatically.')
            return redirect('space_trip', pk=trip.pk)
    else:
        form = TripForm(user=request.user)
    return render(request, 'space/trip_form.html', {'form': form})


@login_required
def my_trips(request):
    if _role(request.user) != 'transporter':
        return redirect('home')
    expire_trips()
    trips = Trip.objects.filter(owner=request.user).select_related('truck')
    return render(request, 'space/my_trips.html', {'trips': trips})


@login_required
def trip_detail(request, pk):
    expire_trips()
    trip = get_object_or_404(Trip.objects.select_related('truck', 'owner'), pk=pk)
    is_owner = trip.owner_id == request.user.id
    role = _role(request.user)

    form = None
    my_request = None
    link_load = None
    if not is_owner and role == 'shipper':
        my_request = trip.requests.filter(shipper=request.user, status='pending').first()
        load_id = request.GET.get('load') or request.POST.get('load_id') or ''
        if load_id.isdigit():
            link_load = Load.objects.filter(pk=load_id, shipper=request.user, status='open').first()
        if trip.status == 'open' and my_request is None and trip.tonnes_left > 0:
            if request.method == 'POST':
                form = SpaceRequestForm(request.POST, trip=trip, load=link_load)
                if form.is_valid():
                    data = form.cleaned_data
                    req = SpaceRequest.objects.create(
                        trip=trip, shipper=request.user, load=link_load, cargo=data['cargo'],
                        cargo_type=data['cargo_type'], pickup=data['pickup'],
                        dropoff=data['dropoff'], tonnes=data['tonnes'],
                        price_per_tonne=data['price_per_tonne'],
                        message=data['message'].strip())
                    notify(trip.owner,
                           f'{request.user.username} wants {req.tonnes} t on your trip '
                           f'{trip.origin} to {trip.destination} ({req.pickup} to {req.dropoff}) '
                           f'for ${req.total_price}.',
                           reverse('space_trip', args=[trip.pk]))
                    messages.success(request, 'Request sent. The transporter will accept or decline.')
                    return redirect('space_trip', pk=trip.pk)
            else:
                form = SpaceRequestForm(trip=trip, load=link_load)

    requests_list = []
    matches = []
    if is_owner:
        requests_list = trip.requests.select_related('shipper', 'load').order_by('-created_at')
        matches = matches_for_trip(trip)[:10]

    return render(request, 'space/trip_detail.html', {
        'trip': trip,
        'is_owner': is_owner,
        'role': role,
        'form': form,
        'my_request': my_request,
        'link_load': link_load,
        'requests_list': requests_list,
        'matches': matches,
    })


@login_required
@require_POST
def request_action(request, pk, action):
    if action not in ('accept', 'decline', 'withdraw'):
        raise Http404
    req = get_object_or_404(
        SpaceRequest.objects.select_related('trip', 'trip__owner', 'shipper', 'load'), pk=pk)
    trip = req.trip
    trip_url = reverse('space_trip', args=[trip.pk])

    if action == 'withdraw':
        if request.user.id != req.shipper_id:
            raise Http404
        if req.status != 'pending':
            messages.error(request, 'This request can no longer be changed.')
            return redirect('space_trip', pk=trip.pk)
        req.status = 'withdrawn'
        req.save()
        notify(trip.owner, f'{req.shipper.username} withdrew their space request.', trip_url)
        messages.success(request, 'Request withdrawn.')
        return redirect('space_trip', pk=trip.pk)

    if request.user.id != trip.owner_id:
        raise Http404
    if req.status != 'pending':
        messages.error(request, 'This request was already answered.')
        return redirect('space_trip', pk=trip.pk)

    if action == 'decline':
        req.status = 'declined'
        req.save()
        notify(req.shipper,
               f'{trip.owner.username} declined your space request on {trip.origin} to {trip.destination}.',
               reverse('space_list'))
        messages.success(request, 'Request declined.')
        return redirect('space_trip', pk=trip.pk)

    try:
        req, load, offer = accept_request(req)
    except SpaceError as exc:
        messages.error(request, str(exc))
        return redirect('space_trip', pk=trip.pk)
    notify(req.shipper,
           f'{trip.owner.username} accepted your request for {req.tonnes} t. Pay your platform fee '
           f'within {deadline_hours()} hours to unlock contact details.',
           reverse('load_detail', args=[load.pk]))
    messages.success(request,
                     f'Accepted. Both sides now pay a small platform fee within '
                     f'{deadline_hours()} hours to unlock contact details.')
    return redirect('load_detail', pk=load.pk)


@login_required
@require_POST
def close_trip(request, pk):
    trip = get_object_or_404(Trip, pk=pk, owner=request.user)
    if trip.status != 'open':
        messages.error(request, 'This trip is already closed.')
    else:
        trip.status = 'closed'
        trip.save()
        for req in trip.requests.filter(status='pending').select_related('shipper'):
            req.status = 'declined'
            req.save()
            notify(req.shipper,
                   f'The trip {trip.origin} to {trip.destination} was closed, so your space request was declined.',
                   reverse('space_list'))
        messages.success(request, 'Trip closed.')
    return redirect('my_trips')


@login_required
def load_matches(request, pk):
    expire_trips()
    load = get_object_or_404(Load, pk=pk, shipper=request.user)
    return render(request, 'space/load_matches.html', {
        'load': load,
        'matches': matches_for_load(load),
    })