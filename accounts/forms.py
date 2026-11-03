from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Profile


class RegisterForm(UserCreationForm):
    role = forms.ChoiceField(choices=Profile.ROLE_CHOICES)
    phone = forms.CharField(max_length=20, required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            Profile.objects.create(
                user=user,
                role=self.cleaned_data['role'],
                phone=self.cleaned_data['phone'],
            )
        return user


class AccountForm(forms.Form):
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)
    phone = forms.CharField(max_length=20, required=False, label='Phone number')

    def clean_phone(self):
        phone = self.cleaned_data['phone'].replace(' ', '')
        digits = phone.lstrip('+')
        if phone and not (digits.isdigit() and 10 <= len(digits) <= 13):
            raise forms.ValidationError('Enter a valid phone number, like 0771234567.')
        return phone