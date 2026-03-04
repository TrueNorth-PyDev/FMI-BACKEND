"""
Signals for the investments app.
Handles automatic actions when investment-related models are saved.
"""
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.db.models import F
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
from .models import OwnershipTransfer, Investment, CapitalActivity, PerformanceSnapshot, SecondaryMarketInterest
from marketplace.models import InvestorInterest
import logging

logger = logging.getLogger('investments')


@receiver(post_save, sender=Investment)
def create_performance_snapshot(sender, instance, created, **kwargs):
    """
    Create a PerformanceSnapshot when an investment's value changes.
    This tracks historical performance for charts and analytics.
    """
    # Only create snapshot if investment has a value
    if instance.current_value and instance.current_value > 0:
        today = timezone.now().date()
        # update_or_create is a single upsert — avoids the exists()+create
        # two-query pattern that fired on every Investment.save().
        snapshot, created = PerformanceSnapshot.objects.update_or_create(
            investment=instance,
            date=today,
            defaults={'value': instance.current_value},
        )
        if created:
            logger.info(f"Performance snapshot created for {instance.get_name()}: ${instance.current_value}")


@receiver(pre_save, sender=Investment)
def capture_old_investment_data(sender, instance, **kwargs):
    """
    Capture old investment data before saving to detect changes and set initial fund_size.
    """
    if instance.pk:
        try:
            old_obj = Investment.objects.filter(pk=instance.pk).only('opportunity', 'total_invested').first()
            instance._old_opportunity_id = old_obj.opportunity_id if old_obj else None
            instance._old_total_invested = old_obj.total_invested if old_obj else Decimal('0.00')
        except Exception:
            instance._old_opportunity_id = None
            instance._old_total_invested = Decimal('0.00')
    else:
        instance._old_opportunity_id = None
        instance._old_total_invested = Decimal('0.00')
        
        # Set initial fund size from opportunity's current raised amount if not provided
        if instance.opportunity and (not instance.fund_size or instance.fund_size == 0):
            instance.fund_size = instance.opportunity.current_raised_amount
            logger.info(f"Set initial fund_size for {instance.get_name()} to ${instance.fund_size}")


@receiver(post_save, sender=Investment)
def sync_opportunity_investors_count_on_save(sender, instance, created, **kwargs):
    """
    Sync MarketplaceOpportunity.investors_count when an investment is created or its opportunity changes.
    """
    if created:
        if instance.opportunity:
            instance.opportunity.__class__.objects.filter(pk=instance.opportunity.pk).update(
                investors_count=F('investors_count') + 1
            )
            logger.info(f"Incremented investors_count for opportunity: {instance.opportunity.title}")
    else:
        # Check if opportunity changed
        old_opp_id = getattr(instance, '_old_opportunity_id', None)
        new_opp_id = instance.opportunity_id
        
        if old_opp_id != new_opp_id:
            # Decrement old opportunity
            if old_opp_id:
                from marketplace.models import MarketplaceOpportunity
                MarketplaceOpportunity.objects.filter(pk=old_opp_id).update(
                    investors_count=F('investors_count') - 1
                )
                logger.info(f"Decremented investors_count for old opportunity ID: {old_opp_id}")
            
            # Increment new opportunity
            if new_opp_id:
                instance.opportunity.__class__.objects.filter(pk=new_opp_id).update(
                    investors_count=F('investors_count') + 1
                )
                logger.info(f"Incremented investors_count for new opportunity: {instance.opportunity.title}")


