from django import forms
from django.utils import timezone

from .models import Load, Offer


class LoadForm(forms.ModelForm):
    class Meta:
        model = Load
        fields = ['title', 'pickup', 'destination', 'weight_tonnes',
                  'offered_price', 'pickup_date']
        widgets = {'pickup_date': forms.DateInput(attrs={'type': 'date'})}

    def clean_pickup_date(self):
        date = self.cleaned_data.get('pickup_date')
        if date and date < timezone.localdate():
            raise forms.ValidationError('Pickup date cannot be in the past.')
        return date


class OfferForm(forms.ModelForm):
    class Meta:
        model = Offer
        fields = ['price', 'truck', 'message']

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields['truck'].queryset = user.trucks.all()
        self.fields['truck'].required = False