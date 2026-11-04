from django.urls import path

from . import views

urlpatterns = [
    path('', views.wallet_home, name='wallet_home'),
    path('topup/', views.wallet_topup, name='wallet_topup'),
    path('withdraw/', views.wallet_withdraw, name='wallet_withdraw'),
    path('escrow/<int:offer_pk>/fund/', views.escrow_fund, name='escrow_fund'),
    path('disputes/', views.dispute_list, name='dispute_list'),
    path('disputes/new/<int:offer_pk>/', views.dispute_new, name='dispute_new'),
    path('disputes/<int:pk>/', views.dispute_detail, name='dispute_detail'),
]