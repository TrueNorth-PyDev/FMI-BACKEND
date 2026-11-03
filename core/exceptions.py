"""
Custom exception handlers for the core app.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler, set_rollback
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger('core')


def custom_exception_handler(exc, context):
    """
    Custom exception handler for DRF.
    Provides consistent error response format and logging.
    """
    # Model validation and investments.services raise Django's ValidationError;
    # report those as 400s rather than 500s.
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(exc.message_dict if hasattr(exc, 'error_dict') else exc.messages)

    # Call REST framework's default exception handler first (it also marks the
    # request's transaction for rollback under ATOMIC_REQUESTS)
    response = exception_handler(exc, context)
    request = context.get('request')
    path = request.path if request else 'unknown'
    
    if response is not None:
        # Client errors (4xx) are expected traffic; keep them out of WARNING-level logs
        log = logger.warning if response.status_code >= 500 else logger.info
        log(f"API Error: {exc.__class__.__name__} at {path} - {str(exc)}")
        response.data = {
            'error': True,
            'message': 'An error occurred',
            'details': response.data
        }
        return response

    # Unhandled exception: roll back any partial writes, log the traceback,
    # and never return internals to the client
    set_rollback()
    logger.error(f"Unhandled exception at {path}: {exc.__class__.__name__} - {str(exc)}", exc_info=exc)
    return Response({
        'error': True,
        'message': 'An unexpected error occurred',
        'details': None,
    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
