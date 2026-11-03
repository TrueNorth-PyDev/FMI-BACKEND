from django_rq import job
from django.core.management import call_command
import logging

logger = logging.getLogger('investments')

@job
def run_daily_irr_accrual():
    """
    Wrapper task to run the accrue_daily_irr management command.
    """
    logger.info("Starting scheduled task: accrue_daily_irr")
    try:
        call_command('accrue_daily_irr')
    except Exception:
        # Log and re-raise so RQ records the job as failed instead of successful
        logger.exception("Failed to run accrue_daily_irr")
        raise
    logger.info("Successfully completed scheduled task: accrue_daily_irr")
