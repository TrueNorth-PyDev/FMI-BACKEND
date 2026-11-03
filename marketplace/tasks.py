from django_rq import job
from django.core.management import call_command
import logging

logger = logging.getLogger('marketplace')

@job
def run_transition_opportunities():
    """
    Wrapper task to run the transition_opportunities management command.
    """
    logger.info("Starting scheduled task: transition_opportunities")
    try:
        call_command('transition_opportunities')
    except Exception:
        # Log and re-raise so RQ records the job as failed instead of successful
        logger.exception("Failed to run transition_opportunities")
        raise
    logger.info("Successfully completed scheduled task: transition_opportunities")
