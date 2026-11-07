from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from loads.models import Offer
from loads.pricing import TOWNS

from .forms import PhotoForm, TruckForm
from .models import Truck, TruckPhoto
from .photos import MAX_PHOTOS


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
              .select_related('owner').prefetch_related('photos'))
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
def truck_detail(request, pk):
    truck = get_object_or_404(Truck.objects.select_related('owner').prefetch_related('photos'), pk=pk)
    is_owner = truck.owner_id == request.user.id
    # The plate is shown to the owner, and to a shipper who has booked this truck.
    can_see_plate = is_owner or Offer.objects.filter(
        truck=truck, status='accepted', load__shipper=request.user).exists()
    return render(request, 'trucks/truck_detail.html', {
        'truck': truck, 'is_owner': is_owner, 'can_see_plate': can_see_plate,
        'photos': list(truck.photos.all()),
    })


@login_required
def my_trucks(request):
    if _role(request.user) != 'transporter':
        return redirect('home')
    trucks = Truck.objects.filter(owner=request.user).prefetch_related('photos').order_by('-created_at')
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
            messages.success(request, 'Truck registered. Now add photos so cargo owners can see it.')
            return redirect('truck_photos', pk=truck.pk)
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


@login_required
def truck_photos(request, pk):
    truck = get_object_or_404(Truck, pk=pk, owner=request.user)
    photos = list(truck.photos.all())
    if request.method == 'POST':
        form = PhotoForm(request.POST, request.FILES)
        if len(photos) >= MAX_PHOTOS:
            messages.error(request, f'A truck can have up to {MAX_PHOTOS} photos. Delete one to add another.')
            return redirect('truck_photos', pk=truck.pk)
        if form.is_valid():
            main, thumb = form.processed
            photo = TruckPhoto(truck=truck, kind=form.cleaned_data['kind'])
            photo.image.save('photo.jpg', main, save=False)
            photo.thumb.save('thumb.jpg', thumb, save=False)
            photo.save()
            messages.success(request, 'Photo added. Cargo owners can now see it.')
            return redirect('truck_photos', pk=truck.pk)
    else:
        form = PhotoForm()
    return render(request, 'trucks/photos.html', {
        'truck': truck, 'photos': photos, 'form': form,
        'max_photos': MAX_PHOTOS, 'room': len(photos) < MAX_PHOTOS,
    })


@login_required
@require_POST
def delete_photo(request, pk, photo_pk):
    photo = get_object_or_404(TruckPhoto, pk=photo_pk, truck__pk=pk, truck__owner=request.user)
    photo.delete()
    messages.success(request, 'Photo deleted.')
    return redirect('truck_photos', pk=pk)


@login_required
def photo_file(request, photo_pk, size):
    """Truck photos are shown only to people who are logged in."""
    if size not in ('thumb', 'full'):
        raise Http404
    photo = get_object_or_404(TruckPhoto, pk=photo_pk)
    stored = photo.thumb if size == 'thumb' else photo.image
    try:
        handle = stored.open('rb')
    except (FileNotFoundError, ValueError):
        raise Http404
    response = FileResponse(handle, content_type='image/jpeg')
    response['Content-Disposition'] = 'inline'
    response['Cache-Control'] = 'private, max-age=86400'
    response['X-Content-Type-Options'] = 'nosniff'
    return response