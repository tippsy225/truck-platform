from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import APIException


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'This action conflicts with the current state.'
    default_code = 'conflict'


def role_of(user):
    profile = getattr(user, 'profile', None)
    return profile.role if profile else None


def needs_verification(user):
    """True when the REQUIRE_VERIFICATION switch is on and this user is not verified."""
    if not getattr(settings, 'REQUIRE_VERIFICATION', False):
        return False
    if user.is_staff:
        return False
    profile = getattr(user, 'profile', None)
    return not (profile and profile.is_verified)


def accepted_offer(load):
    return load.offers.filter(status='accepted').select_related('transporter').first()


def side_of(user, load, offer):
    """'shipper' or 'transporter' when the user is a party to the booking, otherwise None."""
    if user.id == load.shipper_id:
        return 'shipper'
    if offer is not None and user.id == offer.transporter_id:
        return 'transporter'
    return None