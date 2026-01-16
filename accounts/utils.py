"""
Utility functions for the accounts app.
Handles OTP generation, email sending, and security helpers.
"""

from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import logging

logger = logging.getLogger('accounts')


def send_verification_email(user, otp):
    """
    Send email verification OTP to the user.
    
    Args:
        user: User instance
        otp: OTP instance
    """
    subject = 'Verify Your Email - PrivCap Hub'
    
    # Create email body
    message = f"""
    Hi {user.first_name},
    
    Welcome to PrivCap Hub! Please verify your email address to complete your registration.
    
    Your verification code is: {otp.otp_code}
    
    This code will expire in {settings.OTP_EXPIRY_MINUTES} minutes.
    
    If you didn't create an account with PrivCap Hub, please ignore this email.
    
    Best regards,
    The PrivCap Hub Team
    """
    
    try:
        send_mail(
            subject=subject,
            message=message.strip(),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info(f"Verification email sent to {user.email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send verification email to {user.email}: {str(e)}")
        return False


def send_password_reset_email(user, otp):
    """
    Send password reset OTP to the user.
    
    Args:
        user: User instance
        otp: OTP instance
    """
    subject = 'Reset Your Password - PrivCap Hub'
    
    message = f"""
    Hi {user.first_name},
    
    We received a request to reset your password for your PrivCap Hub account.
    
    Your password reset code is: {otp.otp_code}
    
    This code will expire in {settings.OTP_EXPIRY_MINUTES} minutes.
    
    If you didn't request a password reset, please ignore this email and ensure your account is secure.
    
    Best regards,
    The PrivCap Hub Team
    """
    
    try:
        send_mail(
            subject=subject,
            message=message.strip(),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info(f"Password reset email sent to {user.email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send password reset email to {user.email}: {str(e)}")
        return False


def send_welcome_email(user):
    """
    Send welcome email after successful email verification.
    
    Args:
        user: User instance
    """
    subject = 'Welcome to PrivCap Hub!'
    
    message = f"""
    Hi {user.first_name},
    
    Your email has been successfully verified! Welcome to PrivCap Hub.
    
    You can now access all features of your investment portfolio dashboard.
    
    Get back to managing your investments like a pro!
    
    Best regards,
    The PrivCap Hub Team
    """
    
    try:
        send_mail(
            subject=subject,
            message=message.strip(),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info(f"Welcome email sent to {user.email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send welcome email to {user.email}: {str(e)}")
        return False


def get_client_ip(request):
    """
    Get the client's IP address from the request.
    
    Args:
        request: Django request object
        
    Returns:
        str: IP address
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def log_auth_event(event_type, user_email, ip_address, success=True, details=None):
    """
    Log authentication events for security auditing.
    
    Args:
        event_type: Type of event (login, registration, password_reset, etc.)
        user_email: User's email address
        ip_address: Client IP address
        success: Whether the event was successful
        details: Additional details about the event
    """
    security_logger = logging.getLogger('security')
    
    status = "SUCCESS" if success else "FAILED"
    log_message = f"{event_type.upper()} {status} - Email: {user_email}, IP: {ip_address}"
    
    if details:
        log_message += f", Details: {details}"
    
    if success:
        security_logger.info(log_message)
    else:
        security_logger.warning(log_message)
