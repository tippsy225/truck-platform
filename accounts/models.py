import uuid
from datetime import timedelta

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.db.models import Avg, Count, Exists, OuterRef, Q
from django.utils import timezone


def get_private_storage():
    return FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT)


def kyc_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'bin'
    return f'kyc/{instance.user_id}/{uuid.uuid4().hex}.{ext}'


class Profile(models.Model):
    ROLE_CHOICES = [
        ('shipper', 'Shipper (I have loads)'),
        ('transporter', 'Transporter (I have trucks)'),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    phone = models.CharField(max_length=20, blank=True)
    both_roles = models.BooleanField(default=False)

    @property
    def kyc_status(self):
        latest = self.user.kyc_submissions.first()
        return latest.status if latest else 'none'

    @property
    def is_verified(self):
        return self.kyc_status == 'approved'

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


class KycSubmission(models.Model):
    DOC_CHOICES = [
        ('national_id', 'National ID (Zimbabwe)'),
        ('passport', 'Passport'),
        ('licence', "Driver's licence"),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='kyc_submissions')
    doc_type = models.CharField(max_length=20, choices=DOC_CHOICES, default='national_id')
    id_number = models.CharField(max_length=50)
    front = models.FileField(upload_to=kyc_path, storage=get_private_storage)
    back = models.FileField(upload_to=kyc_path, storage=get_private_storage, blank=True)
    selfie = models.FileField(upload_to=kyc_path, storage=get_private_storage, blank=True)
    kin_name = models.CharField(max_length=100, blank=True)
    kin_relationship = models.CharField(max_length=50, blank=True)
    kin_phone = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    review_note = models.CharField(max_length=255, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='+')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username}: {self.get_doc_type_display()} ({self.status})"


class Review(models.Model):
    offer = models.ForeignKey('loads.Offer', on_delete=models.CASCADE, related_name='reviews')
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name='reviews_given')
    reviewee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name='reviews_received')
    stars = models.PositiveSmallIntegerField()
    comment = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('offer', 'reviewer')

    def __str__(self):
        return f"{self.reviewer.username} rated {self.reviewee.username} {self.stars}/5"


def visible_reviews(user):
    """A review is shown once the other person has also reviewed, or after 14 days."""
    cutoff = timezone.now() - timedelta(days=14)
    reply = Review.objects.filter(offer=OuterRef('offer'), reviewer=OuterRef('reviewee'))
    return (Review.objects.filter(reviewee=user)
            .annotate(has_reply=Exists(reply))
            .filter(Q(has_reply=True) | Q(created_at__lt=cutoff)))


def rating_summary(user):
    data = visible_reviews(user).aggregate(avg=Avg('stars'), n=Count('id'))
    return data['avg'], data['n']