"""
Signals for the investments app.

Investment signals keep MarketplaceOpportunity totals and performance snapshots
in sync. Status-transition signals (transfer completed, pledge / secondary
interest converted) delegate to investments.services, which raise
ValidationError on failure. Wrap status-changing saves in transaction.atomic()
so a failed operation also rolls the status change back.
"""
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.db.models import F
from django.utils import timezone
from decimal import Decimal
from .models import OwnershipTransfer, Investment, PerformanceSnapshot, SecondaryMarketInterest
from . import services
from marketplace.models import InvestorInterest, MarketplaceOpportunity
import logging

logger = logging.getLogger('investments')


@receiver(post_save, sender=Investment)
def create_performance_snapshot(sender, instance, created, **kwargs):
    """
    Record today's value when an investment is created or its value changes.
    (Daily IRR accrual writes its own snapshots via bulk upsert.)
    """
    update_fields = kwargs.get('update_fields')
    if not created and update_fields is not None and 'current_value' not in update_fields:
        return
    if instance.current_value and instance.current_value > 0:
        PerformanceSnapshot.objects.update_or_create(
            investment=instance,
            date=timezone.now().date(),
            defaults={'value': instance.current_value},
        )


@receiver(post_save, sender=Investment)
def sync_opportunity_on_save(sender, instance, created, **kwargs):
    """
    Keep MarketplaceOpportunity.investors_count and current_raised_amount in step
    with investments, then apply funding-based status transitions.

    The raised amount moves by the change in the investment's primary_capital,
    which Investment.save() derives (ownership transfers contribute nothing).
    """
    old_opp_id = getattr(instance, '_old_opportunity_id', None)
    new_opp_id = instance.opportunity_id
    old_primary = getattr(instance, '_old_primary_capital', Decimal('0.00'))
    new_primary = instance.primary_capital
    opportunities = MarketplaceOpportunity.objects
    raised_increased = False

    moved = created or old_opp_id != new_opp_id
    if moved:
        if old_opp_id and not created:
            opportunities.filter(pk=old_opp_id).update(
                current_raised_amount=F('current_raised_amount') - old_primary,
            )
        if new_opp_id:
            opportunities.filter(pk=new_opp_id).update(
                current_raised_amount=F('current_raised_amount') + new_primary,
            )
            raised_increased = new_primary > 0
    elif new_opp_id and new_primary != old_primary:
        opportunities.filter(pk=new_opp_id).update(
            current_raised_amount=F('current_raised_amount') + (new_primary - old_primary)
        )
        raised_increased = new_primary > old_primary

    if moved or getattr(instance, '_old_status', None) != instance.status:
        recount_investors(old_opp_id, new_opp_id)
    if raised_increased:
        _apply_funding_status(new_opp_id)


def recount_investors(*opportunity_ids):
    """
    Set investors_count to the number of distinct users with an active holding.
    A recount (one indexed COUNT) can't drift the way +1/-1 updates can when
    holdings are exited, reactivated or edited by staff.
    """
    for opportunity_id in {pk for pk in opportunity_ids if pk}:
        count = Investment.objects.filter(
            opportunity_id=opportunity_id, status__in=['ACTIVE', 'UNDERPERFORMING']
        ).values('user_id').distinct().count()
        MarketplaceOpportunity.objects.filter(pk=opportunity_id).update(investors_count=count)


def _apply_funding_status(opportunity_id):
    """Move an opportunity forward to CLOSING_SOON (≥90%) or CLOSED (≥100%)."""
    opp = MarketplaceOpportunity.objects.only(
        'status', 'title', 'target_raise_amount', 'current_raised_amount'
    ).get(pk=opportunity_id)
    if opp.target_raise_amount <= 0:
        return
    progress = opp.current_raised_amount / opp.target_raise_amount

    allowed_from = {
        'CLOSED': ['NEW', 'ACTIVE', 'CLOSING_SOON'],
        'CLOSING_SOON': ['NEW', 'ACTIVE'],
    }
    new_status = 'CLOSED' if progress >= 1 else 'CLOSING_SOON' if progress >= Decimal('0.9') else None
    if new_status and opp.status in allowed_from[new_status]:
        MarketplaceOpportunity.objects.filter(pk=opportunity_id).update(status=new_status)
        logger.info(f"Opportunity {opp.title} transitioned to {new_status} (Progress: {progress * 100:.1f}%)")


@receiver(post_delete, sender=Investment)
def sync_opportunity_on_delete(sender, instance, **kwargs):
    """Remove a deleted investment's capital and holder from its opportunity."""
    if not instance.opportunity_id:
        return
    MarketplaceOpportunity.objects.filter(pk=instance.opportunity_id).update(
        current_raised_amount=F('current_raised_amount') - instance.primary_capital
    )
    recount_investors(instance.opportunity_id)
    logger.info(f"Opportunity {instance.opportunity_id} totals reduced (Investment {instance.pk} deleted)")


@receiver(post_save, sender=OwnershipTransfer)
def handle_transfer_completion(sender, instance, created, **kwargs):
    """Execute the asset move when a direct transfer is marked COMPLETED."""
    if instance.status == 'COMPLETED' and not instance.is_processed:
        services.execute_ownership_transfer(instance.pk)


def _capture_old_status(model):
    """
    pre_save receiver factory: remember the stored status so post_save can detect
    a genuine transition, and make CONVERTED final (re-converting would credit
    the investor a second time).
    """
    def receiver_fn(sender, instance, **kwargs):
        instance._old_status = (
            model.objects.filter(pk=instance.pk).values_list('status', flat=True).first()
            if instance.pk else None
        )
        if instance._old_status == 'CONVERTED' and instance.status != 'CONVERTED':
            from django.core.exceptions import ValidationError
            raise ValidationError("A converted interest is final and its status cannot be changed.")
    return receiver_fn


capture_investor_interest_old_status = _capture_old_status(InvestorInterest)
capture_secondary_interest_old_status = _capture_old_status(SecondaryMarketInterest)
pre_save.connect(capture_investor_interest_old_status, sender=InvestorInterest,
                 dispatch_uid='capture_investor_interest_old_status')
pre_save.connect(capture_secondary_interest_old_status, sender=SecondaryMarketInterest,
                 dispatch_uid='capture_secondary_interest_old_status')


@receiver(post_save, sender=InvestorInterest)
def convert_investor_interest_to_investment(sender, instance, created, **kwargs):
    """Create or top up an Investment when a pledge transitions to CONVERTED."""
    if instance.status == 'CONVERTED' and getattr(instance, '_old_status', None) != 'CONVERTED':
        services.convert_investor_interest(instance.pk)


@receiver(post_save, sender=SecondaryMarketInterest)
def convert_secondary_market_interest(sender, instance, created, **kwargs):
    """Execute the purchase when a secondary-market interest transitions to CONVERTED."""
    if instance.status == 'CONVERTED' and getattr(instance, '_old_status', None) != 'CONVERTED':
        services.execute_secondary_purchase(instance.pk)
