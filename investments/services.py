"""
Financial operations that move capital or ownership.

Every function here runs inside a transaction, locks the rows it changes
(select_for_update) and raises django.core.exceptions.ValidationError instead
of failing silently. They are triggered from the post_save signals in
investments/signals.py, so callers that change a status should wrap the save in
transaction.atomic() to roll the status change back when the operation fails.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone
import logging

from .models import Investment, CapitalActivity, OwnershipTransfer, SecondaryMarketInterest, PerformanceSnapshot

logger = logging.getLogger('investments')

CENT = Decimal('0.01')
HOLDING_STATUSES = ['ACTIVE', 'UNDERPERFORMING']


def _to_cents(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _move_position(seller_investment_id, buyer, amount, *, whole_position, reference):
    """
    Move `amount` of value from the seller's investment to `buyer`.

    The seller's cost basis is reduced proportionally to the share of value
    sold; the buyer's cost basis is the amount acquired (transfers carry no fee).
    The same share of the seller's primary_capital moves to the buyer, so the
    opportunity's raised amount (the sum of its holders' primary capital) is
    unchanged: no new capital enters.

    Returns (seller_investment, buyer_investment, amount_moved).
    """
    seller_investment = (
        Investment.objects.select_for_update()
        .select_related('opportunity', 'user')
        .get(pk=seller_investment_id)
    )
    if seller_investment.status not in HOLDING_STATUSES:
        raise ValidationError("The seller's investment is no longer active.")
    if seller_investment.user_id == buyer.id:
        raise ValidationError("Buyer and seller cannot be the same user.")

    current_value = seller_investment.current_value
    if whole_position:
        amount = current_value
    if amount <= 0:
        raise ValidationError("Transfer amount must be greater than zero.")
    if amount > current_value:
        raise ValidationError(
            f"Transfer amount (${amount}) exceeds the seller's current value (${current_value})."
        )

    # --- Seller side -------------------------------------------------------
    share = amount / current_value
    cost_basis_sold = _to_cents(seller_investment.total_invested * share)
    primary_moved = _to_cents(seller_investment.primary_capital * share)
    new_value = current_value - amount
    exited = new_value < CENT
    if exited:
        new_value = Decimal('0.00')
        cost_basis_sold = seller_investment.total_invested
        primary_moved = seller_investment.primary_capital
    new_cost_basis = max(seller_investment.total_invested - cost_basis_sold, Decimal('0.00'))

    # .update() bypasses the Investment signals so the opportunity's raised
    # amount is not reduced.
    Investment.objects.filter(pk=seller_investment.pk).update(
        current_value=new_value,
        total_invested=new_cost_basis,
        primary_capital=F('primary_capital') - primary_moved,
        status='EXITED' if exited else seller_investment.status,
        updated_at=timezone.now(),
    )
    opportunity = seller_investment.opportunity

    today = timezone.now().date()
    CapitalActivity.objects.create(
        investment=seller_investment,
        activity_type='FULL_EXIT' if exited else 'PARTIAL_EXIT',
        amount=amount,  # positive = proceeds to the seller
        cost_basis=cost_basis_sold,
        date=today,
        details=f"{'Full' if exited else 'Partial'} sale to {buyer.email} ({reference})",
    )

    # --- Buyer side --------------------------------------------------------
    buyer_investment = None
    if opportunity:
        buyer_investment = (
            Investment.objects.select_for_update()
            .filter(user=buyer, opportunity=opportunity, status__in=HOLDING_STATUSES)
            .first()
        )

    if buyer_investment:
        Investment.objects.filter(pk=buyer_investment.pk).update(
            total_invested=F('total_invested') + amount,
            current_value=F('current_value') + amount,
            primary_capital=F('primary_capital') + primary_moved,
            updated_at=timezone.now(),
        )
        buyer_investment.refresh_from_db()
    else:
        buyer_investment = Investment(
            user=buyer,
            opportunity=opportunity,
            name=seller_investment.get_name(),
            sector=seller_investment.get_sector(),
            status='ACTIVE',
            total_invested=amount,
            current_value=amount,
            investment_date=today,
            manager=seller_investment.manager,
            fund_vintage=seller_investment.fund_vintage,
        )
        # Skip the raised-amount sync and over-funding check: ownership moves,
        # no new capital enters the opportunity.
        buyer_investment._skip_financial_sync = True
        buyer_investment.save()
        if primary_moved:
            Investment.objects.filter(pk=buyer_investment.pk).update(primary_capital=primary_moved)
            buyer_investment.primary_capital = primary_moved

    CapitalActivity.objects.create(
        investment=buyer_investment,
        activity_type='INITIAL_INVESTMENT',
        amount=-amount,  # negative = capital paid by the buyer
        date=today,
        details=f"Purchase from {seller_investment.user.email} ({reference})",
    )

    seller_investment.refresh_from_db()
    if opportunity:
        from .signals import recount_investors
        recount_investors(opportunity.pk)

    # Snapshot both sides at their post-transfer values so performance history
    # (and the cash-flow-adjusted analytics) see the move on the day it happened.
    for inv in (seller_investment, buyer_investment):
        PerformanceSnapshot.objects.update_or_create(
            investment=inv, date=today, defaults={'value': inv.current_value}
        )
    return seller_investment, buyer_investment, amount


def _log_portfolio_activity(seller, buyer, amount, metadata):
    """Audit-log both sides. Runs after commit so logging can't roll back the transfer."""
    from accounts.models import UserActivity

    def log():
        try:
            UserActivity.log_activity(
                user=seller, activity_type='PORTFOLIO_UPDATE',
                description=f'Transfer of ${amount} completed',
                metadata={**metadata, 'type': 'seller'},
            )
            UserActivity.log_activity(
                user=buyer, activity_type='PORTFOLIO_UPDATE',
                description=f'Received ${amount} via transfer',
                metadata={**metadata, 'type': 'buyer'},
            )
        except Exception as e:
            logger.warning(f"Failed to log UserActivity for transfer: {e}")

    transaction.on_commit(log)