@receiver(post_save, sender=Investment)
def sync_opportunity_financials_on_save(sender, instance, created, **kwargs):
    """
    Sync MarketplaceOpportunity.current_raised_amount when an investment is created or updated.

    NOTE: Secondary-market ownership transfers must NOT change current_raised_amount
    because no new capital is entering the opportunity — ownership is merely moving
    between investors.  Any code path that creates/updates a buyer's Investment as
    part of a transfer must set  instance._skip_financial_sync = True  on the
    Investment instance before saving so this signal skips the raised-amount update.
    """
    # Skip raised-amount sync when explicitly flagged (e.g. ownership transfers)
    if getattr(instance, '_skip_financial_sync', False):
        return

    if not instance.opportunity_id and not getattr(instance, '_old_opportunity_id', None):
        return

    from marketplace.models import MarketplaceOpportunity
    
    if created:
        if instance.opportunity_id:
            MarketplaceOpportunity.objects.filter(pk=instance.opportunity_id).update(
                current_raised_amount=F('current_raised_amount') + instance.total_invested
            )
            logger.info(f"Incremented raised amount for opportunity ID: {instance.opportunity_id} by ${instance.total_invested}")
    else:
        old_opp_id = getattr(instance, '_old_opportunity_id', None)
        new_opp_id = instance.opportunity_id
        old_total = getattr(instance, '_old_total_invested', Decimal('0.00'))
        new_total = instance.total_invested
        
        if old_opp_id != new_opp_id:
            # 1. Decrement old opportunity
            if old_opp_id:
                MarketplaceOpportunity.objects.filter(pk=old_opp_id).update(
                    current_raised_amount=F('current_raised_amount') - old_total
                )
                logger.debug(f"Decremented raised amount for old opportunity ID: {old_opp_id} by ${old_total}")
            
            # 2. Increment new opportunity
            if new_opp_id:
                MarketplaceOpportunity.objects.filter(pk=new_opp_id).update(
                    current_raised_amount=F('current_raised_amount') + new_total
                )
                logger.debug(f"Incremented raised amount for new opportunity ID: {new_opp_id} by ${new_total}")
        elif old_total != new_total:
            # Update same opportunity by delta
            delta = new_total - old_total
            if new_opp_id:
                MarketplaceOpportunity.objects.filter(pk=new_opp_id).update(
                    current_raised_amount=F('current_raised_amount') + delta
                )
                logger.debug(f"Adjusted raised amount for opportunity ID: {new_opp_id} by delta: ${delta}")

    # Check for status transitions based on funding progress
    if instance.opportunity_id:
        opp = instance.opportunity
        opp.refresh_from_db()
        
        progress = Decimal('0.00')
        if opp.target_raise_amount > 0:
            progress = opp.current_raised_amount / opp.target_raise_amount
            
        new_status = None
        if progress >= 1.0:
            new_status = 'CLOSED'
        elif progress >= 0.9:
            new_status = 'CLOSING_SOON'
        
        if new_status and opp.status != new_status:
            # Only transition if it's moving "forward" (ACTIVE -> CLOSING_SOON -> CLOSED)
            # or if it was NEW/ACTIVE.
            allowed_transitions = {
                'CLOSING_SOON': ['NEW', 'ACTIVE'],
                'CLOSED': ['NEW', 'ACTIVE', 'CLOSING_SOON']
            }
            
            if opp.status in allowed_transitions.get(new_status, []):
                opp.status = new_status
                opp.save(update_fields=['status'])
                logger.info(f"Opportunity {opp.title} transitioned to {new_status} (Progress: {progress*100:.1f}%)")


@receiver(post_delete, sender=Investment)
def sync_opportunity_investors_count_on_delete(sender, instance, **kwargs):
    """
    Decrement MarketplaceOpportunity.investors_count when an investment is deleted.
    """
    if instance.opportunity_id:
        from marketplace.models import MarketplaceOpportunity
        MarketplaceOpportunity.objects.filter(pk=instance.opportunity_id).update(
            investors_count=F('investors_count') - 1
        )
        logger.info(f"Decremented investors_count for opportunity: {instance.opportunity.title} (Investment deleted)")


