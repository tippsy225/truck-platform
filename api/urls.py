from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from . import views

urlpatterns = [
    path('auth/token/', views.LoginView.as_view(), name='api_token'),
    path('auth/logout/', views.LogoutView.as_view(), name='api_logout'),
    path('me/', views.MeView.as_view(), name='api_me'),
    path('price-guide/', views.PriceGuideView.as_view(), name='api_price_guide'),

    path('loads/', views.LoadListView.as_view(), name='api_loads'),
    path('loads/mine/', views.MyLoadsView.as_view(), name='api_my_loads'),
    path('loads/<int:pk>/', views.LoadDetailView.as_view(), name='api_load'),
    path('loads/<int:pk>/offers/', views.LoadOffersView.as_view(), name='api_load_offers'),

    path('offers/mine/', views.MyOffersView.as_view(), name='api_my_offers'),
    path('offers/<int:pk>/accept/', views.OfferAcceptView.as_view(), name='api_offer_accept'),
    path('offers/<int:pk>/decline/', views.OfferDeclineView.as_view(), name='api_offer_decline'),
    path('offers/<int:pk>/counter/', views.OfferCounterView.as_view(), name='api_offer_counter'),
    path('offers/<int:pk>/withdraw/', views.OfferWithdrawView.as_view(), name='api_offer_withdraw'),

    path('trucks/', views.TruckListView.as_view(), name='api_trucks'),
    path('trucks/mine/', views.MyTrucksView.as_view(), name='api_my_trucks'),

    path('wallet/', views.WalletView.as_view(), name='api_wallet'),
    path('notifications/', views.NotificationListView.as_view(), name='api_notifications'),
    path('notifications/read/', views.NotificationReadView.as_view(), name='api_notifications_read'),

    path('schema/', SpectacularAPIView.as_view(), name='api_schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='api_schema'), name='api_docs'),
]