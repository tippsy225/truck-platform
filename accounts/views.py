from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from loads.models import Load
from trucks.models import Truck

from .forms import RegisterForm


def home(request):
    if request.user.is_authenticated:
        profile = getattr(request.user, 'profile', None)
        if profile and profile.role == 'shipper':
            return redirect('truck_list')
        return redirect('load_list')
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
def notifications(request):
    items = list(request.user.notifications.all()[:50])
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return render(request, 'accounts/notifications.html', {'items': items})