from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum

from loads.models import Load


class Trip(models.Model):
    STATUS_CHOICES = [('open', 'Open'), ('closed', 'Closed'), ('expired', 'Expired')]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              related_name='trips')
    truck = models.ForeignKey('trucks.Truck', on_delete=models.CASCADE, related_name='trips')
    origin = models.CharField(max_length=100)
    destination = models.CharField(max_length=100)
    via = models.CharField(max_length=200, blank=True)
    departure_date = models.DateField()
    tonnes_available = models.DecimalField(max_digits=6, decimal_places=2)
    price_per_tonne = models.DecimalField(max_digits=8, decimal_places=2)
    negotiable = models.BooleanField(default=True)
    notes = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['departure_date']

    @property
    def stops(self):
        middle = [s.strip() for s in self.via.split(',') if s.strip()]
        return [self.origin] + middle + [self.destination]

    @property
    def tonnes_booked(self):
        total = (self.requests.filter(status='accepted', load__status__in=['booked', 'delivered'])
                 .aggregate(t=Sum('tonnes'))['t'])
        return total or Decimal('0')

    @property
    def tonnes_left(self):
        return self.tonnes_available - self.tonnes_booked

    @property
    def pending_requests(self):
        return self.requests.filter(status='pending').count()

    def __str__(self):
        return f"{self.origin} to {self.destination} on {self.departure_date}"


class SpaceRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Awaiting transporter'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('withdrawn', 'Withdrawn'),
    ]

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='requests')
    shipper = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='space_requests')
    load = models.ForeignKey('loads.Load', null=True, blank=True, on_delete=models.SET_NULL,
                             related_name='space_requests')
    cargo = models.CharField(max_length=100)
    cargo_type = models.CharField(max_length=20, choices=Load.CARGO_CHOICES, default='general')
    pickup = models.CharField(max_length=100)
    dropoff = models.CharField(max_length=100)
    tonnes = models.DecimalField(max_digits=6, decimal_places=2)
    price_per_tonne = models.DecimalField(max_digits=8, decimal_places=2)
    message = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def total_price(self):
        return (self.tonnes * self.price_per_tonne).quantize(Decimal('0.01'))

    def __str__(self):
        return f"{self.shipper.username}: {self.tonnes} t on {self.trip}"