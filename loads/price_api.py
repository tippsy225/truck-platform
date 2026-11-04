from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from .learning import refine
from .pricing import suggest_price


@login_required
def price_suggestion(request):
    try:
        tonnes = float(request.GET.get('tonnes', ''))
    except ValueError:
        return JsonResponse({'ok': False})
    if not (0 < tonnes <= 500):
        return JsonResponse({'ok': False})
    pickup = request.GET.get('pickup', '')
    destination = request.GET.get('destination', '')
    result = suggest_price(pickup, destination, tonnes)
    if result is None:
        return JsonResponse({'ok': False})
    result = refine(result, pickup, destination, tonnes)
    return JsonResponse({'ok': True, **result})