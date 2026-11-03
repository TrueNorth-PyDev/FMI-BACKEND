"""
Session tracking utilities for parsing device information and managing sessions.
"""
from user_agents import parse
import logging

logger = logging.getLogger('accounts')


def parse_device_name(user_agent_string):
    """
    Parse user agent string to extract device name.
    
    Args:
        user_agent_string (str): HTTP User-Agent header value
        
    Returns:
        str: Human-readable device name (e.g., "Chrome on Windows", "Safari on iPhone")
    """
    if not user_agent_string:
        return "Unknown Device"
    
    try:
        user_agent = parse(user_agent_string)
        
        # Build device name
        browser = user_agent.browser.family
        os = user_agent.os.family
        
        # Handle mobile devices
        if user_agent.is_mobile:
            device = user_agent.device.family
            if device != "Other":
                return f"{browser} on {device}"
            return f"{browser} on Mobile"
        
        # Handle tablets
        if user_agent.is_tablet:
            device = user_agent.device.family
            if device != "Other":
                return f"{browser} on {device}"
            return f"{browser} on Tablet"
        
        # Desktop/PC
        return f"{browser} on {os}"
        
    except Exception as e:
        logger.warning(f"Failed to parse user agent: {str(e)}")
        return "Unknown Device"


def get_location_from_ip(ip_address):
    """
    Get location from IP address.
    
    Note: This is a placeholder. In production, integrate with a service like:
    - ipapi.co
    - ipstack.com
    - MaxMind GeoIP2
    
    Args:
        ip_address (str): IP address
        
    Returns:
        str: Location string (e.g., "New York, NY, USA")
    """
    # Localhost detection
    if ip_address in ['127.0.0.1', '::1', 'localhost']:
        return "Local Development"
    
    # TODO: Integrate with IP geolocation service
    # Example with ipapi (requires requests library):
    # try:
    #     response = requests.get(f'https://ipapi.co/{ip_address}/json/', timeout=2)
    #     if response.status_code == 200:
    #         data = response.json()
    #         city = data.get('city', '')
    #         region = data.get('region', '')
    #         country = data.get('country_name', '')
    #         return f"{city}, {region}, {country}" if city else country
    # except Exception as e:
    #     logger.warning(f"IP geolocation failed: {str(e)}")
    
    return "Unknown Location"


def create_session(user, request, refresh, ip_address):
    """
    Record a login session keyed by the refresh token's JTI, mark it current,
    and prune the user's oldest sessions.
    """
    from .models import UserSession

    user_agent = request.META.get('HTTP_USER_AGENT', '')
    UserSession.objects.filter(user=user, is_current=True).update(is_current=False)
    session = UserSession.objects.create(
        user=user,
        device_name=parse_device_name(user_agent),
        location=get_location_from_ip(ip_address),
        ip_address=ip_address,
        user_agent=user_agent,
        is_current=True,
        session_key=str(refresh['jti']),
    )
    cleanup_old_sessions(user)
    return session


def revoke_sessions(sessions):
    """
    Blacklist the refresh tokens behind the given UserSession queryset and delete
    the sessions. Access tokens already issued expire on their own (15 minutes).

    Returns the number of sessions removed.
    """
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

    session_keys = list(sessions.values_list('session_key', flat=True))
    outstanding = OutstandingToken.objects.filter(jti__in=session_keys)
    BlacklistedToken.objects.bulk_create(
        [BlacklistedToken(token=token) for token in outstanding],
        ignore_conflicts=True,
    )
    count, _ = sessions.delete()
    return count


def cleanup_old_sessions(user, max_sessions=10):
    """
    Clean up old sessions, keeping only the most recent ones.
    Pruned sessions have their refresh tokens revoked.
    
    Args:
        user: User instance
        max_sessions (int): Maximum number of sessions to keep
    """
    from .models import UserSession

    # Collect PKs of sessions beyond the limit first — Django forbids
    # calling .delete() directly on a sliced queryset (LIMIT/OFFSET).
    ids_to_delete = list(
        UserSession.objects.filter(user=user)
        .order_by('-last_activity')
        .values_list('pk', flat=True)[max_sessions:]
    )
    if ids_to_delete:
        deleted_count = revoke_sessions(UserSession.objects.filter(pk__in=ids_to_delete))
        logger.info(f"Cleaned up {deleted_count} old sessions for {user.email}")
