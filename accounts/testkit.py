"""Small helpers shared by the automated tests. Not a test file itself."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import Profile
from loads.models import Load, Offer, Payment
from trucks.models import Truck

PASSWORD = 'test-pass-12345'


def make_user(username, role, phone='0771234567', staff=False):
    user = User.objects.create_user(username, password=PASSWORD, is_staff=staff)
    Profile.objects.create(user=user, role=role, phone=phone)
    return user


def make_truck(owner, capacity='20', truck_type='flatbed', **extra):
    today = timezone.localdate()
    data = dict(owner=owner, truck_type=truck_type, capacity_tonnes=Decimal(capacity),
                registration_number='ABC 1234', current_location='Harare',
                insurance_expiry=today + timedelta(days=200),
                roadworthy_expiry=today + timedelta(days=200))
    data.update(extra)
    return Truck.objects.create(**data)


def make_load(shipper, **extra):
    data = dict(shipper=shipper, title='Cement bags', pickup='Harare', destination='Bulawayo',
                weight_tonnes=Decimal('10'), offered_price=Decimal('800'),
                pickup_date=timezone.localdate() + timedelta(days=3))
    data.update(extra)
    return Load.objects.create(**data)


def make_offer(load, transporter, price='700', truck=None, status='pending', **extra):
    if truck is None:
        truck = make_truck(transporter)
    return Offer.objects.create(load=load, transporter=transporter, truck=truck,
                                price=Decimal(price), status=status, **extra)


def pay_fees(offer, shipper=True, transporter=True):
    now = timezone.now()
    if shipper:
        Payment.objects.create(offer=offer, payer=offer.load.shipper, payer_role='shipper',
                               amount=offer.shipper_fee, phone='0771111111',
                               status='paid', paid_at=now)
    if transporter:
        Payment.objects.create(offer=offer, payer=offer.transporter, payer_role='transporter',
                               amount=offer.transporter_fee, phone='0772222222',
                               status='paid', paid_at=now)


def book(load, transporter, price='700', paid='both', accepted_at=None):
    """An accepted offer on a booked load. paid is 'both', 'shipper', 'transporter' or 'none'."""
    offer = make_offer(load, transporter, price=price, status='accepted',
                       accepted_at=accepted_at or timezone.now())
    load.status = 'booked'
    load.save()
    pay_fees(offer, shipper=paid in ('both', 'shipper'), transporter=paid in ('both', 'transporter'))
    return offer


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class BaseTestCase(TestCase):
    # The fast test hasher keeps the test run quick. Real logins still use Django's strong default.
    def setUp(self):
        cache.clear()  # rate limits are kept in the cache, so every test starts fresh