from django.contrib import admin
from django.urls import include, path

from accounts import views as accounts_views

urlpatterns = [
    path('', accounts_views.home, name='home'),
    path('admin/', admin.site.urls),
    path('loads/', include('loads.urls')),
    path('trucks/', include('trucks.urls')),
    path('accounts/', include('accounts.urls')),
    path('wallet/', include('wallet.urls')),
]