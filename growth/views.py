from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.notify import notify
from wallet.services import balance

from .billing import BillingError, subscribe
from .dashboard import collect
from .models import Referral, ReferralCode
from .plans import PERIOD_DAYS, PLANS, current_subscription
from .referrals import bonus_amount, get_code


@login_required
def hub(request):
    sub = current_subscription(request.user)
    current_key = sub.plan_key if sub and sub.plan_key in PLANS else 'free'
    plans = []
    for key, plan in PLANS.items():
        plans.append({
            'key': key, 'name': plan['name'], 'price': plan['price'],
            'discount': plan['discount'], 'perks': plan['perks'],
            'current': key == current_key,
            'expires': sub.expires_at if (sub and key == current_key and key != 'free') else None,
        })
    code = get_code(request.user)
    made = request.user.referrals_made.select_related('referred')
    return render(request, 'growth/hub.html', {
        'plans': plans,
        'period': PERIOD_DAYS,
        'balance': balance(request.user),
        'code': code,
        'link': request.build_absolute_uri(reverse('growth_ref', args=[code])),
        'made': made,
        'rewarded': made.filter(status='rewarded').count(),
        'bonus': bonus_amount(),
        'referred_by': Referral.objects.filter(referred=request.user).select_related('referrer').first(),
    })


@login_required
@require_POST
def subscribe_view(request, key):
    try:
        sub = subscribe(request.user, key)
    except BillingError as exc:
        messages.error(request, str(exc))
    else:
        name = PLANS[key]['name']
        notify(request.user, f'You are on the {name} plan until {sub.expires_at:%d %b %Y}.',
               reverse('growth_hub'))
        messages.success(request, f'You are on the {name} plan until {sub.expires_at:%d %b %Y}. '
                                  f'Your platform fees are now lower. (Simulated payment.)')
    return redirect('growth_hub')


def referral_landing(request, code):
    code = code.strip().upper()
    if not ReferralCode.objects.filter(code=code).exists():
        messages.error(request, 'That referral link is not valid.')
        return redirect('growth_hub' if request.user.is_authenticated else 'register')
    if request.user.is_authenticated:
        messages.info(request, 'Referral links are for new members. Share your own link from this page.')
        return redirect('growth_hub')
    request.session['ref_code'] = code
    messages.success(request, 'Referral code applied. Create your account, and you both earn a bonus after your first delivered job.')
    return redirect('register')


@login_required
def owner_dashboard(request):
    if not request.user.is_staff:
        raise Http404
    return render(request, 'growth/owner.html', {'s': collect()})