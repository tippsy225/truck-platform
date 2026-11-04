from django.contrib import admin
from django.urls import include, path

from accounts import pwa
from accounts import views as accounts_views

urlpatterns = [
    path('', accounts_views.home, name='home'),
    path('admin/', admin.site.urls),
    path('loads/', include('loads.urls')),
    path('trucks/', include('trucks.urls')),
    path('accounts/', include('accounts.urls')),
    path('wallet/', include('wallet.urls')),
    path('space/', include('space.urls')),
    path('reach/', include('reach.urls')),
    path('tracking/', include('tracking.urls')),
    path('manifest.webmanifest', pwa.manifest, name='pwa_manifest'),
    path('sw.js', pwa.service_worker, name='pwa_sw'),
    path('offline/', pwa.offline, name='pwa_offline'),
]