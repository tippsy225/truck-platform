from decimal import Decimal

from django import forms
from django.utils import timezone

from loads.models import Load
from loads.pricing import TOWNS, town_choices
from trucks.models import Truck

from .matching import route_fit
from .models import Trip


class TripForm(forms.ModelForm):
    origin = forms.ChoiceField(choices=town_choices, label='Leaving from')
    destination = forms.ChoiceField(choices=town_choices, label='Going to')
    via = forms.CharField(
        required=False, max_length=200, label='Stops along the way',
        help_text='Towns on the route, in order, separated by commas. For example: Kwekwe, Gweru')

    class Meta:
        model = Trip
        fields = ['truck', 'origin', 'destination', 'via', 'departure_date',
                  'tonnes_available', 'price_per_tonne', 'negotiable', 'notes']
        labels = {
            'departure_date': 'Departure date',
            'tonnes_available': 'Tonnes of space to sell',
            'price_per_tonne': 'Price per tonne (USD)',
            'negotiable': 'Price is negotiable, shippers may propose a lower price',
            'notes': 'Notes (optional)',
        }
        widgets = {'departure_date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        trucks = user.trucks.all() if user is not None else Truck.objects.none()
        self.fields['truck'].queryset = trucks
        self.fields['truck'].empty_label = 'Choose one of your trucks'

    def clean_truck(self):
        truck = self.cleaned_data['truck']
        if truck.insurance_expired:
            raise forms.ValidationError("This truck's insurance has expired. Update it first.")
        if truck.roadworthy_expired:
            raise forms.ValidationError("This truck's roadworthy certificate has expired. Update it first.")
        return truck

    def clean_via(self):
        lookup = {name.lower(): name for name in TOWNS}
        stops, unknown = [], []
        for part in self.cleaned_data.get('via', '').split(','):
            part = part.strip()
            if not part:
                continue
            name = lookup.get(part.lower())
            if name is None:
                unknown.append(part)
            elif name not in stops:
                stops.append(name)
        if unknown:
            raise forms.ValidationError(
                'Unknown town: ' + ', '.join(unknown) + '. Use towns from the dropdown lists, separated by commas.')
        return ', '.join(stops)

    def clean_departure_date(self):
        day = self.cleaned_data['departure_date']
        if day < timezone.localdate():
            raise forms.ValidationError('The departure date cannot be in the past.')
        return day

    def clean_tonnes_available(self):
        value = self.cleaned_data['tonnes_available']
        if value <= 0:
            raise forms.ValidationError('Enter a number of tonnes above zero.')
        return value

    def clean_price_per_tonne(self):
        value = self.cleaned_data['price_per_tonne']
        if value <= 0:
            raise forms.ValidationError('Enter a price above zero.')
        return value

    def clean(self):
        cleaned = super().clean()
        origin = cleaned.get('origin')
        destination = cleaned.get('destination')
        if origin and origin == destination:
            self.add_error('destination', 'The destination must be a different town from the start.')
        via = [s for s in cleaned.get('via', '').split(', ') if s]
        if origin in via or destination in via:
            self.add_error('via', 'The stops should not include the start or the end town.')
        truck = cleaned.get('truck')
        tonnes = cleaned.get('tonnes_available')
        if truck and tonnes is not None and tonnes > truck.capacity_tonnes:
            self.add_error('tonnes_available', f'This truck carries up to {truck.capacity_tonnes} t.')
        return cleaned


class SpaceRequestForm(forms.Form):
    cargo = forms.CharField(max_length=100, label='What are you moving?')
    cargo_type = forms.ChoiceField(choices=Load.CARGO_CHOICES, label='Cargo type')
    pickup = forms.ChoiceField(label='Pickup point')
    dropoff = forms.ChoiceField(label='Drop-off point')
    tonnes = forms.DecimalField(max_digits=6, decimal_places=2, min_value=Decimal('0.1'),
                                label='Tonnes')
    price_per_tonne = forms.DecimalField(max_digits=8, decimal_places=2,
                                         min_value=Decimal('0.01'),
                                         label='Your price per tonne (USD)')
    message = forms.CharField(max_length=200, required=False,
                              label='Message to the transporter')

    def __init__(self, *args, trip=None, load=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.trip = trip
        stops = trip.stops
        self.fields['pickup'].choices = [(s, s) for s in stops[:-1]]
        self.fields['dropoff'].choices = [(s, s) for s in stops[1:]]
        self.initial.setdefault('price_per_tonne', trip.price_per_tonne)
        if not trip.negotiable:
            self.fields['price_per_tonne'].disabled = True
            self.initial['price_per_tonne'] = trip.price_per_tonne
        if load is not None:
            self.initial.update(cargo=load.title, cargo_type=load.cargo_type,
                                pickup=load.pickup, dropoff=load.destination,
                                tonnes=load.weight_tonnes)
            for name in ('cargo', 'cargo_type', 'pickup', 'dropoff', 'tonnes'):
                self.fields[name].disabled = True

    def clean(self):
        cleaned = super().clean()
        pickup = cleaned.get('pickup')
        dropoff = cleaned.get('dropoff')
        tonnes = cleaned.get('tonnes')
        if pickup and dropoff and not route_fit(self.trip.stops, pickup, dropoff):
            self.add_error('dropoff', 'The drop-off must come after the pickup on this route.')
        if tonnes is not None and tonnes > self.trip.tonnes_left:
            self.add_error('tonnes', f'Only {self.trip.tonnes_left} t are free on this trip.')
        return cleaned