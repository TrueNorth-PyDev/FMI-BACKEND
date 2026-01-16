from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import InvestorProfile
import logging

logger = logging.getLogger('accounts')
User = get_user_model()

@receiver(post_save, sender=User)
def create_investor_profile(sender, instance, created, **kwargs):
    """Create InvestorProfile when a new User is created."""
    if created:
        InvestorProfile.objects.create(user=instance)
        logger.info(f"InvestorProfile created for user: {instance.email}")


@receiver(post_save, sender=User)
def create_notification_preferences(sender, instance, created, **kwargs):
    """
    Automatically create UserNotificationPreference when a new user is created.
    """
    from .models import UserNotificationPreference
    
    if created:
        UserNotificationPreference.objects.create(user=instance)
        logger.info(f"UserNotificationPreference created for user: {instance.email}")

@receiver(post_save, sender=User)
def save_investor_profile(sender, instance, **kwargs):
    """Save InvestorProfile when User is saved."""
    try:
        instance.investor_profile.save()
    except InvestorProfile.DoesNotExist:
        # Should be created by create_investor_profile, but for safety:
        InvestorProfile.objects.create(user=instance)
