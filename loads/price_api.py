from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from .pricing import suggest_price


@login_required
def price_suggestion(request):
    try:
        tonnes = float(request.GET.get('tonnes', ''))
    except ValueError:
        return JsonResponse({'ok': False})
    result = suggest_price(request.GET.get('pickup', ''),
                           request.GET.get('destination', ''), tonnes)
    if result is None:
        return JsonResponse({'ok': False})
    return JsonResponse({'ok': True, **result})