from datetime import timedelta
from statistics import median

from django.utils import timezone

from .models import Offer
from .pricing import TOWNS, _rates, distance_km

WINDOW_DAYS = 180        # only recent agreed jobs count
MIN_ROUTE_SAMPLES = 3    # agreed jobs needed on the same route before we trust them
MIN_ALL_SAMPLES = 5      # agreed jobs needed across all routes
FULL_TRUST_AT = 10       # jobs at which the learned price gets its maximum weight
MAX_WEIGHT = 0.7         # the learned price never counts for more than 70 percent


def _round5(value):
    return int(round(value / 5.0) * 5)


def _agreed_rates(pickup, destination):
    """Dollars per tonne-kilometre on jobs that were really agreed on the platform."""
    cutoff = timezone.now() - timedelta(days=WINDOW_DAYS)
    offers = (Offer.objects
              .filter(status='accepted', load__status__in=['booked', 'delivered'],
                      accepted_at__gte=cutoff)
              .select_related('load'))
    on_route, everywhere = [], []
    for offer in offers:
        load = offer.load
        if (load.pickup not in TOWNS or load.destination not in TOWNS
                or load.pickup == load.destination):
            continue
        tonnes = float(load.weight_tonnes)
        km = distance_km(load.pickup, load.destination)
        if tonnes <= 0 or km <= 0:
            continue
        rate = float(offer.price) / (km * tonnes)
        everywhere.append(rate)
        if {load.pickup, load.destination} == {pickup, destination}:
            on_route.append(rate)
    return on_route, everywhere


def refine(result, pickup, destination, tonnes):
    """Take the formula's answer and blend in what real jobs on the platform cost."""
    on_route, everywhere = _agreed_rates(pickup, destination)
    if len(on_route) >= MIN_ROUTE_SAMPLES:
        rates, scope = on_route, 'this route'
    elif len(everywhere) >= MIN_ALL_SAMPLES:
        rates, scope = everywhere, 'all routes'
    else:
        known = len(everywhere)
        plural = '' if known == 1 else 's'
        result.update(
            basis='formula', samples=known,
            note=f'Based on distance and weight. The platform has {known} agreed job{plural} '
                 f'to learn from so far, so there is no market data yet.')
        return result

    settings_ = _rates()
    learned = median(rates) * result['distance_km'] * float(tonnes)
    n = len(rates)
    weight = min(n / FULL_TRUST_AT, 1.0) * MAX_WEIGHT
    blended = (1 - weight) * result['suggested'] + weight * learned
    blended = max(blended, settings_['minimum'])
    spread = settings_['range']
    plural = '' if n == 1 else 's'
    result.update(
        suggested=_round5(blended),
        low=_round5(blended * (1 - spread)),
        high=_round5(blended * (1 + spread)),
        basis='learned', samples=n,
        note=f'Adjusted using {n} agreed job{plural} on {scope} from the last {WINDOW_DAYS} days.')
    return result