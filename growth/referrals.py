import secrets
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from accounts.notify import notify
from wallet.models import LedgerEntry

from .models import Referral, ReferralCode

ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def bonus_amount():
    return Decimal(str(getattr(settings, 'REFERRAL_BONUS', '2.00'))).quantize(Decimal('0.01'))


def get_code(user):
    existing = ReferralCode.objects.filter(user=user).first()
    if existing:
        return existing.code
    for _ in range(25):
        code = ''.join(secrets.choice(ALPHABET) for _ in range(7))
        try:
            with transaction.atomic():
                return ReferralCode.objects.create(user=user, code=code).code
        except IntegrityError:
            existing = ReferralCode.objects.filter(user=user).first()
            if existing:
                return existing.code
    raise RuntimeError('Could not create a referral code.')


@transaction.atomic
def reward(referral):
    """Pay both sides once the referred person has completed a first delivered job."""
    ref = Referral.objects.select_for_update().select_related('referrer', 'referred').get(pk=referral.pk)
    if ref.status != 'pending':
        return False
    cap = int(getattr(settings, 'REFERRAL_MAX_REWARDS', 20))
    already = Referral.objects.filter(referrer=ref.referrer, status='rewarded').count()
    ref.rewarded_at = timezone.now()
    url = reverse('growth_hub')
    if already >= cap:
        ref.status = 'capped'
        ref.save()
        return False
    bonus = bonus_amount()
    LedgerEntry.objects.create(
        user=ref.referrer, amount=bonus, kind='referral_bonus',
        note=f'Referral bonus: {ref.referred.username} completed a first job')
    LedgerEntry.objects.create(
        user=ref.referred, amount=bonus, kind='referral_bonus',
        note='Welcome bonus: you completed your first job')
    ref.status = 'rewarded'
    ref.save()
    notify(ref.referrer, f'{ref.referred.username} completed a first job, so you each earned ${bonus} in your wallet.', url)
    notify(ref.referred, f'You completed your first job, so you and {ref.referrer.username} each earned ${bonus} in your wallet.', url)
    return True