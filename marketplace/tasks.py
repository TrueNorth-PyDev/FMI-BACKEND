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
        logger.info("Successfully completed scheduled task: transition_opportunities")
    except Exception as e:
        logger.error(f"Failed to run transition_opportunities: {str(e)}")
