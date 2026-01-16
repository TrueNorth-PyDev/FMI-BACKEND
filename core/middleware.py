"""
Custom middleware for the core app.
Handles security logging and additional security features.
"""

import logging
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger('security')


class SecurityLoggingMiddleware(MiddlewareMixin):
    """
    Middleware to log security-related events and suspicious activities.
    """
    
    def process_request(self, request):
        """Log incoming requests to authentication endpoints."""
        # Only log authentication-related requests
        auth_paths = ['/api/auth/login/', '/api/auth/register/', '/api/auth/password-reset/']
        
        if any(path in request.path for path in auth_paths):
            ip_address = self.get_client_ip(request)
            logger.info(f"Auth request: {request.method} {request.path} from IP: {ip_address}")
        
        return None
    
    def process_response(self, request, response):
        """Log failed authentication attempts."""
        # Log failed authentication (4xx responses on auth endpoints)
        if request.path.startswith('/api/auth/') and 400 <= response.status_code < 500:
            ip_address = self.get_client_ip(request)
            logger.warning(
                f"Failed auth attempt: {request.method} {request.path} "
                f"from IP: {ip_address}, Status: {response.status_code}"
            )
        
        return response
    
    @staticmethod
    def get_client_ip(request):
        """Get the client's IP address from the request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
