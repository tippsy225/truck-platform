import base64
import urllib.parse
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import OutboxMessage

MAX_PER_HOUR = 20


def _twilio(channel, phone, body):
    # Not tested against a live account. Check Twilio's current documentation and your account setup.
    sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
    token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
    sender = getattr(settings, 'TWILIO_FROM', '')
    if not (sid and token and sender):
        return 'failed', 'Twilio settings are missing.'
    to, from_ = phone, sender
    if channel == 'whatsapp':
        to = f'whatsapp:{phone}'
        from_ = sender if sender.startswith('whatsapp:') else f'whatsapp:{sender}'
    data = urllib.parse.urlencode({'To': to, 'From': from_, 'Body': body}).encode()
    url = f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json'
    request = urllib.request.Request(url, data=data)
    credentials = base64.b64encode(f'{sid}:{token}'.encode()).decode()
    request.add_header('Authorization', f'Basic {credentials}')
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            if 200 <= response.status < 300:
                return 'sent', ''
            return 'failed', f'The provider answered with status {response.status}.'
    except Exception as exc:
        return 'failed', str(exc)[:200]


def send(channel, phone, body):
    if getattr(settings, 'ALERT_BACKEND', 'outbox') == 'twilio':
        return _twilio(channel, phone, body)
    return 'queued', 'No provider is connected, so this message was recorded but not sent.'


def deliver(user, channel, phone, body):
    now = timezone.now()
    recent = OutboxMessage.objects.filter(
        user=user, created_at__gte=now - timedelta(hours=1)).count()
    message = OutboxMessage.objects.create(user=user, channel=channel, phone=phone, body=body[:300])
    if recent >= MAX_PER_HOUR:
        message.status = 'skipped'
        message.detail = 'The hourly limit was reached.'
        message.save()
        return message
    status, detail = send(channel, phone, message.body)
    message.status = status
    message.detail = detail
    message.sent_at = now if status == 'sent' else None
    message.save()
    return message