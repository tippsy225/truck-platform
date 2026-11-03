from datetime import date

from django import forms

from .models import Truck


class TruckForm(forms.ModelForm):
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