from decimal import Decimal

from django.utils import timezone

PERIOD_DAYS = 30

# Placeholder prices and discounts. Change them here.
PLANS = {
    'free': {
        'name': 'Free',
        'price': Decimal('0'),
        'discount': 0,
        'perks': ['Post loads, send offers and book space', 'Standard platform fees'],
    },
    'pro': {
        'name': 'Pro',
        'price': Decimal('9'),
        'discount': 25,
        'perks': ['25 percent off the platform fee on every job'],
    },
    'business': {
        'name': 'Business',
        'price': Decimal('24'),
        'discount': 50,
        'perks': ['50 percent off the platform fee on every job'],
    },
}


def current_subscription(user):
    from .models import Subscription
    if user is None or not getattr(user, 'is_authenticated', False):
        return None
    now = timezone.now()
    return (Subscription.objects
            .filter(user=user, started_at__lte=now, expires_at__gt=now)
            .order_by('-expires_at').first())


def current_plan_key(user):
    sub = current_subscription(user)
    if sub and sub.plan_key in PLANS:
        return sub.plan_key
    return 'free'


def discount_percent(user):
    return PLANS[current_plan_key(user)]['discount']


def apply_discount(fee, user):
    """Lower a platform fee according to the user's plan."""
    if user is None:
        return fee
    percent = discount_percent(user)
    if percent <= 0:
        return fee
    return (fee * (Decimal(100) - Decimal(percent)) / Decimal(100)).quantize(Decimal('0.01'))