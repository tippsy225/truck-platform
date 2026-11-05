from django.urls import path

from . import views

urlpatterns = [
    path('', views.hub, name='growth_hub'),
    path('plans/<str:key>/subscribe/', views.subscribe_view, name='growth_subscribe'),
    path('r/<str:code>/', views.referral_landing, name='growth_ref'),
    path('owner/', views.owner_dashboard, name='owner_dashboard'),
]