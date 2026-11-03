from django.contrib import admin, messages
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from .models import KycSubmission, Notification, Profile, Review
from .notify import notify


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'phone', 'both_roles')
    list_filter = ('role',)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'message', 'is_read', 'created_at')
    list_filter = ('is_read',)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('reviewer', 'reviewee', 'stars', 'offer', 'created_at')
    list_filter = ('stars',)


@admin.register(KycSubmission)
class KycSubmissionAdmin(admin.ModelAdmin):
    list_display = ('user', 'doc_type', 'id_number', 'status', 'created_at', 'reviewed_by')
    list_filter = ('status', 'doc_type')
    search_fields = ('user__username', 'id_number')
    actions = ['approve_selected', 'reject_selected']
    fields = ('user', 'doc_type', 'id_number', 'document_links', 'kin_name',
              'kin_relationship', 'kin_phone', 'status', 'review_note',
              'reviewed_by', 'reviewed_at', 'created_at')
    readonly_fields = ('user', 'doc_type', 'id_number', 'document_links', 'kin_name',
                       'kin_relationship', 'kin_phone', 'reviewed_by', 'reviewed_at',
                       'created_at')

    def document_links(self, obj):
        links = []
        for kind, label in (('front', 'Front'), ('back', 'Back'), ('selfie', 'Selfie')):
            if getattr(obj, kind):
                url = reverse('kyc_document', args=[obj.pk, kind])
                links.append(format_html('<a href="{}" target="_blank">{}</a>', url, label))
        if not links:
            return 'No documents'
        return format_html_join(' | ', '{}', ((link,) for link in links))

    document_links.short_description = 'Documents'

    def _tell(self, obj):
        url = reverse('kyc')
        if obj.status == 'approved':
            notify(obj.user, 'Your identity was verified. You now have a Verified badge.', url)
        elif obj.status == 'rejected':
            note = obj.review_note or 'please submit clear photos of your document'
            notify(obj.user, f'Your identity submission was rejected: {note}.', url)

    def save_model(self, request, obj, form, change):
        status_changed = change and 'status' in form.changed_data
        if status_changed:
            obj.reviewed_by = request.user
            obj.reviewed_at = timezone.now()
        super().save_model(request, obj, form, change)
        if status_changed and obj.status in ('approved', 'rejected'):
            self._tell(obj)

    def _review(self, request, queryset, status, note=''):
        done = 0
        for obj in queryset.filter(status='pending'):
            obj.status = status
            obj.review_note = note
            obj.reviewed_by = request.user
            obj.reviewed_at = timezone.now()
            obj.save()
            self._tell(obj)
            done += 1
        self.message_user(request, f'{done} submission(s) {status}.', messages.SUCCESS)

    def approve_selected(self, request, queryset):
        self._review(request, queryset, 'approved')

    approve_selected.short_description = 'Approve selected pending submissions'

    def reject_selected(self, request, queryset):
        self._review(request, queryset, 'rejected',
                     'the photos were unclear or did not match. Please resubmit')

    reject_selected.short_description = 'Reject selected pending submissions'