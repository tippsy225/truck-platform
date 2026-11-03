from django import template

register = template.Library()


@register.simple_tag
def unread_count(user):
    if not user.is_authenticated:
        return 0
    return user.notifications.filter(is_read=False).count()