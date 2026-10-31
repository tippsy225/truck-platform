from django.conf import settings
from django.db import models


class Truck(models.Model):
    TYPE_CHOICES = [
        ('flatbed', 'Flatbed'),
        ('tipper', 'Tipper'),
        ('tanker', 'Tanker'),
        ('refrigerated', 'Refrigerated'),
        ('box', 'Closed box / lorry'),
        ('lowbed', 'Lowbed'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              related_name='trucks')
    truck_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    capacity_tonnes = models.DecimalField(max_digits=6, decimal_places=2)
    registration_number = models.CharField(max_length=20)
    current_location = models.CharField(max_length=100)
    heading_to = models.CharField(max_length=100, blank=True)
    available_from = models.DateField(null=True, blank=True)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_truck_type_display()} {self.registration_number} ({self.capacity_tonnes}t)"