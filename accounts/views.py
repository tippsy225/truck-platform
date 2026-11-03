from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from loads.models import Load, Offer
from loads.services import run_housekeeping
from trucks.models import Truck

from .forms import AccountForm, KycForm, RegisterForm, ReviewForm
from .models import KycSubmission, Review, rating_summary, visible_reviews
from .notify import notify


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


@login_required
def kyc(request):
    latest = request.user.kyc_submissions.first()
    can_submit = latest is None or latest.status == 'rejected'
    form = None
    if can_submit:
        if request.method == 'POST':
            form = KycForm(request.POST, request.FILES)
            if form.is_valid():
                submission = form.save(commit=False)
                submission.user = request.user
                submission.save()
                for staff in User.objects.filter(is_staff=True):
                    notify(staff, f'New identity submission from {request.user.username}.',
                           '/admin/accounts/kycsubmission/')
                messages.success(request, 'Submitted. A reviewer will check your documents soon.')
                return redirect('kyc')
        else:
            form = KycForm()
    return render(request, 'accounts/kyc.html', {
        'form': form, 'latest': latest, 'can_submit': can_submit})


@login_required
def kyc_document(request, pk, kind):
    if kind not in ('front', 'back', 'selfie'):
        raise Http404
    submission = get_object_or_404(KycSubmission, pk=pk)
    if not (request.user.is_staff or submission.user_id == request.user.id):
        raise Http404
    stored = getattr(submission, kind)
    if not stored:
        raise Http404
    response = FileResponse(stored.open('rb'))
    response['Content-Disposition'] = 'inline'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    return response


@login_required
@require_POST
def submit_review(request, offer_pk):
    offer = get_object_or_404(
        Offer.objects.select_related('load', 'load__shipper', 'transporter'),
        pk=offer_pk, status='accepted')
    load = offer.load
    if load.status != 'delivered':
        messages.error(request, 'You can leave a rating once the load is delivered.')
        return redirect('load_detail', pk=load.pk)

    if request.user.id == load.shipper_id:
        reviewee = offer.transporter
    elif request.user.id == offer.transporter_id:
        reviewee = load.shipper
    else:
        raise Http404

    if Review.objects.filter(offer=offer, reviewer=request.user).exists():
        messages.info(request, 'You have already rated this job.')
        return redirect('load_detail', pk=load.pk)

    form = ReviewForm(request.POST)
    if form.is_valid():
        stars = form.cleaned_data['stars']
        Review.objects.create(offer=offer, reviewer=request.user, reviewee=reviewee,
                              stars=stars, comment=form.cleaned_data['comment'].strip())
        notify(reviewee, f'{request.user.username} rated you on "{load.title}". '
                         f'Rate them too to see what they said.',
               reverse('load_detail', args=[load.pk]))
        messages.success(request, 'Thank you. Your rating was saved.')
    else:
        messages.error(request, 'Choose a rating from 1 to 5.')
    return redirect('load_detail', pk=load.pk)


@login_required
def public_profile(request, username):
    person = get_object_or_404(User, username=username)
    profile = getattr(person, 'profile', None)
    avg, count = rating_summary(person)
    reviews = visible_reviews(person).select_related('reviewer', 'offer__load')[:20]
    jobs = (Offer.objects.filter(status='accepted', load__status='delivered')
            .filter(Q(transporter=person) | Q(load__shipper=person)).count())
    return render(request, 'accounts/profile.html', {
        'person': person,
        'profile': profile,
        'verified': bool(profile and profile.is_verified),
        'avg': round(avg, 1) if avg else None,
        'count': count,
        'reviews': reviews,
        'jobs': jobs,
    })