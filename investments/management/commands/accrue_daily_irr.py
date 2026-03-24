"""
Django management command to accrue daily IRR for all active investments.

This command:
1. Fetches all active investments with linked opportunities
2. Calculates daily IRR from annual target_irr using compound interest
3. Updates current_value with daily growth
4. Creates performance snapshots for tracking
5. Logs all updates

Run manually: python manage.py accrue_daily_irr
Schedule: Daily at 00:00 UTC (midnight UTC)
"""

from django.core.management.base import BaseCommand
from investments.models import Investment, PerformanceSnapshot
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
import logging

logger = logging.getLogger('investments')


class Command(BaseCommand):
    help = 'Accrue daily IRR for all active investments based on opportunity target IRR'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip the already-ran-today guard and force accrual (use with caution)',
        )
    
    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        force = options.get('force', False)

        today = timezone.now().date()

        # ---------------------------------------------------------------
        # Per-investment idempotency handles multiple triggers in a day.
        # It loops through the difference in days from the last snapshot
        # until `today` ensuring all gaps are filled retroactively.
        # ---------------------------------------------------------------
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved'))
        
        # Evaluate to a list once — avoids issuing a separate COUNT query
        # followed by a second SELECT on iteration.
        investments = list(Investment.objects.filter(
            status__in=['ACTIVE', 'UNDERPERFORMING'],
            opportunity__isnull=False
        ).select_related('opportunity'))

        total_count = len(investments)
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        self.stdout.write(f'Processing {total_count} active investments...')
        
        for investment in investments:
            try:
                # Skip if no target IRR or IRR is zero/negative
                if not investment.target_irr or investment.target_irr <= 0:
                    self.stdout.write(
                        self.style.WARNING(
                            f'  Skipped {investment.get_name()}: No positive target IRR'
                        )
                    )
                    skipped_count += 1
                    continue
                
                # Determine the last recorded snapshot date
                last_snapshot = investment.performance_snapshots.order_by('-date').first()
                if last_snapshot:
                    last_date = last_snapshot.date
                else:
                    last_date = investment.investment_date if investment.investment_date else investment.created_at.date()

                days_to_accrue = (today - last_date).days
                if days_to_accrue <= 0 and not force:
                    # Already up to date
                    continue

                # Calculate daily IRR using compound interest formula
                # Daily Rate = (1 + Annual Rate)^(1/365) - 1
                annual_rate = Decimal(str(investment.target_irr / 100))  # Convert % to decimal
                days_in_year = Decimal('365')
                daily_rate = (1 + annual_rate) ** (Decimal('1') / days_in_year) - 1
                
                old_value = investment.current_value
                new_value = old_value
                
                if dry_run:
                    self.stdout.write(
                        f'  [{investment.get_name()}] '
                        f'Would accrue {days_to_accrue} days. '
                        f'Current ${old_value:,.2f} ({investment.target_irr}% IRR)'
                    )
                else:
                    # Use transaction to ensure atomicity
                    with transaction.atomic():
                        overflow = False
                        # Retroactively fill in missed days
                        for i in range(1, days_to_accrue + 1):
                            current_accrual_date = last_date + timezone.timedelta(days=i)
                            
                            raw_new_value = new_value * (1 + daily_rate)
                            next_val = raw_new_value.quantize(Decimal('0.01'))
                            
                            # Ensure value doesn't exceed max digits
                            if next_val > Decimal('999999999999999999.99'):
                                logger.warning(f"Skipping update for {investment.get_name()}: Value {next_val} exceeds max digits on {current_accrual_date}")
                                self.stdout.write(self.style.WARNING(f"  ⚠ Value overflow for {investment.get_name()} on {current_accrual_date}"))
                                error_count += 1
                                overflow = True
                                break

                            new_value = next_val
                            
                            # Create or update today's/past performance snapshot
                            PerformanceSnapshot.objects.update_or_create(
                                investment=investment,
                                date=current_accrual_date,
                                defaults={'value': new_value}
                            )
                        
                        if overflow and i == 1:
                            # If overflow hit on the very first day, abort
                            continue
                            
                        growth = new_value - old_value
                        
                        # Update investment value
                        investment.current_value = new_value
                        logger.debug(f"Updated current value for {investment.get_name()}: {investment.current_value}")
                        investment.save(update_fields=['current_value', 'updated_at'])
                        
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'  ✓ {investment.get_name()}: '
                                f'Accrued {days_to_accrue} days. '
                                f'${old_value:,.2f} → ${new_value:,.2f} '
                                f'(+${growth:,.2f})'
                            )
                        )
                        
                        logger.info(
                            f'IRR accrued for {investment.get_name()}: '
                            f'${old_value} → ${new_value} (+${growth}) over {days_to_accrue} days.'
                        )
                
                updated_count += 1
                
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(
                        f'  ✗ Error processing {investment.get_name()}: {str(e)}'
                    )
                )
                logger.error(
                    f'Error accruing IRR for {investment.get_name()}: {str(e)}',
                    exc_info=True
                )
        
        # Summary
        self.stdout.write('\n' + '='*60)
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN COMPLETE - No changes saved'))
        else:
            self.stdout.write(self.style.SUCCESS('DAILY IRR ACCRUAL COMPLETE'))
        
        self.stdout.write(f'  Total investments: {total_count}')
        self.stdout.write(
            self.style.SUCCESS(f'  ✓ Updated: {updated_count}')
        )
        if skipped_count > 0:
            self.stdout.write(
                self.style.WARNING(f'  ⊘ Skipped: {skipped_count}')
            )
        if error_count > 0:
            self.stdout.write(
                self.style.ERROR(f'  ✗ Errors: {error_count}')
            )
        self.stdout.write('='*60)
        
        # Log summary
        if not dry_run:
            logger.info(
                f'Daily IRR accrual complete: {updated_count} updated, '
                f'{skipped_count} skipped, {error_count} errors'
            )
