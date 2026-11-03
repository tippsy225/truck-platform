from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='accounts/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('account/', views.account, name='account'),
    path('enable-both-roles/', views.enable_both_roles, name='enable_both_roles'),
    path('switch-role/', views.switch_role, name='switch_role'),
    path('notifications/', views.notifications, name='notifications'),
]