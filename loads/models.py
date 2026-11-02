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

    def __str__(self):
        return f"${self.price} by {self.transporter.username} for {self.load.title}"