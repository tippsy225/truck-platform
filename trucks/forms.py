from django import forms
from .models import Truck


class TruckForm(forms.ModelForm):
    class Meta:
        model = Truck
        fields = ['truck_type', 'capacity_tonnes', 'registration_number',
                  'current_location', 'available_from', 'is_available']
        widgets = {'available_from': forms.DateInput(attrs={'type': 'date'})}