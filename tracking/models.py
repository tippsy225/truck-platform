from django.db import models


class Tracking(models.Model):
    offer = models.OneToOneField('loads.Offer', on_delete=models.CASCADE,
                                 related_name='tracking')
    active = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    last_lat = models.FloatField(null=True, blank=True)
    last_lng = models.FloatField(null=True, blank=True)
    last_accuracy = models.FloatField(null=True, blank=True)
    last_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Tracking for {self.offer} ({'on' if self.active else 'off'})"


class LocationPing(models.Model):
    tracking = models.ForeignKey(Tracking, on_delete=models.CASCADE, related_name='pings')
    lat = models.FloatField()
    lng = models.FloatField()
    accuracy = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.lat:.4f}, {self.lng:.4f} at {self.created_at:%d %b %H:%M}"