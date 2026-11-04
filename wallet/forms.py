from decimal import Decimal

from django import forms

from .models import Dispute


class TopUpForm(forms.Form):
    amount = forms.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal('1'),
                                max_value=Decimal('5000'), label='Amount (USD)')


class WithdrawForm(forms.Form):
    amount = forms.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('1'),
                                label='Amount (USD)')


class DisputeForm(forms.Form):
    reason = forms.ChoiceField(choices=Dispute.REASON_CHOICES, label='What went wrong?')
    description = forms.CharField(
        min_length=20, max_length=1000, label='Describe what happened',
        widget=forms.Textarea(attrs={'rows': 5}),
        help_text='At least 20 characters. Include dates and what was agreed.')


class DisputeMessageForm(forms.Form):
    body = forms.CharField(max_length=1000, label='Add a message',
                           widget=forms.Textarea(attrs={'rows': 3}))