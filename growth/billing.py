from datetime import timedelta

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from wallet.models import LedgerEntry
from wallet.services import balance

from .models import Subscription
from .plans import PERIOD_DAYS, PLANS, current_subscription


class BillingError(Exception):
    pass


@transaction.atomic
def subscribe(user, key):
    plan = PLANS.get(key)
    if plan is None or plan['price'] <= 0:
        raise BillingError('Choose a paid plan.')
    User.objects.select_for_update().get(pk=user.pk)
    price = plan['price']
    available = balance(user)
    if available < price:
        raise BillingError(
            f'Your wallet has ${available}, but the {plan["name"]} plan costs ${price}. Top up your wallet first.')

    now = timezone.now()
    current = current_subscription(user)
    if current and current.plan_key == key:
        start = current.expires_at          # renewing: add time after the current period
    else:
        # Changing plan: the old plan ends now. There is no refund for unused days.
        Subscription.objects.filter(user=user, expires_at__gt=now).update(expires_at=now)
        start = now

    sub = Subscription.objects.create(
        user=user, plan_key=key, started_at=start,
        expires_at=start + timedelta(days=PERIOD_DAYS), price_paid=price)
    LedgerEntry.objects.create(
        user=user, amount=-price, kind='subscription',
        note=f'{plan["name"]} plan, {PERIOD_DAYS} days')
    return sub