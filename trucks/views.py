from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import TruckForm
from .models import Truck


def _role(user):
    profile = getattr(user, 'profile', None)
    return profile.role if profile else None


@login_required
def truck_list(request):
    if _role(request.user) == 'transporter':
        return redirect('load_list')
    trucks = Truck.objects.filter(is_available=True).order_by('-created_at')
    return render(request, 'trucks/truck_list.html', {'trucks': trucks})


@login_required
def add_truck(request):
    if _role(request.user) != 'transporter':
        return redirect('home')
    if request.method == 'POST':
        form = TruckForm(request.POST)
        if form.is_valid():
            truck = form.save(commit=False)
            truck.owner = request.user
            truck.save()
            return redirect('load_list')
    else:
        form = TruckForm()
    return render(request, 'trucks/truck_form.html', {'form': form})