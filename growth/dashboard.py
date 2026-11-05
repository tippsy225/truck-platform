from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from accounts.models import KycSubmission, Profile
from loads.models import Load, Offer, Payment
from wallet.models import Dispute, Escrow, LedgerEntry

from .models import Referral, Subscription
from .plans import PLANS

ZERO = Decimal('0')


def _sum(queryset, field):
    return queryset.aggregate(t=Sum(field))['t'] or ZERO


def _trend(days=14):
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    loads = {r['d']: r['n'] for r in
             Load.objects.filter(created_at__date__gte=start)
             .annotate(d=TruncDate('created_at')).values('d')
             .annotate(n=Count('id')).order_by()}
    books = {r['d']: r['n'] for r in
             Offer.objects.filter(accepted_at__date__gte=start)
             .annotate(d=TruncDate('accepted_at')).values('d')
             .annotate(n=Count('id')).order_by()}
    peak = max([1] + list(loads.values()) + list(books.values()))
    rows = []
    for i in range(days):
        day = start + timedelta(days=i)
        l, b = loads.get(day, 0), books.get(day, 0)
        rows.append({'label': day.strftime('%d %b'), 'loads': l, 'bookings': b,
                     'loads_pct': int(l * 100 / peak), 'bookings_pct': int(b * 100 / peak)})
    return rows


def collect():
    now = timezone.now()
    since30 = now - timedelta(days=30)

    real_jobs = Offer.objects.filter(status='accepted', load__status__in=['booked', 'delivered'])
    jobs = real_jobs.count()
    offers_total = Offer.objects.count()
    paid = Payment.objects.filter(status='paid')
    disputes_total = Dispute.objects.count()

    active_subs = (Subscription.objects.filter(started_at__lte=now, expires_at__gt=now)
                   .values('plan_key').annotate(n=Count('user', distinct=True)))
    plans = []
    mrr = ZERO
    for row in active_subs:
        plan = PLANS.get(row['plan_key'])
        if plan:
            plans.append({'name': plan['name'], 'n': row['n']})
            mrr += plan['price'] * row['n']

    routes = (real_jobs.values('load__pickup', 'load__destination')
              .annotate(jobs=Count('id'), value=Sum('price')).order_by('-jobs', '-value')[:8])

    return {
        'users_total': User.objects.count(),
        'users_new': User.objects.filter(date_joined__gte=since30).count(),
        'roles': {r['role']: r['n'] for r in Profile.objects.values('role').annotate(n=Count('id'))},
        'verified': KycSubmission.objects.filter(status='approved').values('user').distinct().count(),
        'kyc_pending': KycSubmission.objects.filter(status='pending').count(),
        'loads_by_status': {r['status']: r['n'] for r in Load.objects.values('status').annotate(n=Count('id'))},
        'loads_total': Load.objects.count(),
        'offers_total': offers_total,
        'jobs': jobs,
        'accept_rate': int(round(100 * jobs / offers_total)) if offers_total else 0,
        'gmv': _sum(real_jobs, 'price'),
        'gmv_delivered': _sum(real_jobs.filter(load__status='delivered'), 'price'),
        'fees': _sum(paid, 'amount'),
        'fees_count': paid.count(),
        'refund_due': _sum(Payment.objects.filter(status='refund_due'), 'amount'),
        'escrow_held': _sum(Escrow.objects.filter(status='held'), 'amount'),
        'wallet_total': _sum(LedgerEntry.objects.all(), 'amount'),
        'disputes_open': Dispute.objects.filter(status='open').count(),
        'disputes_total': disputes_total,
        'dispute_rate': int(round(100 * disputes_total / jobs)) if jobs else 0,
        'routes': routes,
        'trend': _trend(),
        'plans': plans,
        'mrr': mrr,
        'referrals': Referral.objects.count(),
        'referrals_rewarded': Referral.objects.filter(status='rewarded').count(),
    }