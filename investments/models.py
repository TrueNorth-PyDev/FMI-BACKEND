from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from accounts.models import User
from decimal import Decimal
import logging

logger = logging.getLogger('investments')


class Investment(models.Model):
    """
    Represents a private equity investment/fund in the user's portfolio.
    Linked to a MarketplaceOpportunity to derive name, sector, and IRR.
    """
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('UNDERPERFORMING', 'Underperforming'),
        ('EXITED', 'Exited'),
    ]
    
    SECTOR_CHOICES = [
        ('TECHNOLOGY', 'Technology'),
        ('HEALTHCARE', 'Healthcare'),
        ('REAL_ESTATE', 'Real Estate'),
        ('FINTECH', 'FinTech'),
        ('AGRICULTURE', 'Agriculture'),
        ('ENERGY', 'Energy'),
        ('CONSUMER', 'Consumer'),
        ('INDUSTRIAL', 'Industrial'),
        ('OTHER', 'Other'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='investments')
    
    # Link to marketplace opportunity
    opportunity = models.ForeignKey(
        'marketplace.MarketplaceOpportunity',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='investments',
        help_text="Marketplace opportunity this investment is based on"
    )
    
    # Legacy fields - kept for backward compatibility
    # New investments should use opportunity.title and opportunity.sector instead
    name = models.CharField(max_length=255, blank=True, null=True, help_text="Fund/Investment name (deprecated, use opportunity.title)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    sector = models.CharField(max_length=20, choices=SECTOR_CHOICES, blank=True, null=True, help_text="Investment sector (deprecated, use opportunity.sector)")
    
    # Financial details
    total_invested = models.DecimalField(
        max_digits=20, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Total amount invested"
    )
    current_value = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Current valuation"
    )
    fund_size = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total fund size (AUM)"
    )
    unfunded_commitment = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Remaining capital commitment"
    )
    
    # Fund details
    manager = models.CharField(max_length=255, blank=True, help_text="Fund manager name")
    investment_date = models.DateField(help_text="Initial investment date")
    expected_horizon_years = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(50)],
        help_text="Expected investment duration in years"
    )
    fund_vintage = models.IntegerField(
        null=True,
        blank=True,
        help_text="Fund vintage year"
    )
    
    # How much of this investment counts toward the opportunity's raised amount.
    # Ownership transfers move value and cost basis between investors without
    # adding capital, so a bought-in position contributes nothing here.
    primary_capital = models.DecimalField(
        max_digits=20, decimal_places=2, default=Decimal('0.00'), editable=False,
        help_text="Capital this investment contributed to the opportunity's raised amount",
    )

    # Daily IRR accrual bookkeeping: value growth has been applied up to and
    # including this date. Kept separately from PerformanceSnapshot so that an
    # ordinary save (which snapshots today's value) can't make the accrual job
    # think missed days are already accrued.
    last_accrued_date = models.DateField(null=True, blank=True, editable=False)
    
    # Progress
    progress_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text="Fund deployment progress"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'investments'
        verbose_name = 'Investment'
        verbose_name_plural = 'Investments'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'sector']),
            models.Index(fields=['investment_date']),
        ]
    
    def __str__(self):
        return f"{self.get_name()} - {self.user.email}"

    def _load_previous_state(self):
        """
        Read the stored opportunity/total_invested once per save. Used by clean()
        and by the post_save signals that keep the opportunity's totals in sync.
        """
        old = None
        if self.pk:
            old = Investment.objects.filter(pk=self.pk).values(
                'opportunity_id', 'total_invested', 'primary_capital', 'status'
            ).first()
        self._old_opportunity_id = old['opportunity_id'] if old else None
        self._old_total_invested = old['total_invested'] if old else Decimal('0.00')
        self._old_primary_capital = old['primary_capital'] if old else Decimal('0.00')
        self._old_status = old['status'] if old else None
        self._compute_primary_capital()

    def _compute_primary_capital(self):
        """
        Derive primary_capital from the change being saved:
        - no opportunity: contributes nothing
        - ownership transfer (_skip_financial_sync): contributes nothing new
        - new investment, or moved to another opportunity: all of total_invested
        - otherwise: changes to total_invested are capital added or withdrawn
        """
        moved = self.pk is None or self._old_opportunity_id != self.opportunity_id
        if not self.opportunity_id:
            self.primary_capital = Decimal('0.00')
        elif getattr(self, '_skip_financial_sync', False):
            if moved:
                self.primary_capital = Decimal('0.00')
        elif moved:
            self.primary_capital = self.total_invested or Decimal('0.00')
        else:
            delta = (self.total_invested or Decimal('0.00')) - self._old_total_invested
            self.primary_capital = max(self._old_primary_capital + delta, Decimal('0.00'))

    def clean(self):
        """
        Validate that new primary capital doesn't push the opportunity past its target.

        Only the capital being *added* to the opportunity is checked, so value-only
        updates and ownership transfers are never rejected because an opportunity
        is fully funded.
        """
        from django.core.exceptions import ValidationError
        
        if not self.opportunity:
            return
        if not hasattr(self, '_old_primary_capital'):
            self._load_previous_state()
        
        previous = self._old_primary_capital if self._old_opportunity_id == self.opportunity_id else Decimal('0.00')
        added = self.primary_capital - previous
        if added <= 0:
            return
        
        target = self.opportunity.target_raise_amount
        current = self.opportunity.current_raised_amount or Decimal('0.00')
        if current + added > target:
            raise ValidationError(
                f"Total investment exceeds the target amount. "
                f"Please buy less as your amount is greater than the target raised amount. "
                f"(Target: ${target}, Current: ${current})"
            )

    def save(self, *args, **kwargs):
        """Validate, fill opportunity-derived defaults, and stash previous state for signals."""
        self._load_previous_state()
        is_new = self.pk is None
        if is_new and not self.last_accrued_date:
            # Growth starts accruing from the day after the investment is recorded
            self.last_accrued_date = timezone.now().date()
        if self.opportunity:
            if not self.name:
                self.name = self.opportunity.title
            self.sector = self.opportunity.sector
            self.expected_horizon_years = self.opportunity.investment_term_years
            if is_new and not self.fund_size:
                self.fund_size = self.opportunity.current_raised_amount
        self.full_clean()
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            kwargs['update_fields'] = set(update_fields) | {
                'name', 'sector', 'expected_horizon_years', 'primary_capital'
            }
        super().save(*args, **kwargs)
    
    def get_name(self):
        """Get investment name from opportunity title or legacy name field."""
        if self.opportunity:
            return self.opportunity.title
        return self.name or "Unnamed Investment"
    
    def get_sector(self):
        """Get sector from opportunity or legacy sector field."""
        if self.opportunity:
            return self.opportunity.sector
        return self.sector or "OTHER"
    
    def get_sector_display(self):
        """Get human-readable sector from opportunity or legacy field."""
        sector = self.get_sector()
        # Find the display name from SECTOR_CHOICES
        for choice_value, choice_display in self.SECTOR_CHOICES:
            if choice_value == sector:
                return choice_display
        return sector
    
    @property
    def target_irr(self):
        """Get target IRR from opportunity."""
        if self.opportunity:
            return self.opportunity.target_irr
        return None

    def get_expected_horizon_years(self):
        """Get expected horizon from opportunity investment term."""
        if self.opportunity:
            return self.opportunity.investment_term_years
        return self.expected_horizon_years
    
    @property
    def unrealized_gain(self):
        """Calculate unrealized gain/loss."""
        if self.current_value is not None and self.total_invested is not None:
            return self.current_value - self.total_invested
        return Decimal('0.00')
    
    @property
    def unrealized_gain_percentage(self):
        """Calculate unrealized gain/loss percentage."""
        if self.total_invested and self.total_invested > 0:
            gain = self.unrealized_gain
            if gain is not None:
                return (gain / self.total_invested) * 100
        return Decimal('0.00')
    
    @property
    def moic(self):
        """Calculate Multiple on Invested Capital."""
        if self.total_invested and self.total_invested > 0 and self.current_value is not None:
            return self.current_value / self.total_invested
        return Decimal('0.00')
    
    @property
    def expected_end_date(self):
        """Calculate expected investment end date."""
        if self.expected_horizon_years:
            from dateutil.relativedelta import relativedelta
            return self.investment_date + relativedelta(years=self.expected_horizon_years)
        return None
    
    def calculate_irr(self):
        """
        Calculate Internal Rate of Return based on capital activities.
        Returns annualized IRR as a percentage.
        """
        from .utils import calculate_investment_irr
        return calculate_investment_irr(self)
    
    def get_performance_history(self, days=365):
        """Get performance snapshots for the specified period."""
        from datetime import timedelta
        start_date = timezone.now().date() - timedelta(days=days)
        return self.performance_snapshots.filter(date__gte=start_date).order_by('date')