@receiver(post_delete, sender=Investment)
def sync_opportunity_financials_on_delete(sender, instance, **kwargs):
    """
    Decrement MarketplaceOpportunity.current_raised_amount when an investment is deleted.
    """
    if instance.opportunity_id:
        from marketplace.models import MarketplaceOpportunity
        MarketplaceOpportunity.objects.filter(pk=instance.opportunity_id).update(
            current_raised_amount=F('current_raised_amount') - instance.total_invested
        )
        logger.info(f"Decremented raised amount for opportunity ID: {instance.opportunity_id} by ${instance.total_invested} (Investment deleted)")


@receiver(post_save, sender=OwnershipTransfer)
def handle_transfer_completion(sender, instance, created, **kwargs):
    """
    Execute asset transfer logic when OwnershipTransfer is marked as COMPLETED.
    
    This signal ensures:
    1. Idempotency - processes each transfer only once
    2. Atomicity - all operations succeed or fail together
    3. Validation - prevents invalid transfers
    4. Audit trail - logs all activities
    """
    # Idempotency check - only process COMPLETED transfers that haven't been processed
    if instance.status != 'COMPLETED' or instance.is_processed:
        return
    
    buyer = instance.to_user
    if not buyer:
        logger.warning(f"Transfer {instance.id} completed but no buyer user assigned. Skipping.")
        return
    
    seller_investment = instance.investment
    
    # Validation: Ensure transfer amount doesn't exceed current value
    if seller_investment.current_value < instance.transfer_amount:
        logger.error(
            f"Transfer {instance.id} amount ({instance.transfer_amount}) "
            f"exceeds seller's current value ({seller_investment.current_value})"
        )
        # Don't raise exception in signal - log and skip
        return
    
    # Wrap financial operations in atomic transaction
    try:
        with transaction.atomic():
            # Calculate proportional cost basis
            transfer_ratio = Decimal('0.0')
            if seller_investment.current_value > 0:
                transfer_ratio = instance.transfer_amount / seller_investment.current_value
            
            cost_basis_deduction = seller_investment.total_invested * transfer_ratio
            
            # 1. Update Seller's Investment
            seller_investment.current_value -= instance.transfer_amount
            seller_investment.total_invested -= cost_basis_deduction
            
            # Handle Full Exit
            if instance.transfer_type == 'FULL' or seller_investment.current_value < Decimal('0.01'):
                seller_investment.status = 'EXITED'
                seller_investment.current_value = Decimal('0.00')
                seller_investment.total_invested = Decimal('0.00')
            
            # Use update_fields to bypass full_clean() — we already validated
            # transfer_amount above so this save is always safe.
            Investment.objects.filter(pk=seller_investment.pk).update(
                current_value=seller_investment.current_value,
                total_invested=seller_investment.total_invested,
                status=seller_investment.status,
            )
            # No refresh_from_db needed — we have the exact computed values above.
            
            # Log Seller Activity
            CapitalActivity.objects.create(
                investment=seller_investment,
                activity_type='PARTIAL_EXIT' if instance.transfer_type == 'PARTIAL' else 'DISTRIBUTION',
                amount=instance.transfer_amount,
                date=timezone.now().date(),
                details=f"Ownership transfer to {buyer.email} (Transfer #{instance.id})"
            )
            
            # 2. Create/Update Buyer's Investment
            # Ownership transfers must NOT affect current_raised_amount on the
            # opportunity — no new capital is entering, only ownership is moving.
            # We therefore bypass the financial-sync signal by:
            #   a) using .filter().update() (which skips signals) for existing
            #      investments, and
            #   b) tagging new Investment instances with _skip_financial_sync=True
            #      so the post_save signal leaves current_raised_amount alone.
            opportunity = seller_investment.opportunity
            buyer_investment = Investment.objects.filter(
                user=buyer,
                opportunity=opportunity,
                name=seller_investment.name or seller_investment.get_name(),
            ).first()

            if buyer_investment:
                # Top up existing investment — use .update() to bypass signals
                buyer_investment.total_invested += instance.transfer_amount
                buyer_investment.current_value += instance.transfer_amount
                Investment.objects.filter(pk=buyer_investment.pk).update(
                    current_value=buyer_investment.current_value,
                    total_invested=buyer_investment.total_invested,
                )
                # No refresh_from_db needed — values computed above are correct.
            else:
                # Create new investment and flag it to skip financial sync
                buyer_investment = Investment(
                    user=buyer,
                    opportunity=opportunity,
                    name=seller_investment.name or seller_investment.get_name(),
                    sector=seller_investment.sector or seller_investment.get_sector(),
                    status='ACTIVE',
                    total_invested=instance.transfer_amount,
                    current_value=instance.transfer_amount,
                    investment_date=timezone.now().date(),
                    manager=seller_investment.manager,
                    fund_vintage=seller_investment.fund_vintage,
                )
                buyer_investment._skip_financial_sync = True
                buyer_investment.save()
            
            # Log Buyer Activity
            CapitalActivity.objects.create(
                investment=buyer_investment,
                activity_type='INITIAL_INVESTMENT',
                amount=-instance.transfer_amount,  # Negative for outflow
                date=timezone.now().date(),
                details=f"Ownership transfer from {instance.from_user.email} (Transfer #{instance.id})"
            )
            
            # 3. Mark transfer as processed and set completion date
            instance.is_processed = True
            if not instance.completion_date:
                instance.completion_date = timezone.now()
            instance.save(update_fields=['is_processed', 'completion_date'])
            
            logger.info(
                f"Successfully processed transfer {instance.id}: "
                f"{instance.from_user.email} → {buyer.email}, "
                f"Amount: ${instance.transfer_amount}"
            )
    
    except Exception as e:
        logger.error(f"Failed to process transfer {instance.id}: {str(e)}", exc_info=True)
        # Transaction will rollback automatically
        return

    # Log portfolio update activity OUTSIDE the atomic block so audit logging
    # failures never roll back the financial transfer itself.
    try:
        from accounts.models import UserActivity
        UserActivity.log_activity(
            user=instance.from_user,
            activity_type='PORTFOLIO_UPDATE',
            description=f'Transfer of ${instance.transfer_amount} completed',
            metadata={'transfer_id': instance.id, 'type': 'seller'}
        )
        UserActivity.log_activity(
            user=buyer,
            activity_type='PORTFOLIO_UPDATE',
            description=f'Received ${instance.transfer_amount} via transfer',
            metadata={'transfer_id': instance.id, 'type': 'buyer'}
        )
    except Exception as e:
        logger.warning(f"Failed to log UserActivity for transfer {instance.id}: {str(e)}")


