from datetime import date

from django import forms

from loads.pricing import town_choices

from .models import Truck, TruckPhoto
from .photos import PhotoError, process


class TruckForm(forms.ModelForm):
    current_location = forms.ChoiceField(choices=town_choices, label='Current location')

    class Meta:
        model = Truck
        fields = ['truck_type', 'capacity_tonnes', 'registration_number', 'make',
                  'vehicle_model', 'year', 'axle_configuration', 'volume_cbm',
                  'current_location', 'available_from', 'insurance_expiry',
                  'roadworthy_expiry', 'is_available']
        labels = {
            'registration_number': 'Registration plate',
            'capacity_tonnes': 'Capacity (tonnes)',
            'vehicle_model': 'Model',
            'axle_configuration': 'Axle configuration (for example 6x4)',
            'volume_cbm': 'Volume (CBM)',
            'insurance_expiry': 'Insurance expiry',
            'roadworthy_expiry': 'Roadworthy expiry',
        }
        widgets = {
            'available_from': forms.DateInput(attrs={'type': 'date'}),
            'insurance_expiry': forms.DateInput(attrs={'type': 'date'}),
            'roadworthy_expiry': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean_year(self):
        year = self.cleaned_data.get('year')
        if year is not None and not (1980 <= year <= date.today().year + 1):
            raise forms.ValidationError('Enter a valid year.')
        return year


class PhotoForm(forms.Form):
    kind = forms.ChoiceField(choices=TruckPhoto.KIND_CHOICES, label='What does the photo show?')
    image = forms.FileField(
        label='Photo (JPG, PNG or WebP, up to 10 MB)',
        widget=forms.FileInput(attrs={'accept': 'image/jpeg,image/png,image/webp'}))

    def clean_image(self):
        upload = self.cleaned_data['image']
        try:
            self.processed = process(upload)
        except PhotoError as exc:
            raise forms.ValidationError(str(exc))
        return upload