class CapitalActivity(models.Model):
    """
    Represents capital activities (calls, distributions) for an investment.
    """
    ACTIVITY_TYPE_CHOICES = [
        ('INITIAL_INVESTMENT', 'Initial Investment'),
        ('CAPITAL_CALL', 'Capital Call'),
        ('DISTRIBUTION', 'Distribution'),
        ('PARTIAL_EXIT', 'Partial Exit'),
        ('FULL_EXIT', 'Full Exit'),
    ]
    
    investment = models.ForeignKey(
        Investment,
        on_delete=models.CASCADE,
        related_name='capital_activities'
    )
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPE_CHOICES)
    amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Amount (negative for calls/investments, positive for distributions)"
    )
    date = models.DateField(help_text="Activity date")
    details = models.TextField(blank=True, help_text="Activity description")
    cost_basis = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Exits only: cost basis of the portion sold (realized gain = amount - cost_basis)",
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'capital_activities'
        verbose_name = 'Capital Activity'
        verbose_name_plural = 'Capital Activities'
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['investment', 'date']),
            models.Index(fields=['activity_type']),
        ]
    
    def __str__(self):
        return f"{self.get_activity_type_display()} - {self.investment.get_name()} - ${self.amount}"
    
    OUTFLOW_TYPES = ('INITIAL_INVESTMENT', 'CAPITAL_CALL')
    INFLOW_TYPES = ('DISTRIBUTION', 'PARTIAL_EXIT', 'FULL_EXIT')

    @classmethod
    def signed_amount(cls, activity_type, amount):
        """Apply the sign convention: negative for capital paid in, positive for proceeds."""
        if activity_type in cls.OUTFLOW_TYPES:
            return -abs(amount)
        if activity_type in cls.INFLOW_TYPES:
            return abs(amount)
        return amount

    def save(self, *args, **kwargs):
        """Log capital activity creation."""
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new:
            logger.info(
                f"Capital activity created: {self.activity_type} for {self.investment.get_name()}, "
                f"Amount: ${self.amount}, Date: {self.date}"
            )


