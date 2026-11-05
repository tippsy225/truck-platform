import logging
from datetime import timedelta

from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone

from accounts.notify import notify
from loads.models import Load

from .models import Referral, ReferralCode
from .referrals import reward

log = logging.getLogger(__name__)


@receiver(user_logged_in)
def capture_referral(sender, request, user, **kwargs):
    """A brand new account that arrived through a referral link or typed a code is linked to the referrer."""
    if request is None:
        return
    try:
        if Referral.objects.filter(referred=user).exists():
            return
        if timezone.now() - user.date_joined > timedelta(minutes=30):
            return
        code = (request.POST.get('ref_code') or request.session.get('ref_code') or '').strip().upper()
        if not code:
            return
        owner = ReferralCode.objects.filter(code=code).select_related('user').first()
        if owner is None or owner.user_id == user.id:
            return
        Referral.objects.create(referrer=owner.user, referred=user)
        request.session.pop('ref_code', None)
        notify(owner.user,
               f'{user.username} joined with your referral code. You each get a bonus when they complete their first job.',
               reverse('growth_hub'))
    except Exception:
        log.exception('Could not record a referral')


@receiver(post_save, sender=Load)
def reward_on_delivery(sender, instance, **kwargs):
    if instance.status != 'delivered':
        return
    try:
        offer = instance.offers.filter(status='accepted').select_related('transporter').first()
        if offer is None or instance.shipper is None:
            return
        pairs = ((instance.shipper, offer.transporter), (offer.transporter, instance.shipper))
        for person, other in pairs:
            referral = Referral.objects.filter(referred=person, status='pending').first()
            if referral and referral.referrer_id != other.pk:
                reward(referral)
    except Exception:
        log.exception('Could not process a referral reward')