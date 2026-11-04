from decimal import Decimal

from django.utils import timezone

from loads.models import Load

from .models import Trip

DATE_WINDOW_DAYS = 3


def route_fit(stops, pickup, destination):
    """True when both towns are on the route and the pickup comes first."""
    if pickup not in stops or destination not in stops:
        return False
    return stops.index(pickup) < stops.index(destination)


def _score(trip, load):
    stops = trip.stops
    points = 40 if (load.pickup == stops[0] and load.destination == stops[-1]) else 25
    if load.pickup_date is None:
        points += 15
    else:
        gap = abs((load.pickup_date - trip.departure_date).days)
        points += 30 if gap == 0 else 20 if gap == 1 else 10
    left = trip.tonnes_left
    if left > 0:
        use = min(float(load.weight_tonnes) / float(left), 1.0)
        points += int(round(30 * use))
    return points


def trip_fits_load(trip, load):
    if trip.status != 'open' or load.status != 'open':
        return False
    if trip.departure_date < timezone.localdate():
        return False
    if trip.owner_id == load.shipper_id:
        return False
    if not route_fit(trip.stops, load.pickup, load.destination):
        return False
    if load.pickup_date is not None:
        if abs((load.pickup_date - trip.departure_date).days) > DATE_WINDOW_DAYS:
            return False
    if trip.tonnes_left < load.weight_tonnes:
        return False
    if load.truck_type_needed not in ('any', trip.truck.truck_type):
        return False
    return trip.truck.documents_ok


def matches_for_trip(trip, limit=20):
    """Open loads that fit this trip, best first."""
    if trip.status != 'open':
        return []
    stops = trip.stops
    loads = (Load.objects.filter(status='open', pickup__in=stops, destination__in=stops)
             .select_related('shipper'))
    found = [{'load': load, 'trip': trip, 'score': _score(trip, load)}
             for load in loads if trip_fits_load(trip, load)]
    found.sort(key=lambda m: -m['score'])
    return found[:limit]


def matches_for_load(load, limit=20):
    """Open trips that could carry this load, best first."""
    if load.status != 'open':
        return []
    trips = (Trip.objects.filter(status='open', departure_date__gte=timezone.localdate())
             .select_related('truck', 'owner'))
    found = []
    for trip in trips:
        if trip_fits_load(trip, load):
            found.append({
                'trip': trip,
                'load': load,
                'score': _score(trip, load),
                'estimate': (trip.price_per_tonne * load.weight_tonnes).quantize(Decimal('0.01')),
            })
    found.sort(key=lambda m: -m['score'])
    return found[:limit]