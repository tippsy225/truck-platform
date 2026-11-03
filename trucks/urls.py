from django.urls import path
from . import views

urlpatterns = [
    path('', views.truck_list, name='truck_list'),
    path('add/', views.add_truck, name='add_truck'),
    path('mine/', views.my_trucks, name='my_trucks'),
    path('<int:pk>/edit/', views.edit_truck, name='edit_truck'),
    path('<int:pk>/toggle/', views.toggle_truck, name='toggle_truck'),
    path('<int:pk>/delete/', views.delete_truck, name='delete_truck'),
]