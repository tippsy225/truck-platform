from decimal import Decimal

from django.conf import settings
from django.db import models


class Load(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('booked', 'Booked'),
        ('delivered', 'Delivered'),
    ]

    shipper = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='loads', null=True, blank=True)
    title = models.CharField(max_length=100)
    pickup = models.CharField(max_length=100)
    destination = models.CharField(max_length=100)
    weight_tonnes = models.DecimalField(max_digits=6, decimal_places=2)
    offered_price = models.DecimalField(max_digits=10, decimal_places=2)
    pickup_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title}: {self.pickup} to {self.destination}"


class Offer(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
    ]

    load = models.ForeignKey(Load, on_delete=models.CASCADE, related_name='offers')
    transporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                    related_name='offers')
    truck = models.ForeignKey('trucks.Truck', on_delete=models.SET_NULL,
                              null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    message = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def _fee(self, percent):
        fee = self.price * Decimal(str(percent)) / Decimal('100')
        minimum = Decimal(str(settings.PLATFORM_FEE_MINIMUM))
        return max(fee, minimum).quantize(Decimal('0.01'))

    @property
    def shipper_fee(self):
        return self._fee(settings.PLATFORM_FEE_PERCENT_SHIPPER)

    @property
    def transporter_fee(self):
        return self._fee(settings.PLATFORM_FEE_PERCENT_TRANSPORTER)

    @property
    def shipper_paid(self):
        return self.payments.filter(status='paid', payer_role='shipper').exists()

    @property
    def transporter_paid(self):
        return self.payments.filter(status='paid', payer_role='transporter').exists()

    @property
    def fee_paid(self):
        return self.shipper_paid and self.transporter_paid

    def __str__(self):
        return f"${self.price} by {self.transporter.username} for {self.load.title}"


class Payment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    ]
    ROLE_CHOICES = [
        ('shipper', 'Shipper'),
        ('transporter', 'Transporter'),
    ]

    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name='payments')
    payer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              related_name='payments')
    payer_role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='shipper')
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    phone = models.CharField(max_length=15)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    poll_url = models.URLField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"${self.amount} {self.payer_role} fee for {self.offer} ({self.status})"