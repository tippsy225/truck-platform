from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .backends import deliver
from .models import AlertPreference, OutboxMessage
from .phone import to_e164


@login_required
def alerts(request):
    pref, _ = AlertPreference.objects.get_or_create(user=request.user)
    profile = getattr(request.user, 'profile', None)

    if request.method == 'POST':
        channel = request.POST.get('channel', 'none')
        if channel not in dict(AlertPreference.CHANNEL_CHOICES):
            channel = 'none'
        phone = request.POST.get('phone', '').strip()
        e164 = to_e164(phone)
        if channel != 'none' and e164 is None:
            messages.error(request, 'Enter a valid Zimbabwean mobile number, like 0771234567, to get phone alerts.')
            return redirect('alerts')
        pref.channel = channel
        pref.phone = phone
        pref.save()
        if request.POST.get('action') == 'test' and channel != 'none':
            message = deliver(request.user, channel, e164,
                              'TruckLink: this is a test alert. You will get messages like this '
                              'when something needs your attention.')
            if message.status == 'sent':
                messages.success(request, 'Test message sent.')
            elif message.status == 'queued':
                messages.info(request, 'Test message recorded below. No provider is connected, so nothing was sent.')
            else:
                messages.error(request, f'The test message did not go out: {message.detail}')
        elif channel == 'none':
            messages.success(request, 'Phone alerts are off.')
        else:
            messages.success(request, 'Alert settings saved.')
        return redirect('alerts')

    return render(request, 'reach/alerts.html', {
        'pref': pref,
        'phone': pref.phone or (profile.phone if profile else ''),
        'channels': AlertPreference.CHANNEL_CHOICES,
        'recent': OutboxMessage.objects.filter(user=request.user)[:10],
        'backend': getattr(settings, 'ALERT_BACKEND', 'outbox'),
    })