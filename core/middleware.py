"""
Custom middleware for the core app.
Handles security logging and additional security features.
"""

import logging
from django.utils.deprecation import MiddlewareMixin
from accounts.utils import get_client_ip

logger = logging.getLogger('security')

AUTH_PATH_PREFIXES = (
    '/api/accounts/login/',
    '/api/accounts/register/',
    '/api/accounts/verify-email/',
    '/api/accounts/resend-otp/',
    '/api/accounts/password-reset/',
    '/api/accounts/token/refresh/',
)


class SecurityLoggingMiddleware(MiddlewareMixin):
    """
    Middleware to log security-related events and suspicious activities.
    """

    def process_request(self, request):
        """Log incoming requests to authentication endpoints."""
        if request.path.startswith(AUTH_PATH_PREFIXES):
            logger.info(f"Auth request: {request.method} {request.path} from IP: {get_client_ip(request)}")
        return None

    def process_response(self, request, response):
        """Log failed authentication attempts (4xx responses on auth endpoints)."""
        if request.path.startswith(AUTH_PATH_PREFIXES) and 400 <= response.status_code < 500:
            logger.warning(
                f"Failed auth attempt: {request.method} {request.path} "
                f"from IP: {get_client_ip(request)}, Status: {response.status_code}"
            )
        return response
