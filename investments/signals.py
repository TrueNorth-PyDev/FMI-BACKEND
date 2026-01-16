"""
Signals for the investments app.
Handles automatic actions when investment-related models are saved.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
from .models import OwnershipTransfer, Investment, CapitalActivity, PerformanceSnapshot
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
        # Check if we already have a snapshot for today
        today = timezone.now().date()
        existing = PerformanceSnapshot.objects.filter(
            investment=instance,
            date=today
        ).exists()
        
        if not existing:
            PerformanceSnapshot.objects.create(
                investment=instance,
                date=today,
                value=instance.current_value
            )
            logger.info(f"Performance snapshot created for {instance.name}: ${instance.current_value}")


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
    
    # Wrap entire operation in atomic transaction
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
            
            seller_investment.save()
            
            # Log Seller Activity
            CapitalActivity.objects.create(
                investment=seller_investment,
                activity_type='PARTIAL_EXIT' if instance.transfer_type == 'PARTIAL' else 'DISTRIBUTION',
                amount=instance.transfer_amount,
                date=timezone.now().date(),
                details=f"Ownership transfer to {buyer.email} (Transfer #{instance.id})"
            )
            
            # 2. Create/Update Buyer's Investment
            buyer_investment, created_inv = Investment.objects.get_or_create(
                user=buyer,
                name=seller_investment.name,
                defaults={
                    'sector': seller_investment.sector,
                    'status': 'ACTIVE',
                    'total_invested': Decimal('0.00'),
                    'current_value': Decimal('0.00'),
                    'investment_date': timezone.now().date(),
                    'manager': seller_investment.manager,
                    'fund_vintage': seller_investment.fund_vintage,
                }
            )
            
            # Update Buyer Values
            buyer_investment.total_invested += instance.transfer_amount
            buyer_investment.current_value += instance.transfer_amount
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
            
            # Log portfolio update activity for both users
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
            
            logger.info(
                f"Successfully processed transfer {instance.id}: "
                f"{instance.from_user.email} → {buyer.email}, "
                f"Amount: ${instance.transfer_amount}"
            )
    
    except Exception as e:
        logger.error(f"Failed to process transfer {instance.id}: {str(e)}", exc_info=True)
        # Transaction will rollback automatically