class PerformanceSnapshot(models.Model):
    """
    Stores point-in-time performance data for investments.
    Used for generating performance charts and historical analysis.
    """
    investment = models.ForeignKey(
        Investment,
        on_delete=models.CASCADE,
        related_name='performance_snapshots'
    )
    date = models.DateField(help_text="Snapshot date")
    value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Investment value at this point in time"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'performance_snapshots'
        verbose_name = 'Performance Snapshot'
        verbose_name_plural = 'Performance Snapshots'
        ordering = ['date']
        unique_together = ['investment', 'date']
        indexes = [
            models.Index(fields=['investment', 'date']),
        ]
    
    def __str__(self):
        return f"{self.investment.get_name()} - {self.date} - ${self.value}"


class OwnershipTransfer(models.Model):
    """
    Represents an ownership transfer of an investment from one user to another.
    """
    TRANSFER_TYPE_CHOICES = [
        ('FULL', 'Full Transfer'),
        ('PARTIAL', 'Partial Transfer'),
    ]
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
        ('REJECTED', 'Rejected'),
    ]
    
    investment = models.ForeignKey(
        Investment,
        on_delete=models.CASCADE,
        related_name='ownership_transfers'
    )
    from_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='outgoing_transfers',
        help_text="User transferring ownership"
    )
    to_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name='incoming_transfers',
        null=True,
        blank=True,
        help_text="Recipient user (if registered)"
    )
    to_email = models.EmailField(blank=True, help_text="Recipient email (for external recipients)")
    to_name = models.CharField(max_length=255, blank=True, help_text="Recipient name/entity")
    
    # Transfer Details
    transfer_type = models.CharField(max_length=20, choices=TRANSFER_TYPE_CHOICES)
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01')), MaxValueValidator(Decimal('100.00'))],
        help_text="Percentage of ownership to transfer (for partial transfers)"
    )
    transfer_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Amount being transferred"
    )
    transfer_fee = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Transfer fee (0%)"
    )
    net_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Amount recipient receives after fees"
    )
    
    # Compliance
    reason = models.TextField(help_text="Reason for transfer (required for compliance)")
    
    # Status & Dates
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    is_processed = models.BooleanField(
        default=False,
        help_text="Flag to prevent duplicate signal processing"
    )
    initiated_date = models.DateTimeField(auto_now_add=True)
    completion_date = models.DateTimeField(null=True, blank=True)
    estimated_completion_date = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'ownership_transfers'
        verbose_name = 'Ownership Transfer'
        verbose_name_plural = 'Ownership Transfers'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['from_user', 'status']),
            models.Index(fields=['to_user', 'status']),
            models.Index(fields=['status']),
            models.Index(fields=['status', 'is_processed']),
        ]
    
    def __str__(self):
        recipient = self.to_user.email if self.to_user else self.to_email
        return f"{self.investment.get_name()} transfer from {self.from_user.email} to {recipient}"
    
    def save(self, *args, **kwargs):
        """Calculate fees and net amount before saving."""
        # Transfer fee is currently 0%
        self.transfer_fee = Decimal('0.00')
        self.net_amount = self.transfer_amount
        
        # Set estimated completion date if not set
        if not self.estimated_completion_date and self.status == 'PENDING':
            from datetime import timedelta
            self.estimated_completion_date = timezone.now() + timedelta(days=10)
        
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new:
            logger.info(
                f"Ownership transfer created: {self.investment.get_name()} from {self.from_user.email}, "
                f"Amount: ${self.transfer_amount}, Status: {self.status}"
            )


