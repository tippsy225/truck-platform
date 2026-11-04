from django import template

from tracking.models import Tracking
from tracking.services import can_track

register = template.Library()


@register.inclusion_tag('tracking/_tracking_box.html', takes_context=True)
def tracking_box(context, load):
    user = context['request'].user
    result = {'show': False}
    if not user.is_authenticated or load.status != 'booked':
        return result
    offer = load.offers.filter(status='accepted').first()
    if not offer or not can_track(offer):
        return result
    if user.id not in (offer.transporter_id, load.shipper_id):
        return result
    tracking = Tracking.objects.filter(offer=offer).first()
    result.update(show=True, offer=offer, active=bool(tracking and tracking.active),
                  is_transporter=user.id == offer.transporter_id)
    return result