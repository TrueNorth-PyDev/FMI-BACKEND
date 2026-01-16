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
    name = models.CharField(max_length=255, help_text="Fund/Investment name")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    sector = models.CharField(max_length=20, choices=SECTOR_CHOICES)
    
    # Financial details
    total_invested = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Total amount invested"
    )
    current_value = models.DecimalField(
        max_digits=15,
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
        return f"{self.name} - {self.user.email}"
    
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
            from datetime import timedelta
            return self.investment_date + timedelta(days=365 * self.expected_horizon_years)
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
        return f"{self.get_activity_type_display()} - {self.investment.name} - ${self.amount}"
    
    def save(self, *args, **kwargs):
        """Log capital activity creation."""
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new:
            logger.info(
                f"Capital activity created: {self.activity_type} for {self.investment.name}, "
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
        return f"{self.investment.name} - {self.date} - ${self.value}"


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
        help_text="Transfer fee (2.5%)"
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
        return f"{self.investment.name} transfer from {self.from_user.email} to {recipient}"
    
    def save(self, *args, **kwargs):
        """Calculate fees and net amount before saving."""
        # Calculate transfer fee (2.5%)
        self.transfer_fee = self.transfer_amount * Decimal('0.025')
        self.net_amount = self.transfer_amount - self.transfer_fee
        
        # Set estimated completion date if not set
        if not self.estimated_completion_date and self.status == 'PENDING':
            from datetime import timedelta
            self.estimated_completion_date = timezone.now() + timedelta(days=10)
        
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new:
            logger.info(
                f"Ownership transfer created: {self.investment.name} from {self.from_user.email}, "
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