def _cancel_open_buyer_interests(transfer_id, exclude_pk=None):
    qs = SecondaryMarketInterest.objects.filter(transfer_id=transfer_id, status='PENDING')
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    qs.update(status='CANCELLED', updated_at=timezone.now())


@transaction.atomic
def execute_ownership_transfer(transfer_id):
    """
    Execute a COMPLETED direct ownership transfer (seller → transfer.to_user).
    Idempotent: a transfer is processed at most once.
    """
    transfer = (
        OwnershipTransfer.objects.select_for_update()
        .select_related('to_user', 'from_user')
        .get(pk=transfer_id)
    )
    if transfer.is_processed or transfer.status != 'COMPLETED':
        return transfer
    if not transfer.to_user:
        raise ValidationError(
            "This transfer has no registered recipient (to_user), so it cannot be completed."
        )

    _, _, moved = _move_position(
        transfer.investment_id, transfer.to_user, transfer.transfer_amount,
        whole_position=transfer.transfer_type == 'FULL',
        reference=f"Transfer #{transfer.pk}",
    )

    transfer.transfer_amount = moved
    transfer.is_processed = True
    transfer.completion_date = transfer.completion_date or timezone.now()
    # save() recomputes net_amount from transfer_amount
    transfer.save(update_fields=['transfer_amount', 'net_amount', 'transfer_fee',
                                 'is_processed', 'completion_date', 'updated_at'])
    _cancel_open_buyer_interests(transfer.pk)

    logger.info(
        f"Processed transfer {transfer.pk}: {transfer.from_user.email} → "
        f"{transfer.to_user.email}, Amount: ${moved}"
    )
    _log_portfolio_activity(transfer.from_user, transfer.to_user, moved, {'transfer_id': transfer.pk})
    return transfer


