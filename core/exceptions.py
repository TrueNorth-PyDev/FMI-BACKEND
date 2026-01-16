"""
Custom exception handlers for the core app.
"""

from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger('core')


def custom_exception_handler(exc, context):
    """
    Custom exception handler for DRF.
    Provides consistent error response format and logging.
    """
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)
    
    if response is not None:
        # Customize the response format
        custom_response_data = {
            'error': True,
            'message': 'An error occurred',
            'details': response.data
        }
        
        # Log the exception
        request = context.get('request')
        if request:
            logger.error(
                f"API Error: {exc.__class__.__name__} at {request.path} - {str(exc)}"
            )
        
        response.data = custom_response_data
    else:
        # Handle non-DRF exceptions
        logger.error(f"Unhandled exception: {exc.__class__.__name__} - {str(exc)}")
        
        response = Response({
            'error': True,
            'message': 'An unexpected error occurred',
            'details': str(exc)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return response
