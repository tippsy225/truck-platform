from decimal import Decimal

from django import template
from django.conf import settings

from wallet.models import Escrow
from wallet.services import balance

register = template.Library()


def _side(user, load, offer):
    if user.id == load.shipper_id:
        return 'shipper'
    if user.id == offer.transporter_id:
        return 'transporter'
    return None


@register.inclusion_tag('wallet/_escrow_box.html', takes_context=True)
def escrow_box(context, load):
    request = context['request']
    user = request.user
    result = {'show': False, 'csrf_token': context.get('csrf_token')}
    if not user.is_authenticated or load.status not in ('booked', 'delivered'):
        return result
    offer = load.offers.filter(status='accepted').select_related('transporter').first()
    if not offer or not offer.fee_paid:
        return result
    side = _side(user, load, offer)
    if side is None:
        return result
    escrow = Escrow.objects.filter(offer=offer).first()
    result.update(show=True, load=load, offer=offer, side=side, escrow=escrow,
                  required=getattr(settings, 'ESCROW_REQUIRED', False))
    if side == 'shipper' and escrow is None and load.status == 'booked':
        available = balance(user)
        result.update(balance=available,
                      can_fund=available >= offer.price,
                      shortfall=max(offer.price - available, Decimal('0')).quantize(Decimal('0.01')))
    return result


@register.inclusion_tag('wallet/_dispute_box.html', takes_context=True)
def dispute_box(context, load):
    request = context['request']
    user = request.user
    result = {'show': False}
    if not user.is_authenticated:
        return result
    offer = load.offers.filter(status='accepted').first()
    if not offer or not offer.fee_paid or _side(user, load, offer) is None:
        return result
    disputes = list(offer.disputes.all())
    has_open = any(d.status == 'open' for d in disputes)
    can_raise = load.status == 'booked' and not has_open
    if disputes or can_raise:
        result.update(show=True, offer=offer, disputes=disputes, can_raise=can_raise)
    return result