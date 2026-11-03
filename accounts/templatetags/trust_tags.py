from django import template

from accounts.forms import ReviewForm
from accounts.models import Review, rating_summary

register = template.Library()


@register.inclusion_tag('accounts/_trust_chip.html')
def trust_chip(person):
    profile = getattr(person, 'profile', None)
    avg, count = rating_summary(person)
    return {
        'person': person,
        'verified': bool(profile and profile.is_verified),
        'avg': round(avg, 1) if avg else None,
        'count': count,
    }


@register.inclusion_tag('accounts/_review_box.html', takes_context=True)
def review_box(context, load):
    request = context['request']
    user = request.user
    result = {'show': False, 'csrf_token': context.get('csrf_token')}
    if not user.is_authenticated or load.status != 'delivered':
        return result
    offer = load.offers.filter(status='accepted').select_related('transporter').first()
    if not offer:
        return result
    if user.id == load.shipper_id:
        other = offer.transporter
    elif user.id == offer.transporter_id:
        other = load.shipper
    else:
        return result
    mine = Review.objects.filter(offer=offer, reviewer=user).first()
    theirs = Review.objects.filter(offer=offer, reviewer=other).first()
    result.update(show=True, offer=offer, other=other, mine=mine, theirs=theirs,
                  form=ReviewForm())
    return result