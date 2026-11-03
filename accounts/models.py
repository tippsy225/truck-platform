from django.conf import settings
from django.db import models


class Profile(models.Model):
    ROLE_CHOICES = [
        ('shipper', 'Shipper (I have loads)'),
        ('transporter', 'Transporter (I have trucks)'),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    phone = models.CharField(max_length=20, blank=True)
    both_roles = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='notifications')
    message = models.CharField(max_length=255)
    url = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username}: {self.message[:40]}"