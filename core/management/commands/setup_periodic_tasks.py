from django.core.management.base import BaseCommand
from django_rq import get_scheduler
from marketplace.tasks import run_transition_opportunities
from investments.tasks import run_daily_irr_accrual
from core.tasks import run_daily_cleanup
from django.utils import timezone

class Command(BaseCommand):
    help = 'Setup periodic tasks for PrivCap Hub using RQ Scheduler'

    def handle(self, *args, **options):
        scheduler = get_scheduler('default')
        
        # Clear existing jobs to avoid duplicates
        for job in scheduler.get_jobs():
            scheduler.cancel(job)
            job.delete()
        
        # Schedule: Transition Opportunities every 6 hours
        scheduler.schedule(
            scheduled_time=timezone.now(),  # First execution: immediately
            func=run_transition_opportunities,
            interval=6 * 60 * 60,  # 6 hours in seconds
            repeat=None            # Infinite repeat
        )
        self.stdout.write(self.style.SUCCESS("Scheduled 'run_transition_opportunities' every 6 hours."))

        # Schedule: Daily IRR Accrual every 24 hours
        scheduler.schedule(
            scheduled_time=timezone.now(),
            func=run_daily_irr_accrual,
            interval=24 * 60 * 60, # 24 hours in seconds
            repeat=None
        )
        self.stdout.write(self.style.SUCCESS("Scheduled 'run_daily_irr_accrual' every 24 hours."))

        # Schedule: housekeeping (expired tokens, old OTPs) every 24 hours
        scheduler.schedule(
            scheduled_time=timezone.now(),
            func=run_daily_cleanup,
            interval=24 * 60 * 60,
            repeat=None
        )
        self.stdout.write(self.style.SUCCESS("Scheduled 'run_daily_cleanup' every 24 hours."))