class TransferDocument(models.Model):
    """
    Stores documents related to ownership transfers.
    """
    DOCUMENT_TYPE_CHOICES = [
        ('RECEIPT', 'Transfer Receipt'),
        ('AGREEMENT', 'Transfer Agreement'),
        ('COMPLIANCE', 'Compliance Document'),
        ('OTHER', 'Other'),
    ]
    
    transfer = models.ForeignKey(
        OwnershipTransfer,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPE_CHOICES, default='OTHER')
    file = models.FileField(upload_to='transfers/documents/', help_text="Document file")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'transfer_documents'
        verbose_name = 'Transfer Document'
        verbose_name_plural = 'Transfer Documents'
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.get_document_type_display()} - {self.transfer}"


class SecondaryMarketInterest(models.Model):
    """
    Records a buyer's interest in a specific secondary-market listing
    (OwnershipTransfer). When the status transitions to CONVERTED, a signal
    automatically executes the financial transfer: deducting from the seller's
    Investment and creating/topping-up the buyer's Investment.
    """
    STATUS_CHOICES = [
        ('PENDING',   'Pending'),
        ('CONVERTED', 'Converted'),
        ('CANCELLED', 'Cancelled'),
    ]

    transfer = models.ForeignKey(
        OwnershipTransfer,
        on_delete=models.CASCADE,
        related_name='buyer_interests',
        help_text='The secondary-market listing (OwnershipTransfer) the buyer is interested in',
    )
    buyer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='secondary_market_interests',
        help_text='The user expressing interest (buyer)',
    )
    amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text='Amount the buyer wants to acquire (must be ≤ transfer.transfer_amount)',
    )
    interest_date = models.DateField(
        default=timezone.now,
        help_text='Date of interest / expected settlement date',
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'secondary_market_interests'
        verbose_name = 'Secondary Market Interest'
        verbose_name_plural = 'Secondary Market Interests'
        ordering = ['-created_at']
        # One buyer per transfer listing (idempotency guard)
        unique_together = [('transfer', 'buyer')]
        indexes = [
            models.Index(fields=['transfer', 'status']),
            models.Index(fields=['buyer', 'status']),
        ]

    def __str__(self):
        return (
            f"{self.buyer.email} → {self.transfer} "
            f"(${self.amount}, {self.status})"
        )
