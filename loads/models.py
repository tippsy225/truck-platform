from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models

from trucks.models import Truck


class Load(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('booked', 'Booked'),
        ('delivered', 'Delivered'),
        ('expired', 'Expired'),
    ]
    CARGO_CHOICES = [
        ('general', 'General cargo'),
        ('bulk', 'Bulk'),
        ('perishable', 'Perishable'),
        ('fragile', 'Fragile'),
        ('hazardous', 'Hazardous'),
        ('livestock', 'Livestock'),
    ]
    URGENCY_CHOICES = [
        ('standard', 'Standard (1 to 3 days)'),
        ('urgent', 'Urgent (same day)'),
        ('scheduled', 'Scheduled (fixed date)'),
    ]
    TRUCK_NEEDED_CHOICES = [('any', 'Any truck')] + Truck.TYPE_CHOICES

    shipper = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='loads', null=True, blank=True)
    title = models.CharField(max_length=100)
    pickup = models.CharField(max_length=100)
    destination = models.CharField(max_length=100)
    cargo_type = models.CharField(max_length=20, choices=CARGO_CHOICES, default='general')
    weight_tonnes = models.DecimalField(max_digits=6, decimal_places=2)
    truck_type_needed = models.CharField(max_length=20, choices=TRUCK_NEEDED_CHOICES, default='any')
    offered_price = models.DecimalField(max_digits=10, decimal_places=2)
    urgency = models.CharField(max_length=20, choices=URGENCY_CHOICES, default='standard')
    pickup_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True, default='')
    insured = models.BooleanField(default=False)
    insurance_provider = models.CharField(max_length=100, blank=True, default='')
    coverage_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title}: {self.pickup} to {self.destination}"


class Offer(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Awaiting shipper'),
        ('countered', 'Awaiting transporter'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('withdrawn', 'Withdrawn'),
        ('expired', 'Expired'),
    ]

    load = models.ForeignKey(Load, on_delete=models.CASCADE, related_name='offers')
    transporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                    related_name='offers')
    truck = models.ForeignKey('trucks.Truck', on_delete=models.SET_NULL,
                              null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    message = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def _fee(self, percent):
        fee = self.price * Decimal(str(percent)) / Decimal('100')
        minimum = Decimal(str(settings.PLATFORM_FEE_MINIMUM))
        return max(fee, minimum).quantize(Decimal('0.01'))

    @property
    def shipper_fee(self):
        from growth.plans import apply_discount
        return apply_discount(self._fee(settings.PLATFORM_FEE_PERCENT_SHIPPER), self.load.shipper)

    @property
    def transporter_fee(self):
        from growth.plans import apply_discount
        return apply_discount(self._fee(settings.PLATFORM_FEE_PERCENT_TRANSPORTER), self.transporter)

    @property
    def shipper_paid(self):
        return self.payments.filter(status='paid', payer_role='shipper').exists()

    @property
    def transporter_paid(self):
        return self.payments.filter(status='paid', payer_role='transporter').exists()

    @property
    def fee_paid(self):
        return self.shipper_paid and self.transporter_paid

    @property
    def pay_deadline(self):
        if not self.accepted_at:
            return None
        hours = getattr(settings, 'PAYMENT_DEADLINE_HOURS', 24)
        return self.accepted_at + timedelta(hours=hours)

    def __str__(self):
        return f"${self.price} by {self.transporter.username} for {self.load.title}"


class OfferEvent(models.Model):
    KIND_CHOICES = [
        ('offer', 'Offered'),
        ('counter', 'Countered'),
        ('accept', 'Accepted'),
        ('decline', 'Declined'),
        ('withdraw', 'Withdrawn'),
        ('expire', 'Expired'),
    ]

    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name='events')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                              null=True, blank=True, related_name='offer_events')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.kind} on {self.offer}"


class Payment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('refund_due', 'Refund due'),
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