@receiver(pre_save, sender=InvestorInterest)
def capture_investor_interest_old_status(sender, instance, **kwargs):
    """
    Capture the old status of an InvestorInterest before saving,
    so the post_save signal can detect transitions.
    """
    if instance.pk:
        try:
            old = InvestorInterest.objects.filter(pk=instance.pk).only('status').first()
            instance._old_status = old.status if old else None
        except Exception:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=InvestorInterest)
def convert_investor_interest_to_investment(sender, instance, created, **kwargs):
    """
    Automatically create (or update) an Investment when an InvestorInterest
    status transitions to 'CONVERTED'.

    Field mapping:
      - user            <- interest.user
      - opportunity     <- interest.opportunity
      - name            <- opportunity.title
      - sector          <- opportunity.sector
      - total_invested  <- interest.amount
      - current_value   <- interest.amount
      - investment_date <- interest.investment_date
      - status          <- 'ACTIVE'
    """
    # Only act on a transition TO 'CONVERTED' (not on creation with CONVERTED
    # set directly, which is an unusual admin edge-case — guard with created check)
    old_status = getattr(instance, '_old_status', None)
    if instance.status != 'CONVERTED' or old_status == 'CONVERTED':
        return

    opportunity = instance.opportunity

    try:
        with transaction.atomic():
            investment, inv_created = Investment.objects.get_or_create(
                user=instance.user,
                opportunity=opportunity,
                defaults={
                    'name': opportunity.title,
                    'sector': opportunity.sector,
                    'total_invested': instance.amount,
                    'current_value': instance.amount,
                    'investment_date': instance.investment_date,
                    'status': 'ACTIVE',
                }
            )

            if not inv_created:
                # Investment already exists — top it up
                Investment.objects.filter(pk=investment.pk).update(
                    total_invested=investment.total_invested + instance.amount,
                    current_value=investment.current_value + instance.amount,
                )
                investment.refresh_from_db()

                # Manually sync the opportunity since we used .update() which
                # bypasses signals — the opportunity counter would otherwise miss
                # this additional amount.
                from marketplace.models import MarketplaceOpportunity
                MarketplaceOpportunity.objects.filter(pk=opportunity.pk).update(
                    current_raised_amount=F('current_raised_amount') + instance.amount
                )

            # Record the capital inflow
            CapitalActivity.objects.create(
                investment=investment,
                activity_type='INITIAL_INVESTMENT',
                amount=-instance.amount,  # negative = outflow from investor
                date=instance.investment_date,
                details=(
                    f"Converted from investor interest #{instance.pk} "
                    f"for {opportunity.title}"
                ),
            )

            logger.info(
                f"InvestorInterest #{instance.pk} converted: "
                f"{instance.user.email} → Investment #{investment.pk} "
                f"(${instance.amount} in {opportunity.title})"
            )

    except Exception as e:
        logger.error(
            f"Failed to convert InvestorInterest #{instance.pk} to Investment: {e}",
            exc_info=True,
        )

