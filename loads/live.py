from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from accounts.models import Review
from wallet.models import Dispute, Escrow

from .models import Load, OfferEvent, Payment


@login_required
def load_live(request, pk):
    load = get_object_or_404(Load, pk=pk)
    last_event = OfferEvent.objects.filter(offer__load=load).aggregate(m=Max('id'))['m'] or 0
    paid = Payment.objects.filter(offer__load=load, status='paid').count()
    escrow = (Escrow.objects.filter(offer__load=load)
              .values_list('status', flat=True).first() or '')
    disputes = Dispute.objects.filter(offer__load=load)
    reviews = Review.objects.filter(offer__load=load).count()
    signature = '|'.join(str(part) for part in (
        load.status, last_event, paid, escrow,
        disputes.count(), disputes.filter(status='open').count(), reviews))
    return JsonResponse({'signature': signature})