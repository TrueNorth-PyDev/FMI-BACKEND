from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import InvestorProfile, UserNotificationPreference
import logging

logger = logging.getLogger('accounts')
User = get_user_model()


@receiver(post_save, sender=User)
def create_user_related_records(sender, instance, created, **kwargs):
    """Create the InvestorProfile and notification preferences for a new user."""
    if not created:
        return
    InvestorProfile.objects.get_or_create(
        user=instance,
        defaults={'display_name': instance.get_full_name() or instance.email.split('@')[0]},
    )
    UserNotificationPreference.objects.get_or_create(user=instance)
    logger.info(f"InvestorProfile and notification preferences created for user: {instance.email}")