# ---------------------------------------------------------------------------
# SecondaryMarketInterest signals
# ---------------------------------------------------------------------------

@receiver(pre_save, sender=SecondaryMarketInterest)
def capture_secondary_interest_old_status(sender, instance, **kwargs):
    """
    Snapshot the current status before saving so post_save can detect
    true PENDING → CONVERTED transitions.
    """
    if instance.pk:
        # .values_list + .first() fetches only the status column — no need
        # for a full row read.
        row = SecondaryMarketInterest.objects.filter(
            pk=instance.pk
        ).values_list('status', flat=True).first()
        instance._old_status = row  # None if somehow missing
    else:
        instance._old_status = None


@receiver(post_save, sender=SecondaryMarketInterest)
def convert_secondary_market_interest(sender, instance, created, **kwargs):
    """
    When a SecondaryMarketInterest transitions to CONVERTED:
      1. Deduct `amount` from the seller's Investment
      2. Create / top-up the buyer's Investment
      3. Log CapitalActivity records for both sides
      4. Mark the OwnershipTransfer as COMPLETED and is_processed=True
    """
    old_status = getattr(instance, '_old_status', None)
    if instance.status != 'CONVERTED' or old_status == 'CONVERTED':
        return  # Only fire on genuine transitions to CONVERTED

    transfer = instance.transfer
    buyer    = instance.buyer
    seller   = transfer.from_user
    amount   = instance.amount
    today    = timezone.now().date()

    try:
        with transaction.atomic():
            # -----------------------------------------------------------------
            # 1. Locate the seller's Investment (the one being partially sold)
            # -----------------------------------------------------------------
            seller_investment = transfer.investment  # the specific Investment on the transfer

            if seller_investment.current_value < amount:
                logger.error(
                    f"Cannot convert SecondaryMarketInterest #{instance.pk}: "
                    f"seller's current_value ({seller_investment.current_value}) "
                    f"< requested amount ({amount})"
                )
                return

            # Deduct from seller
            new_seller_value     = seller_investment.current_value - amount
            new_seller_invested  = max(seller_investment.total_invested - amount, Decimal('0.00'))
            new_seller_status    = 'EXITED' if new_seller_value == Decimal('0.00') else seller_investment.status

            Investment.objects.filter(pk=seller_investment.pk).update(
                current_value=new_seller_value,
                total_invested=new_seller_invested,
                status=new_seller_status,
            )

            # Log seller's capital exit — differentiate full vs partial exit
            exit_activity_type = 'FULL_EXIT' if new_seller_status == 'EXITED' else 'PARTIAL_EXIT'
            exit_details = (
                f"{'Complete' if exit_activity_type == 'FULL_EXIT' else 'Partial'} secondary market sale "
                f"to {buyer.email} — SecondaryMarketInterest #{instance.pk}"
            )

            CapitalActivity.objects.create(
                investment=seller_investment,
                activity_type=exit_activity_type,
                amount=amount,  # positive = proceeds inflow to seller
                date=today,
                details=exit_details,
            )

            logger.info(
                f"Seller {seller.email} investment reduced by ${amount} "
                f"(new value: ${new_seller_value}, status: {new_seller_status}, "
                f"activity: {exit_activity_type})"
            )

            # -----------------------------------------------------------------
            # 2. Create / top-up the buyer's Investment
            # -----------------------------------------------------------------
            # Secondary-market transfers must NOT change current_raised_amount on
            # the opportunity — no new capital enters, only existing ownership
            # moves between investors.  We therefore:
            #   • use .filter().update() (signal-bypassing) for existing investments
            #   • tag new Investment instances with _skip_financial_sync=True
            # so sync_opportunity_financials_on_save leaves the raised amount alone.
            opportunity = seller_investment.opportunity
            inv_name   = opportunity.title  if opportunity else transfer.investment.name
            inv_sector = opportunity.sector if opportunity else transfer.investment.sector

            if opportunity:
                buyer_investment = Investment.objects.filter(
                    user=buyer,
                    opportunity=opportunity,
                ).first()
            else:
                buyer_investment = None

            if buyer_investment:
                # Top up existing investment — use .update() to bypass signals
                Investment.objects.filter(pk=buyer_investment.pk).update(
                    total_invested=buyer_investment.total_invested + amount,
                    current_value=buyer_investment.current_value + amount,
                )
                buyer_investment.refresh_from_db()
            else:
                # Create new investment and flag it to skip financial sync
                buyer_investment = Investment(
                    user=buyer,
                    opportunity=opportunity,  # may be None for standalone investments
                    name=inv_name,
                    sector=inv_sector,
                    total_invested=amount,
                    current_value=amount,
                    investment_date=today,
                    status='ACTIVE',
                )
                buyer_investment._skip_financial_sync = True
                buyer_investment.save()

            # Log buyer's capital entry
            CapitalActivity.objects.create(
                investment=buyer_investment,
                activity_type='INITIAL_INVESTMENT',
                amount=-amount,  # negative = capital outflow from buyer
                date=today,
                details=(
                    f"Secondary market purchase from {seller.email} — "
                    f"SecondaryMarketInterest #{instance.pk}"
                ),
            )

            logger.info(
                f"Buyer {buyer.email} investment created/updated: ${amount} "
                f"(Investment #{buyer_investment.pk})"
            )

            # -----------------------------------------------------------------
            # 3. Mark the OwnershipTransfer as COMPLETED
            # -----------------------------------------------------------------
            OwnershipTransfer.objects.filter(pk=transfer.pk).update(
                status='COMPLETED',
                is_processed=True,
                completion_date=timezone.now(),
            )

            logger.info(
                f"SecondaryMarketInterest #{instance.pk} converted: "
                f"{seller.email} → {buyer.email}, Amount: ${amount}"
            )

    except Exception as e:
        logger.error(
            f"Failed to convert SecondaryMarketInterest #{instance.pk}: {e}",
            exc_info=True,
        )
