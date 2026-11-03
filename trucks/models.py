from django.conf import settings
from django.db import models
from django.utils import timezone


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
    make = models.CharField(max_length=50, blank=True, default='')
    vehicle_model = models.CharField(max_length=50, blank=True, default='')
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    axle_configuration = models.CharField(max_length=20, blank=True, default='')
    volume_cbm = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    current_location = models.CharField(max_length=100)
    heading_to = models.CharField(max_length=100, blank=True)
    available_from = models.DateField(null=True, blank=True)
    insurance_expiry = models.DateField(null=True, blank=True)
    roadworthy_expiry = models.DateField(null=True, blank=True)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def _expired(day):
        return day is not None and day < timezone.localdate()

    @property
    def insurance_expired(self):
        return self._expired(self.insurance_expiry)

    @property
    def roadworthy_expired(self):
        return self._expired(self.roadworthy_expiry)

    @property
    def documents_ok(self):
        return not (self.insurance_expired or self.roadworthy_expired)

    def __str__(self):
        return f"{self.get_truck_type_display()} {self.registration_number} ({self.capacity_tonnes}t)"