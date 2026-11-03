from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from loads.models import Load, Offer
from loads.services import run_housekeeping
from trucks.models import Truck

from .forms import AccountForm, RegisterForm


def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'landing.html', {
        'open_loads': Load.objects.filter(status='open').count(),
        'open_trucks': Truck.objects.filter(is_available=True).count(),
    })


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})


@login_required
def dashboard(request):
    run_housekeeping()
    profile = getattr(request.user, 'profile', None)
    role = profile.role if profile else None
    today = timezone.localdate()
    ctx = {'role': role}

    if role == 'shipper':
        loads = Load.objects.filter(shipper=request.user)
        accepted = (Offer.objects.filter(load__shipper=request.user, status='accepted',
                                         load__status='booked').select_related('load'))
        ctx.update(
            total=loads.count(),
            open_count=loads.filter(status='open').count(),
            booked_count=loads.filter(status='booked').count(),
            delivered_count=loads.filter(status='delivered').count(),
            waiting_offers=Offer.objects.filter(load__shipper=request.user,
                                                load__status='open', status='pending').count(),
            fees_to_pay=[o for o in accepted if not o.shipper_paid],
            recent=loads.order_by('-created_at')[:5],
        )

    elif role == 'transporter':
        trucks = Truck.objects.filter(owner=request.user)
        offers = Offer.objects.filter(transporter=request.user)
        accepted = offers.filter(status='accepted', load__status='booked').select_related('load')
        soon = today + timedelta(days=30)
        alerts = []
        for truck in trucks:
            for label, day in (('Insurance', truck.insurance_expiry),
                               ('Roadworthy certificate', truck.roadworthy_expiry)):
                if day and day <= soon:
                    days = (day - today).days
                    if days < 0:
                        text = f'{label} expired on {day:%d %b %Y}. This truck cannot bid until it is updated.'
                    else:
                        text = f'{label} expires in {days} day{"s" if days != 1 else ""} ({day:%d %b %Y}).'
                    alerts.append({'truck': truck, 'text': text, 'expired': days < 0})
        ctx.update(
            fleet=trucks.count(),
            available=trucks.filter(is_available=True).count(),
            active_offers=offers.filter(status__in=['pending', 'countered']).count(),
            delivered_jobs=offers.filter(status='accepted', load__status='delivered').count(),
            turn_offers=offers.filter(status='countered', load__status='open').select_related('load'),
            fees_to_pay=[o for o in accepted if not o.transporter_paid],
            alerts=alerts,
            recent_offers=offers.select_related('load').order_by('-created_at')[:5],
        )

    return render(request, 'accounts/dashboard.html', ctx)


@login_required
def account(request):
    profile = getattr(request.user, 'profile', None)
    if request.method == 'POST':
        form = AccountForm(request.POST)
        if form.is_valid():
            user = request.user
            user.first_name = form.cleaned_data['first_name']
            user.last_name = form.cleaned_data['last_name']
            user.email = form.cleaned_data['email']
            user.save()
            if profile:
                profile.phone = form.cleaned_data['phone']
                profile.save()
            messages.success(request, 'Your details were saved.')
            return redirect('account')
    else:
        form = AccountForm(initial={
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
            'email': request.user.email,
            'phone': profile.phone if profile else '',
        })
    return render(request, 'accounts/account.html', {'form': form, 'profile': profile})


@login_required
@require_POST
def enable_both_roles(request):
    profile = getattr(request.user, 'profile', None)
    if profile:
        profile.both_roles = True
        profile.save()
        messages.success(request, 'Done. Use the switch button in the top bar to change between shipper and transporter.')
    return redirect('account')


@login_required
@require_POST
def switch_role(request):
    profile = getattr(request.user, 'profile', None)
    if profile and profile.both_roles:
        profile.role = 'transporter' if profile.role == 'shipper' else 'shipper'
        profile.save()
        messages.success(request, f'You are now using TruckLink as a {profile.role}.')
    return redirect('dashboard')


@login_required
def notifications(request):
    items = list(request.user.notifications.all()[:50])
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return render(request, 'accounts/notifications.html', {'items': items})