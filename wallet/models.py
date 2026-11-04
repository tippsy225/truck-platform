from django.conf import settings
from django.db import models


class LedgerEntry(models.Model):
    KIND_CHOICES = [
        ('topup', 'Top up (simulated)'),
        ('withdraw', 'Withdrawal (simulated)'),
        ('escrow_hold', 'Moved into escrow'),
        ('escrow_release', 'Paid out of escrow'),
        ('escrow_refund', 'Refunded from escrow'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='ledger_entries')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    note = models.CharField(max_length=200, blank=True)
    offer = models.ForeignKey('loads.Offer', on_delete=models.SET_NULL, null=True,
                              blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name_plural = 'ledger entries'

    def __str__(self):
        return f"{self.user.username} {self.amount} ({self.kind})"


class Escrow(models.Model):
    STATUS_CHOICES = [
        ('held', 'Held in escrow'),
        ('released', 'Released to the transporter'),
        ('refunded', 'Refunded to the shipper'),
        ('split', 'Split between both sides'),
    ]

    offer = models.OneToOneField('loads.Offer', on_delete=models.CASCADE,
                                 related_name='escrow')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='held')
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"${self.amount} for {self.offer} ({self.status})"


class Dispute(models.Model):
    REASON_CHOICES = [
        ('not_delivered', 'The cargo was not delivered'),
        ('damaged', 'The cargo was damaged'),
        ('late', 'Delivery was very late'),
        ('no_show', 'The other side did not show up'),
        ('price', 'Disagreement about price or payment'),
        ('other', 'Something else'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('resolved', 'Resolved'),
    ]
    RESOLUTION_CHOICES = [
        ('release', 'Release the money to the transporter'),
        ('refund', 'Refund the money to the shipper'),
        ('split', 'Split the money 50/50'),
        ('no_escrow', 'Close without moving money'),
    ]

    offer = models.ForeignKey('loads.Offer', on_delete=models.CASCADE,
                              related_name='disputes')
    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                  related_name='disputes_raised')
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    resolution = models.CharField(max_length=20, choices=RESOLUTION_CHOICES, blank=True)
    admin_note = models.CharField(max_length=300, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='+')
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Dispute {self.pk}: {self.get_reason_display()} ({self.status})"


class DisputeMessage(models.Model):
    dispute = models.ForeignKey(Dispute, on_delete=models.CASCADE, related_name='thread')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                               related_name='+')
    body = models.CharField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.author.username}: {self.body[:40]}"