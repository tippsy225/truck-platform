from django.shortcuts import render
from .models import Load


def load_list(request):
    loads = Load.objects.order_by('-created_at')
    return render(request, 'loads/load_list.html', {'loads': loads})