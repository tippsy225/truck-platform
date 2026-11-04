from django.urls import path

from . import views

urlpatterns = [
    path('', views.space_list, name='space_list'),
    path('new/', views.trip_new, name='trip_new'),
    path('mine/', views.my_trips, name='my_trips'),
    path('requests/<int:pk>/<str:action>/', views.request_action, name='space_request_action'),
    path('load/<int:pk>/matches/', views.load_matches, name='load_matches'),
    path('<int:pk>/', views.trip_detail, name='space_trip'),
    path('<int:pk>/close/', views.close_trip, name='close_trip'),
]