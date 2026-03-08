"""
Custom permissions for the admin API.
"""
from rest_framework.permissions import BasePermission


class IsAdminUser(BasePermission):
    """
    Allows access only to staff/admin users (is_staff=True).
    Returns 403 for authenticated non-staff and 401 for unauthenticated.
    """
    message = "You do not have permission to access the admin panel."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)
