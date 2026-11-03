from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import KycSubmission, Profile

MAX_UPLOAD = 5 * 1024 * 1024
IMAGE_EXT = ('jpg', 'jpeg', 'png')
DOC_EXT = IMAGE_EXT + ('pdf',)


def _check_file(upload, allowed):
    name = upload.name
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if ext not in allowed:
        raise forms.ValidationError('Upload a file of type: ' + ', '.join(allowed) + '.')
    if upload.size > MAX_UPLOAD:
        raise forms.ValidationError('The file must be 5 MB or smaller.')


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


class KycForm(forms.ModelForm):
    class Meta:
        model = KycSubmission
        fields = ['doc_type', 'id_number', 'front', 'back', 'selfie',
                  'kin_name', 'kin_relationship', 'kin_phone']
        labels = {
            'doc_type': 'Document type',
            'id_number': 'ID or passport number',
            'front': 'Front of the document (JPG, PNG or PDF, up to 5 MB)',
            'back': 'Back of the document (optional, JPG or PNG)',
            'selfie': 'Selfie holding your document (recommended, JPG or PNG)',
            'kin_name': 'Next of kin: full name',
            'kin_relationship': 'Next of kin: relationship',
            'kin_phone': 'Next of kin: phone number',
        }

    def clean_id_number(self):
        value = self.cleaned_data['id_number'].strip()
        if len(value) < 5:
            raise forms.ValidationError('Enter the full document number.')
        return value

    def clean_front(self):
        upload = self.cleaned_data.get('front')
        if upload:
            _check_file(upload, DOC_EXT)
        return upload

    def clean_back(self):
        upload = self.cleaned_data.get('back')
        if upload:
            _check_file(upload, IMAGE_EXT)
        return upload

    def clean_selfie(self):
        upload = self.cleaned_data.get('selfie')
        if upload:
            _check_file(upload, IMAGE_EXT)
        return upload


class ReviewForm(forms.Form):
    stars = forms.TypedChoiceField(
        choices=[(5, '5 - Excellent'), (4, '4 - Good'), (3, '3 - Fair'),
                 (2, '2 - Poor'), (1, '1 - Very poor')],
        coerce=int, label='Your rating')
    comment = forms.CharField(max_length=300, required=False, label='Comment (optional)',
                              widget=forms.Textarea(attrs={'rows': 3}))