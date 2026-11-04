import json
import math
import time
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.notify import notify
from loads.models import Offer
from loads.pricing import TOWNS

from .geo import km_to_go
from .models import LocationPing, Tracking
from .services import can_track, end_tracking, purge_old_pings, retention_days

STALE_SECONDS = 120
MIN_INTERVAL = 5


def _party_offer(request, offer_pk):
    offer = get_object_or_404(
        Offer.objects.select_related('load', 'load__shipper', 'transporter'),
        pk=offer_pk, status='accepted')
    if request.user.id == offer.transporter_id:
        return offer, 'transporter'
    if request.user.id == offer.load.shipper_id:
        return offer, 'shipper'
    raise Http404


def _point(name):
    coords = TOWNS.get(name)
    return [coords[0], coords[1], name] if coords else None


@login_required
def track_page(request, offer_pk):
    offer, side = _party_offer(request, offer_pk)
    load = offer.load
    tracking = Tracking.objects.filter(offer=offer).first()
    ready = can_track(offer)
    if tracking and tracking.active and not ready:
        end_tracking(tracking)
    purge_old_pings()
    active = bool(tracking and tracking.active)

    config = {
        'side': side,
        'active': active,
        'dataUrl': reverse('track_data', args=[offer.pk]),
        'pingUrl': reverse('track_ping', args=[offer.pk]),
        'csrf': get_token(request),
        'pickup': _point(load.pickup),
        'destination': _point(load.destination),
    }
    return render(request, 'tracking/track.html', {
        'offer': offer, 'load': load, 'side': side, 'ready': ready,
        'active': active, 'config': config, 'retention': retention_days(),
    })


@login_required
@require_POST
def start_tracking(request, offer_pk):
    offer, side = _party_offer(request, offer_pk)
    if side != 'transporter':
        raise Http404
    load = offer.load
    if not can_track(offer):
        messages.error(request, 'Tracking can start once the job is booked and both platform fees are paid.')
        return redirect('load_detail', pk=load.pk)
    if request.POST.get('consent') != 'on':
        messages.error(request, 'Tick the box to agree before you share your location.')
        return redirect('track_page', offer_pk=offer.pk)
    tracking, _ = Tracking.objects.get_or_create(offer=offer)
    if not tracking.active:
        tracking.active = True
        tracking.started_at = timezone.now()
        tracking.ended_at = None
        tracking.save()
        notify(load.shipper,
               f'{request.user.username} started sharing the truck location for "{load.title}". Watch it live.',
               reverse('track_page', args=[offer.pk]))
    messages.success(request, 'Sharing is on. Keep this page open, and keep your screen on, so the location keeps updating.')
    return redirect('track_page', offer_pk=offer.pk)


@login_required
@require_POST
def stop_tracking(request, offer_pk):
    offer, side = _party_offer(request, offer_pk)
    if side != 'transporter':
        raise Http404
    tracking = Tracking.objects.filter(offer=offer).first()
    if tracking and tracking.active:
        end_tracking(tracking)
        notify(offer.load.shipper,
               f'{request.user.username} stopped sharing the truck location for "{offer.load.title}".',
               reverse('track_page', args=[offer.pk]))
        messages.success(request, 'Sharing stopped.')
    return redirect('track_page', offer_pk=offer.pk)


@login_required
@require_POST
def ask_tracking(request, offer_pk):
    offer, side = _party_offer(request, offer_pk)
    if side != 'shipper':
        raise Http404
    key = f'track_ask_{offer.pk}'
    last = request.session.get(key, 0)
    if time.time() - last < 3600:
        messages.info(request, 'You already asked recently. Give the transporter some time to respond.')
        return redirect('track_page', offer_pk=offer.pk)
    request.session[key] = time.time()
    notify(offer.transporter,
           f'The shipper would like to follow the truck for "{offer.load.title}". '
           f'Open the tracking page and start sharing if you agree.',
           reverse('track_page', args=[offer.pk]))
    messages.success(request, 'The transporter was asked to share the truck location.')
    return redirect('track_page', offer_pk=offer.pk)


@login_required
@require_POST
def ping(request, offer_pk):
    offer, side = _party_offer(request, offer_pk)
    if side != 'transporter':
        return JsonResponse({'ok': False, 'reason': 'not_allowed'}, status=403)
    tracking = Tracking.objects.filter(offer=offer).first()
    if tracking is None or not tracking.active:
        return JsonResponse({'ok': False, 'reason': 'not_active'}, status=409)
    if not can_track(offer):
        end_tracking(tracking)
        return JsonResponse({'ok': False, 'reason': 'ended'}, status=409)

    try:
        body = json.loads(request.body.decode('utf-8'))
        lat = float(body['lat'])
        lng = float(body['lng'])
        accuracy = body.get('accuracy')
        accuracy = float(accuracy) if accuracy is not None else None
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        return JsonResponse({'ok': False, 'reason': 'bad_data'}, status=400)
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return JsonResponse({'ok': False, 'reason': 'bad_data'}, status=400)
    if accuracy is not None and not (math.isfinite(accuracy) and accuracy >= 0):
        accuracy = None

    now = timezone.now()
    if tracking.last_at and (now - tracking.last_at).total_seconds() < MIN_INTERVAL:
        return JsonResponse({'ok': True, 'skipped': True})
    LocationPing.objects.create(tracking=tracking, lat=lat, lng=lng, accuracy=accuracy)
    tracking.last_lat = lat
    tracking.last_lng = lng
    tracking.last_accuracy = accuracy
    tracking.last_at = now
    tracking.save()
    return JsonResponse({'ok': True})


@login_required
def data(request, offer_pk):
    offer, side = _party_offer(request, offer_pk)
    load = offer.load
    tracking = Tracking.objects.filter(offer=offer).first()
    if tracking and tracking.active and not can_track(offer):
        end_tracking(tracking)
    if tracking is None or not tracking.active:
        return JsonResponse({'ok': True, 'active': False, 'status': load.status})

    now = timezone.now()
    age = None
    if tracking.last_at:
        age = int((now - tracking.last_at).total_seconds())
    trail = list(tracking.pings
                 .filter(created_at__gte=now - timedelta(hours=24))
                 .order_by('-created_at').values_list('lat', 'lng')[:300])
    trail.reverse()
    has_position = tracking.last_lat is not None
    return JsonResponse({
        'ok': True,
        'active': True,
        'status': load.status,
        'last': [tracking.last_lat, tracking.last_lng] if has_position else None,
        'accuracy': tracking.last_accuracy,
        'age': age,
        'stale': age is None or age > STALE_SECONDS,
        'km_to_go': km_to_go(load.destination, tracking.last_lat, tracking.last_lng) if has_position else None,
        'trail': trail,
    })