from math import asin, cos, radians, sin, sqrt

from loads.pricing import TOWNS, _rates


def km_between(lat1, lon1, lat2, lon2):
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    h = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * 6371 * asin(sqrt(h))


def km_to_go(destination, lat, lng):
    """Rough road distance left: the straight line to the town times the road factor."""
    point = TOWNS.get(destination)
    if point is None or lat is None or lng is None:
        return None
    return int(round(km_between(lat, lng, point[0], point[1]) * _rates()['road_factor']))