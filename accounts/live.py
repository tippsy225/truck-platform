from django.http import JsonResponse


def live_state(request):
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False}, status=401)
    notes = request.user.notifications
    latest = notes.order_by('-id').first()
    return JsonResponse({
        'ok': True,
        'unread': notes.filter(is_read=False).count(),
        'latest': None if latest is None else {
            'id': latest.pk,
            'message': latest.message,
            'url': latest.url,
            'is_read': latest.is_read,
        },
    })