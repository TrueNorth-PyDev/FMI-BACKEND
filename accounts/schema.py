"""
OpenAPI (drf-spectacular) extensions for the accounts app.
"""
from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme


class SessionJWTScheme(SimpleJWTScheme):
    """Document SessionJWTAuthentication as the standard Bearer JWT scheme."""
    target_class = 'accounts.authentication.SessionJWTAuthentication'
