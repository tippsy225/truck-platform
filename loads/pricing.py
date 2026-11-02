from math import asin, cos, radians, sin, sqrt

from django.conf import settings

# Approximate coordinates (latitude, longitude). Add more towns here any time.
TOWNS = {
    'Harare': (-17.8292, 31.0522),
    'Bulawayo': (-20.1500, 28.5800),
    'Beitbridge': (-22.2167, 30.0000),
    'Bindura': (-17.3000, 31.3333),
    'Binga': (-17.6167, 27.3333),
    'Chegutu': (-18.1333, 30.1500),
    'Chimanimani': (-19.8000, 32.8667),
    'Chinhoyi': (-17.3667, 30.2000),
    'Chipinge': (-20.1883, 32.6236),
    'Chiredzi': (-21.0500, 31.6667),
    'Chirundu': (-16.0333, 28.8500),
    'Chitungwiza': (-18.0127, 31.0756),
    'Gokwe': (-18.2167, 28.9333),
    'Gweru': (-19.4500, 29.8167),
    'Hwange': (-18.3667, 26.5000),
    'Kadoma': (-18.3333, 29.9167),
    'Kariba': (-16.5167, 28.8000),
    'Karoi': (-16.8167, 29.6833),
    'Kwekwe': (-18.9281, 29.8149),
    'Lupane': (-18.9333, 27.8000),
    'Marondera': (-18.1853, 31.5519),
    'Masvingo': (-20.0744, 30.8328),
    'Mt Darwin': (-16.7667, 31.5833),
    'Mutare': (-18.9707, 32.6709),
    'Mvurwi': (-17.0333, 30.8500),
    'Norton': (-17.8833, 30.7000),
    'Nyamapanda': (-16.9667, 32.8667),
    'Plumtree': (-20.4833, 27.8167),
    'Redcliff': (-19.0333, 29.7833),
    'Rusape': (-18.5333, 32.1167),
    'Ruwa': (-17.8903, 31.2437),
    'Shamva': (-17.3167, 31.5667),
    'Shurugwi': (-19.6667, 30.0000),
    'Triangle': (-21.0333, 31.4500),
    'Victoria Falls': (-17.9243, 25.8572),
    'Zvishavane': (-20.3333, 30.0333),
}

# Placeholder rates in US dollars. Replace with real quotes from transporters.
DEFAULTS = {
    'road_factor': 1.2,      # road distance is about 1.2 times the straight line
    'base': 30.0,            # fixed cost per job
    'per_km': 0.45,          # cost per km, whatever the weight
    'per_tonne_km': 0.025,   # extra cost per tonne per km
    'minimum': 50.0,         # never suggest less than this
    'range': 0.15,           # low and high are 15% below and above
}


def _rates():
    rates = dict(DEFAULTS)
    rates.update(getattr(settings, 'PRICING', {}))
    return rates


def town_choices():
    return [('', 'Choose a town')] + [(name, name) for name in sorted(TOWNS)]


def distance_km(pickup, destination):
    lat1, lon1 = TOWNS[pickup]
    lat2, lon2 = TOWNS[destination]
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    h = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    straight = 2 * 6371 * asin(sqrt(h))
    return int(round(straight * _rates()['road_factor']))


def _round5(value):
    return int(round(value / 5.0) * 5)


def suggest_price(pickup, destination, tonnes):
    if pickup not in TOWNS or destination not in TOWNS or pickup == destination:
        return None
    if tonnes <= 0:
        return None
    rates = _rates()
    km = distance_km(pickup, destination)
    price = rates['base'] + km * (rates['per_km'] + tonnes * rates['per_tonne_km'])
    price = max(price, rates['minimum'])
    return {
        'distance_km': km,
        'suggested': _round5(price),
        'low': _round5(price * (1 - rates['range'])),
        'high': _round5(price * (1 + rates['range'])),
    }