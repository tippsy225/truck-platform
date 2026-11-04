from django.urls import path
from . import live, price_api, views

urlpatterns = [
    path('', views.load_list, name='load_list'),
    path('post/', views.post_load, name='post_load'),
    path('mine/', views.my_loads, name='my_loads'),
    path('offers/', views.my_offers, name='my_offers'),
    path('offers/<int:pk>/<str:action>/', views.offer_action, name='offer_action'),
    path('payments/<int:pk>/pay/', views.pay_fee, name='pay_fee'),
    path('payments/<int:pk>/check/', views.check_payment, name='check_payment'),
    path('suggest-price/', price_api.price_suggestion, name='price_suggestion'),
    path('<int:pk>/deliver/', views.mark_delivered, name='mark_delivered'),
    path('<int:pk>/live/', live.load_live, name='load_live'),
    path('<int:pk>/', views.load_detail, name='load_detail'),
]