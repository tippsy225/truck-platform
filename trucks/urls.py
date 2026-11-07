from django.urls import path
from . import views

urlpatterns = [
    path('', views.truck_list, name='truck_list'),
    path('add/', views.add_truck, name='add_truck'),
    path('mine/', views.my_trucks, name='my_trucks'),
    path('photo/<int:photo_pk>/<str:size>/', views.photo_file, name='truck_photo_file'),
    path('<int:pk>/', views.truck_detail, name='truck_detail'),
    path('<int:pk>/edit/', views.edit_truck, name='edit_truck'),
    path('<int:pk>/toggle/', views.toggle_truck, name='toggle_truck'),
    path('<int:pk>/delete/', views.delete_truck, name='delete_truck'),
    path('<int:pk>/photos/', views.truck_photos, name='truck_photos'),
    path('<int:pk>/photos/<int:photo_pk>/delete/', views.delete_photo, name='delete_truck_photo'),
]