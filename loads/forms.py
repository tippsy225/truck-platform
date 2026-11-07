from decimal import Decimal

from django import forms
from django.utils import timezone

from trucks.models import Truck
from trucks.photos import photo_requirement_message

from .models import Load, Offer
from .pricing import town_choices


class LoadForm(forms.ModelForm):
    pickup = forms.ChoiceField(choices=town_choices)
    destination = forms.ChoiceField(choices=town_choices)

    class Meta:
        model = Load
        fields = ['title', 'pickup', 'destination', 'cargo_type', 'weight_tonnes',
                  'truck_type_needed', 'offered_price', 'urgency', 'pickup_date',
                  'description', 'insured', 'insurance_provider', 'coverage_amount']
        labels = {
            'title': 'What are you moving?',
            'weight_tonnes': 'Weight (tonnes)',
            'truck_type_needed': 'Truck type needed',
            'offered_price': 'Your price (USD)',
            'cargo_type': 'Cargo type',
            'insured': 'Insure this cargo',
            'insurance_provider': 'Insurance provider',
            'coverage_amount': 'Coverage amount (USD)',
        }
        widgets = {
            'pickup_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_pickup_date(self):
        date = self.cleaned_data.get('pickup_date')
        if date and date < timezone.localdate():
            raise forms.ValidationError('Pickup date cannot be in the past.')
        return date

    def clean(self):
        cleaned = super().clean()
        pickup = cleaned.get('pickup')
        if pickup and pickup == cleaned.get('destination'):
            self.add_error('destination', 'The destination must be a different town from the pickup.')
        if cleaned.get('urgency') == 'scheduled' and not cleaned.get('pickup_date'):
            self.add_error('pickup_date', 'Choose a pickup date for a scheduled load.')
        if cleaned.get('insured') and not cleaned.get('insurance_provider'):
            self.add_error('insurance_provider', 'Enter the insurance provider.')
        return cleaned


class OfferForm(forms.ModelForm):
    class Meta:
        model = Offer
        fields = ['price', 'truck', 'message']
        labels = {'price': 'Your price (USD)', 'truck': 'Truck', 'message': 'Message to the shipper'}

    def __init__(self, *args, user=None, load=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.load = load
        trucks = user.trucks.all() if user is not None else Truck.objects.none()
        self.fields['truck'].queryset = trucks
        self.fields['truck'].required = True
        self.fields['truck'].empty_label = 'Choose one of your trucks'

    def clean_price(self):
        price = self.cleaned_data['price']
        if price <= 0:
            raise forms.ValidationError('Enter a price above zero.')
        return price

    def clean_truck(self):
        truck = self.cleaned_data['truck']
        if truck.insurance_expired:
            raise forms.ValidationError('This truck\'s insurance has expired. Update the truck before you bid.')
        if truck.roadworthy_expired:
            raise forms.ValidationError('This truck\'s roadworthy certificate has expired. Update the truck before you bid.')
        problem = photo_requirement_message(truck)
        if problem:
            raise forms.ValidationError(problem)
        load = self.load
        if load is not None:
            if truck.capacity_tonnes < load.weight_tonnes:
                raise forms.ValidationError(
                    f'This truck carries {truck.capacity_tonnes} t, but the load weighs {load.weight_tonnes} t.')
            if load.truck_type_needed not in ('any', truck.truck_type):
                raise forms.ValidationError(
                    f'This load needs a {load.get_truck_type_needed_display().lower()} truck.')
        return truck


class CounterForm(forms.Form):
    price = forms.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))


class PaymentForm(forms.Form):
    phone = forms.CharField(max_length=15, label='EcoCash number')

    def clean_phone(self):
        phone = self.cleaned_data['phone'].replace(' ', '')
        if not (phone.isdigit() and len(phone) == 10 and phone.startswith('07')):
            raise forms.ValidationError('Enter a 10-digit number like 0771234567.')
        return phone