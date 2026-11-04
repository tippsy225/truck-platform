from urllib.parse import quote

from django import template
from django.urls import reverse

from reach.phone import to_e164

register = template.Library()


@register.inclusion_tag('reach/_contact_tools.html', takes_context=True)
def contact_tools(context, load):
    request = context['request']
    user = request.user
    result = {'show': False}
    if not user.is_authenticated:
        return result
    is_owner = load.shipper_id == user.id

    if load.status == 'open' and is_owner:
        link = request.build_absolute_uri(reverse('load_detail', args=[load.pk]))
        text = (f'Load for transport: {load.title}, {load.pickup} to {load.destination}, '
                f'{load.weight_tonnes} t. See it and send your offer on TruckLink: {link}')
        result.update(show=True, share_url='https://wa.me/?text=' + quote(text))
        return result

    offer = load.offers.filter(status='accepted').select_related('transporter').first()
    if not offer or load.status not in ('booked', 'delivered') or not offer.fee_paid:
        return result
    if is_owner:
        other = offer.transporter
    elif offer.transporter_id == user.id:
        other = load.shipper
    else:
        return result
    profile = getattr(other, 'profile', None)
    phone = profile.phone if profile else ''
    e164 = to_e164(phone)
    result.update(
        show=True, other=other, phone=phone,
        wa_url=f'https://wa.me/{e164.lstrip("+")}' if e164 else '',
        tel_url=f'tel:{e164}' if e164 else '')
    return result