@transaction.atomic
def execute_secondary_purchase(interest_id):
    """
    Execute a CONVERTED secondary-market purchase: move the buyer's amount out of
    the listed investment, complete the listing and cancel competing interests.
    """
    interest = SecondaryMarketInterest.objects.select_related('buyer').get(pk=interest_id)
    transfer = (
        OwnershipTransfer.objects.select_for_update()
        .select_related('from_user')
        .get(pk=interest.transfer_id)
    )
    if transfer.is_processed or transfer.status != 'PENDING':
        raise ValidationError("This listing is no longer available.")
    if transfer.to_user_id:
        raise ValidationError("This transfer is addressed to a specific recipient and is not for sale.")
    if interest.amount > transfer.transfer_amount:
        raise ValidationError(
            f"Amount ({interest.amount}) exceeds the listing amount ({transfer.transfer_amount})."
        )

    _, _, moved = _move_position(
        transfer.investment_id, interest.buyer, interest.amount,
        whole_position=transfer.transfer_type == 'FULL',
        reference=f"SecondaryMarketInterest #{interest.pk}",
    )

    if moved != interest.amount:
        SecondaryMarketInterest.objects.filter(pk=interest.pk).update(amount=moved)
    # .update() so the OwnershipTransfer completion signal doesn't fire a second move
    OwnershipTransfer.objects.filter(pk=transfer.pk).update(
        status='COMPLETED',
        is_processed=True,
        to_user=interest.buyer,
        completion_date=timezone.now(),
        updated_at=timezone.now(),
    )
    _cancel_open_buyer_interests(transfer.pk, exclude_pk=interest.pk)

    logger.info(
        f"SecondaryMarketInterest #{interest.pk} converted: "
        f"{transfer.from_user.email} → {interest.buyer.email}, Amount: ${moved}"
    )
    _log_portfolio_activity(transfer.from_user, interest.buyer, moved,
                            {'transfer_id': transfer.pk, 'secondary_interest_id': interest.pk})
    return interest


@transaction.atomic
def convert_investor_interest(interest_id):
    """
    Turn a CONVERTED marketplace pledge into primary capital: create (or top up)
    the investor's Investment in the opportunity.
    """
    from marketplace.models import InvestorInterest, MarketplaceOpportunity

    interest = InvestorInterest.objects.select_related('user').get(pk=interest_id)
    opportunity = MarketplaceOpportunity.objects.select_for_update().get(pk=interest.opportunity_id)

    remaining = opportunity.target_raise_amount - opportunity.current_raised_amount
    if interest.amount > remaining:
        raise ValidationError(
            f"Amount (${interest.amount}) exceeds the opportunity's remaining capacity (${remaining})."
        )

    investment = (
        Investment.objects.select_for_update()
        .filter(user=interest.user, opportunity=opportunity, status__in=HOLDING_STATUSES)
        .first()
    )
    if investment:
        # save() (not .update()) so the signals add the new capital to the
        # opportunity's raised amount and apply funding-based status changes.
        investment.total_invested += interest.amount
        investment.current_value += interest.amount
        investment.opportunity = opportunity
        investment.save()
    else:
        investment = Investment(
            user=interest.user,
            opportunity=opportunity,
            name=opportunity.title,
            sector=opportunity.sector,
            total_invested=interest.amount,
            current_value=interest.amount,
            investment_date=interest.investment_date,
            status='ACTIVE',
        )
        investment.save()

    CapitalActivity.objects.create(
        investment=investment,
        activity_type='INITIAL_INVESTMENT',
        amount=-interest.amount,  # negative = outflow from investor
        date=interest.investment_date,
        details=f"Converted from investor interest #{interest.pk} for {opportunity.title}",
    )

    logger.info(
        f"InvestorInterest #{interest.pk} converted: {interest.user.email} → "
        f"Investment #{investment.pk} (${interest.amount} in {opportunity.title})"
    )
    return investment
