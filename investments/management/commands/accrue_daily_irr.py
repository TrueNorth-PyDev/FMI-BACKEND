"""
Django management command to accrue daily IRR for all active investments.

This command:
1. Fetches all active investments with linked opportunities
2. Calculates the daily rate from the opportunity's annual target_irr (compound interest)
3. Applies growth for every day since the investment's last_accrued_date,
   backfilling any days missed while the scheduler was down
4. Writes one performance snapshot per accrued day
5. Logs all updates

Idempotent: each investment is accrued at most once per calendar day, so it is
safe to run repeatedly (e.g. on every deploy).

Run manually: python manage.py accrue_daily_irr
Schedule: every 24 hours via setup_periodic_tasks
"""

from django.core.management.base import BaseCommand
from investments.models import Investment, PerformanceSnapshot
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
import logging

logger = logging.getLogger('investments')

CENT = Decimal('0.01')
MAX_VALUE = Decimal('9999999999999.99')  # PerformanceSnapshot.value max_digits=15


def daily_rate_for(annual_irr_percent):
    """Daily Rate = (1 + Annual Rate)^(1/365) - 1"""
    annual_rate = Decimal(annual_irr_percent) / 100
    return (1 + annual_rate) ** (Decimal('1') / Decimal('365')) - 1


class Command(BaseCommand):
    help = 'Accrue daily IRR for all active investments based on opportunity target IRR'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        today = timezone.now().date()

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved'))

        investments = list(Investment.objects.filter(
            status__in=['ACTIVE', 'UNDERPERFORMING'],
            opportunity__isnull=False,
        ).select_related('opportunity'))

        total_count = len(investments)
        updated_count = 0
        skipped_count = 0
        error_count = 0

        self.stdout.write(f'Processing {total_count} active investments...')

        for investment in investments:
            try:
                target_irr = investment.target_irr
                if not target_irr or target_irr <= 0:
                    skipped_count += 1
                    continue

                last_date = investment.last_accrued_date or investment.created_at.date()
                days_to_accrue = (today - last_date).days
                if days_to_accrue <= 0:
                    continue  # Already accrued today

                daily_rate = daily_rate_for(target_irr)
                old_value = investment.current_value

                if dry_run:
                    projected = (old_value * (1 + daily_rate) ** days_to_accrue).quantize(CENT, ROUND_HALF_UP)
                    self.stdout.write(
                        f'  [{investment.get_name()}] Would accrue {days_to_accrue} days: '
                        f'${old_value:,.2f} → ${projected:,.2f} ({target_irr}% IRR)'
                    )
                    updated_count += 1
                    continue

                # Compound on the unrounded value so per-day rounding doesn't drift;
                # only the stored figures are rounded to cents.
                running = old_value
                snapshots = []
                accrued_through = last_date
                for day in range(1, days_to_accrue + 1):
                    next_value = running * (1 + daily_rate)
                    if next_value.quantize(CENT, ROUND_HALF_UP) > MAX_VALUE:
                        logger.warning(f"Value overflow for {investment.get_name()}; stopping accrual at {accrued_through}")
                        self.stdout.write(self.style.WARNING(f"  ⚠ Value overflow for {investment.get_name()}"))
                        error_count += 1
                        break
                    running = next_value
                    accrued_through = last_date + timedelta(days=day)
                    snapshots.append(PerformanceSnapshot(
                        investment=investment,
                        date=accrued_through,
                        value=running.quantize(CENT, ROUND_HALF_UP),
                    ))

                if not snapshots:
                    continue
                new_value = snapshots[-1].value

                with transaction.atomic():
                    PerformanceSnapshot.objects.bulk_create(
                        snapshots,
                        update_conflicts=True,
                        unique_fields=['investment', 'date'],
                        update_fields=['value'],
                    )
                    # .update() rather than save(): accrual only changes value, so it
                    # must not re-run model validation (e.g. the over-funding check).
                    # The current_value guard skips the write if the value changed
                    # since it was read (e.g. a concurrent sale); it is retried next run.
                    rows = Investment.objects.filter(
                        pk=investment.pk, current_value=old_value
                    ).update(
                        current_value=new_value,
                        last_accrued_date=accrued_through,
                        updated_at=timezone.now(),
                    )
                    if not rows:
                        transaction.set_rollback(True)
                        logger.warning(f"{investment.get_name()} changed during accrual; will retry next run")
                        error_count += 1
                        continue

                growth = new_value - old_value
                updated_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f'  ✓ {investment.get_name()}: Accrued {len(snapshots)} days. '
                    f'${old_value:,.2f} → ${new_value:,.2f} (+${growth:,.2f})'
                ))
                logger.info(
                    f'IRR accrued for {investment.get_name()}: '
                    f'${old_value} → ${new_value} (+${growth}) over {len(snapshots)} days.'
                )

            except Exception as e:
                error_count += 1
                self.stdout.write(self.style.ERROR(f'  ✗ Error processing {investment.get_name()}: {str(e)}'))
                logger.error(f'Error accruing IRR for {investment.get_name()}: {str(e)}', exc_info=True)

        # Summary
        self.stdout.write('\n' + '=' * 60)
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN COMPLETE - No changes saved'))
        else:
            self.stdout.write(self.style.SUCCESS('DAILY IRR ACCRUAL COMPLETE'))
        self.stdout.write(f'  Total investments: {total_count}')
        self.stdout.write(self.style.SUCCESS(f'  ✓ Updated: {updated_count}'))
        if skipped_count:
            self.stdout.write(self.style.WARNING(f'  ⊘ Skipped (no positive target IRR): {skipped_count}'))
        if error_count:
            self.stdout.write(self.style.ERROR(f'  ✗ Errors: {error_count}'))
        self.stdout.write('=' * 60)

        if not dry_run:
            logger.info(
                f'Daily IRR accrual complete: {updated_count} updated, '
                f'{skipped_count} skipped, {error_count} errors'
            )
