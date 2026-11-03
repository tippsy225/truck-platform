from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from loads.models import Offer
from loads.pricing import TOWNS

from .forms import TruckForm
from .models import Truck


def _role(user):
    profile = getattr(user, 'profile', None)
    return profile.role if profile else None


@login_required
def truck_list(request):
    if _role(request.user) == 'transporter':
        return redirect('load_list')
    today = timezone.localdate()
    selected = {
        'type': request.GET.get('type', ''),
        'location': request.GET.get('location', ''),
        'min': request.GET.get('min', ''),
    }
    trucks = (Truck.objects.filter(is_available=True)
              .exclude(insurance_expiry__lt=today)
              .exclude(roadworthy_expiry__lt=today)
              .select_related('owner'))
    if selected['type']:
        trucks = trucks.filter(truck_type=selected['type'])
    if selected['location']:
        trucks = trucks.filter(current_location=selected['location'])
    if selected['min']:
        try:
            trucks = trucks.filter(capacity_tonnes__gte=Decimal(selected['min']))
        except InvalidOperation:
            pass
    return render(request, 'trucks/truck_list.html', {
        'trucks': trucks.order_by('-created_at'),
        'selected': selected,
        'filtered': any(selected.values()),
        'towns': sorted(TOWNS),
        'type_choices': Truck.TYPE_CHOICES,
    })


@login_required
def my_trucks(request):
    if _role(request.user) != 'transporter':
        return redirect('home')
    trucks = Truck.objects.filter(owner=request.user).order_by('-created_at')
    return render(request, 'trucks/my_trucks.html', {'trucks': trucks})


@login_required
def add_truck(request):
    if _role(request.user) != 'transporter':
        messages.error(request, 'Only transporters can register trucks.')
        return redirect('home')
    if request.method == 'POST':
        form = TruckForm(request.POST)
        if form.is_valid():
            truck = form.save(commit=False)
            truck.owner = request.user
            truck.save()
            messages.success(request, 'Truck registered.')
            return redirect('my_trucks')
    else:
        form = TruckForm()
    return render(request, 'trucks/truck_form.html', {'form': form, 'heading': 'Add a truck'})


@login_required
def edit_truck(request, pk):
    truck = get_object_or_404(Truck, pk=pk, owner=request.user)
    if request.method == 'POST':
        form = TruckForm(request.POST, instance=truck)
        if form.is_valid():
            form.save()
            messages.success(request, 'Truck updated.')
            return redirect('my_trucks')
    else:
        form = TruckForm(instance=truck)
    return render(request, 'trucks/truck_form.html', {
        'form': form, 'heading': f'Edit {truck.registration_number}'})


@login_required
@require_POST
def toggle_truck(request, pk):
    truck = get_object_or_404(Truck, pk=pk, owner=request.user)
    truck.is_available = not truck.is_available
    truck.save()
    messages.success(request, f'{truck.registration_number} is now '
                              f'{"available" if truck.is_available else "marked as not available"}.')
    return redirect('my_trucks')


@login_required
@require_POST
def delete_truck(request, pk):
    truck = get_object_or_404(Truck, pk=pk, owner=request.user)
    if Offer.objects.filter(truck=truck, status='accepted', load__status='booked').exists():
        messages.error(request, 'This truck is assigned to a booked load, so it cannot be deleted yet.')
        return redirect('my_trucks')
    truck.delete()
    messages.success(request, 'Truck deleted.')
    return redirect('my_trucks')