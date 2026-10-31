from django.db import models


class Load(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('booked', 'Booked'),
        ('delivered', 'Delivered'),
    ]

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