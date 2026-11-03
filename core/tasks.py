from django_rq import job
from django.core.management import call_command
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger('core')


@job
def run_daily_cleanup():
    """
    Housekeeping for tables that otherwise grow without bound:
    expired JWT refresh tokens (outstanding/blacklisted), old OTP codes and
    sessions whose refresh token has expired.
    """
    from django.conf import settings
    from accounts.models import OTP, UserSession

    logger.info("Starting scheduled task: daily_cleanup")
    try:
        call_command('flushexpiredtokens')
        cutoff = timezone.now() - timedelta(days=1)
        deleted, _ = OTP.objects.filter(created_at__lt=cutoff).filter(
            Q(is_used=True) | Q(expires_at__lt=cutoff)
        ).delete()
        # A session idle for longer than the refresh-token lifetime can never be refreshed again
        refresh_lifetime = settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME']
        UserSession.objects.filter(last_activity__lt=timezone.now() - refresh_lifetime).delete()
    except Exception:
        # Log and re-raise so RQ records the job as failed instead of successful
        logger.exception("Failed to run daily_cleanup")
        raise
    logger.info(f"Successfully completed scheduled task: daily_cleanup ({deleted} old OTPs removed)")
