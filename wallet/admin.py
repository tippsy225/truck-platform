from django import forms
from django.contrib import admin, messages

from accounts.notify import notify

from .models import Dispute, DisputeMessage, Escrow, LedgerEntry
from .services import WalletError, resolve_dispute


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LedgerEntry)
class LedgerEntryAdmin(ReadOnlyAdmin):
    list_display = ('created_at', 'user', 'kind', 'amount', 'note')
    list_filter = ('kind',)
    search_fields = ('user__username', 'note')


@admin.register(Escrow)
class EscrowAdmin(ReadOnlyAdmin):
    list_display = ('offer', 'amount', 'status', 'created_at', 'resolved_at')
    list_filter = ('status',)


class DisputeMessageInline(admin.TabularInline):
    model = DisputeMessage
    extra = 1
    fields = ('author', 'body', 'created_at')
    readonly_fields = ('author', 'created_at')


class DisputeAdminForm(forms.ModelForm):
    class Meta:
        model = Dispute
        fields = '__all__'

    def clean(self):
        cleaned = super().clean()
        instance = self.instance
        resolution = cleaned.get('resolution')
        if (instance.pk and instance.status == 'open'
                and resolution in ('release', 'refund', 'split')):
            if not Escrow.objects.filter(offer=instance.offer, status='held').exists():
                raise forms.ValidationError(
                    'There is no money held in escrow for this job. '
                    'Choose "Close without moving money" instead.')
        return cleaned


@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    form = DisputeAdminForm
    list_display = ('id', 'offer', 'raised_by', 'reason', 'status', 'resolution', 'created_at')
    list_filter = ('status', 'reason')
    inlines = [DisputeMessageInline]
    fields = ('offer', 'raised_by', 'reason', 'description', 'escrow_info', 'status',
              'resolution', 'admin_note', 'resolved_by', 'resolved_at', 'created_at')

    def has_add_permission(self, request):
        return False

    def get_readonly_fields(self, request, obj=None):
        base = ['offer', 'raised_by', 'reason', 'description', 'escrow_info',
                'status', 'resolved_by', 'resolved_at', 'created_at']
        if obj is not None and obj.status == 'resolved':
            base += ['resolution', 'admin_note']
        return base

    def escrow_info(self, obj):
        escrow = Escrow.objects.filter(offer=obj.offer).first()
        if not escrow:
            return 'No escrow for this job'
        return f'${escrow.amount} ({escrow.get_status_display()})'

    escrow_info.short_description = 'Escrow'

    def save_model(self, request, obj, form, change):
        if change and obj.status == 'open' and obj.resolution:
            try:
                resolve_dispute(obj, obj.resolution, request.user, obj.admin_note)
            except WalletError as exc:
                self.message_user(request, str(exc), messages.ERROR)
            return
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for removed in formset.deleted_objects:
            removed.delete()
        for message in instances:
            if isinstance(message, DisputeMessage) and message.author_id is None:
                message.author = request.user
                message.save()
                offer = message.dispute.offer
                text = f'A reviewer added a message to the dispute on "{offer.load.title}".'
                url = f'/wallet/disputes/{message.dispute.pk}/'
                notify(offer.load.shipper, text, url)
                notify(offer.transporter, text, url)
            else:
                message.save()
        formset.save_m2m()