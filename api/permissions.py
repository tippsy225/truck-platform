from rest_framework.permissions import BasePermission

from .rules import role_of


class IsShipper(BasePermission):
    message = 'Only shippers can do this.'

    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and role_of(request.user) == 'shipper')


class IsTransporter(BasePermission):
    message = 'Only transporters can do this.'

    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and role_of(request.user) == 'transporter')