from django.urls import path
from . import views

urlpatterns = [
    path('', views.load_list, name='load_list'),
    path('post/', views.post_load, name='post_load'),
    path('mine/', views.my_loads, name='my_loads'),
    path('offers/', views.my_offers, name='my_offers'),
    path('offers/<int:pk>/<str:decision>/', views.respond_offer, name='respond_offer'),
    path('payments/<int:pk>/pay/', views.pay_fee, name='pay_fee'),
    path('payments/<int:pk>/check/', views.check_payment, name='check_payment'),
    path('<int:pk>/', views.load_detail, name='load_detail'),
]