from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

from .storage import get_photo_storage, photo_path


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


class TruckPhoto(models.Model):
    KIND_CHOICES = [
        ('front', 'Front'),
        ('side', 'Side'),
        ('back', 'Back'),
        ('cargo', 'Cargo bed or body'),
        ('other', 'Other'),
    ]

    truck = models.ForeignKey(Truck, on_delete=models.CASCADE, related_name='photos')
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default='side')
    image = models.ImageField(upload_to=photo_path, storage=get_photo_storage)
    thumb = models.ImageField(upload_to=photo_path, storage=get_photo_storage)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def __str__(self):
        return f"{self.get_kind_display()} photo of {self.truck}"


@receiver(post_delete, sender=TruckPhoto)
def remove_photo_files(sender, instance, **kwargs):
    """Deleting a photo, or a whole truck, also deletes the picture files from disk."""
    for stored in (instance.image, instance.thumb):
        if stored and stored.name:
            stored.delete(save=False)