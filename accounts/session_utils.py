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


def cleanup_old_sessions(user, max_sessions=10):
    """
    Clean up old sessions, keeping only the most recent ones.
    
    Args:
        user: User instance
        max_sessions (int): Maximum number of sessions to keep
    """
    from .models import UserSession
    
    sessions = UserSession.objects.filter(user=user).order_by('-last_activity')
    
    if sessions.count() > max_sessions:
        # Delete oldest sessions
        old_sessions = sessions[max_sessions:]
        deleted_count = old_sessions.delete()[0]
        logger.info(f"Cleaned up {deleted_count} old sessions for {user.email}")
