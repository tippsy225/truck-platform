from django.urls import path

from . import views

urlpatterns = [
    path('<int:offer_pk>/', views.track_page, name='track_page'),
    path('<int:offer_pk>/start/', views.start_tracking, name='start_tracking'),
    path('<int:offer_pk>/stop/', views.stop_tracking, name='stop_tracking'),
    path('<int:offer_pk>/ask/', views.ask_tracking, name='ask_tracking'),
    path('<int:offer_pk>/ping/', views.ping, name='track_ping'),
    path('<int:offer_pk>/data/', views.data, name='track_data'),
]