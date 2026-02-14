"""
Management command to transition marketplace opportunities based on time.
Transitions 'NEW' opportunities to 'ACTIVE' after a 24-hour period.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from marketplace.models import MarketplaceOpportunity
import logging

logger = logging.getLogger('marketplace')

class Command(BaseCommand):
    help = "Transitions 'NEW' opportunities to 'ACTIVE' after 24 hours."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting opportunity status transitions..."))
        
        # Threshold: 24 hours ago
        threshold_date = timezone.now() - timedelta(hours=24)
        
        # Find NEW opportunities older than the threshold
        new_opps = MarketplaceOpportunity.objects.filter(
            status='NEW',
            created_at__lte=threshold_date
        )
        
        count = new_opps.count()
        if count == 0:
            self.stdout.write("No opportunities found for transition.")
            return

        # Perform the transition
        for opp in new_opps:
            opp.status = 'ACTIVE'
            opp.save(update_fields=['status'])
            self.stdout.write(self.style.SUCCESS(f"Transitioned '{opp.title}' to ACTIVE."))
            logger.info(f"Opportunity {opp.title} transitioned from NEW to ACTIVE (Time-based)")
            
        self.stdout.write(self.style.SUCCESS(f"Successfully transitioned {count} opportunities."))
