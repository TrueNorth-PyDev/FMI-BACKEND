from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from accounts.models import User
from decimal import Decimal
import logging

logger = logging.getLogger('marketplace')


class MarketplaceOpportunity(models.Model):
    """
    Represents an investment opportunity available in the marketplace.
    """
    STATUS_CHOICES = [
        ('NEW', 'New'),
        ('ACTIVE', 'Active'),
        ('CLOSING_SOON', 'Closing Soon'),
        ('CLOSED', 'Closed'),
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
    
    INVESTMENT_TYPE_CHOICES = [
        ('FIXED', 'Fixed Investment'),
        ('VARIABLE', 'Variable Investment'),
    ]
    
    RISK_LEVEL_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
    ]
    
    PAYOUT_FREQUENCY_CHOICES = [
        ('MONTHLY', 'Monthly'),
        ('QUARTERLY', 'Quarterly'),
        ('ANNUALLY', 'Annually'),
    ]
    
    VERIFICATION_TYPE_CHOICES = [
        ('VERIFIED', 'Verified'),
        ('PENDING', 'Pending'),
        ('UNVERIFIED', 'Unverified'),
    ]
    
    # Basic Information
    title = models.CharField(max_length=255, help_text="Investment opportunity name")
    description = models.TextField(help_text="Short description")
    detailed_description = models.TextField(blank=True, help_text="Full investment memo")
    sector = models.CharField(max_length=20, choices=SECTOR_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    
    # Financial Details
    min_investment = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Minimum investment amount"
    )
    target_raise_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Total funding goal"
    )
    current_raised_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Amount raised so far"
    )
    target_irr = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Target IRR percentage"
    )
    
    # Investment Terms
    investment_term_years = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="Investment duration in years"
    )
    investment_type = models.CharField(max_length=20, choices=INVESTMENT_TYPE_CHOICES, default='FIXED')
    risk_level = models.CharField(max_length=20, choices=RISK_LEVEL_CHOICES, default='MEDIUM')
    payout_frequency = models.CharField(max_length=20, choices=PAYOUT_FREQUENCY_CHOICES, default='ANNUALLY')
    currency = models.CharField(max_length=10, default='NGN', help_text="Currency code")
    
    # Metrics
    rating = models.DecimalField(
        max_digits=2,
        decimal_places=1,
        default=Decimal('0.0'),
        validators=[MinValueValidator(Decimal('0.0')), MaxValueValidator(Decimal('5.0'))],
        help_text="Star rating (0-5)"
    )
    investors_count = models.IntegerField(default=0, help_text="Number of investors")
    platform_rating = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Platform rating score"
    )
    
    # Verification & Trust
    verification_type = models.CharField(max_length=20, choices=VERIFICATION_TYPE_CHOICES, default='PENDING')
    
    # Contact Information
    contact_phone = models.CharField(max_length=20, blank=True)
    contact_email = models.EmailField(blank=True)
    location = models.CharField(max_length=255, blank=True)
    
    # Additional Details
    run_rate_sales_min = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum run rate sales"
    )
    run_rate_sales_max = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum run rate sales"
    )
    investment_requirements = models.TextField(blank=True, help_text="Investment criteria/requirements")
    disclaimer = models.TextField(blank=True, help_text="Legal disclaimer")
    
    # Flags
    is_featured = models.BooleanField(default=False, help_text="Featured opportunity")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'marketplace_opportunities'
        verbose_name = 'Marketplace Opportunity'
        verbose_name_plural = 'Marketplace Opportunities'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'sector']),
            models.Index(fields=['is_featured']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return self.title
    
    @property
    def funding_progress_percentage(self):
        """Calculate funding progress as a percentage."""
        if self.target_raise_amount and self.target_raise_amount > 0 and self.current_raised_amount is not None:
            return (self.current_raised_amount / self.target_raise_amount * 100)
        return Decimal('0.00')
    
    @property
    def remaining_amount(self):
        """Calculate remaining amount to be raised."""
        if self.target_raise_amount is not None and self.current_raised_amount is not None:
            return self.target_raise_amount - self.current_raised_amount
        return Decimal('0.00')


class OpportunityDocument(models.Model):
    """
    Stores documents related to marketplace opportunities.
    """
    DOCUMENT_TYPE_CHOICES = [
        ('MEMO', 'Investment Memo'),
        ('RATING', 'DataPro Rating'),
        ('PROSPECTUS', 'Prospectus'),
        ('FINANCIAL', 'Financial Statement'),
        ('OTHER', 'Other'),
    ]
    
    opportunity = models.ForeignKey(
        MarketplaceOpportunity,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    title = models.CharField(max_length=255, help_text="Document name")
    file = models.FileField(upload_to='marketplace/documents/', help_text="Document file")
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPE_CHOICES, default='OTHER')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'opportunity_documents'
        verbose_name = 'Opportunity Document'
        verbose_name_plural = 'Opportunity Documents'
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.title} - {self.opportunity.title}"


class OpportunityTag(models.Model):
    """
    Tags for categorizing and filtering opportunities.
    """
    TAG_TYPE_CHOICES = [
        ('INDUSTRY', 'Industry'),
        ('FEATURE', 'Feature'),
        ('STATUS', 'Status'),
        ('OTHER', 'Other'),
    ]
    
    opportunity = models.ForeignKey(
        MarketplaceOpportunity,
        on_delete=models.CASCADE,
        related_name='tags'
    )
    tag_name = models.CharField(max_length=100, help_text="Tag text")
    tag_type = models.CharField(max_length=20, choices=TAG_TYPE_CHOICES, default='OTHER')
    
    class Meta:
        db_table = 'opportunity_tags'
        verbose_name = 'Opportunity Tag'
        verbose_name_plural = 'Opportunity Tags'
        unique_together = ['opportunity', 'tag_name']
    
    def __str__(self):
        return f"{self.tag_name} ({self.opportunity.title})"


class InvestmentInterest(models.Model):
    """
    Tracks user interest in marketplace opportunities.
    """
    INTEREST_TYPE_CHOICES = [
        ('BOOKMARKED', 'Bookmarked'),
        ('REQUESTED_INFO', 'Requested Information'),
        ('INVESTED', 'Invested'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='investment_interests')
    opportunity = models.ForeignKey(
        MarketplaceOpportunity,
        on_delete=models.CASCADE,
        related_name='interested_users'
    )
    interest_type = models.CharField(max_length=20, choices=INTEREST_TYPE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'investment_interests'
        verbose_name = 'Investment Interest'
        verbose_name_plural = 'Investment Interests'
        unique_together = ['user', 'opportunity', 'interest_type']
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'interest_type']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.get_interest_type_display()} - {self.opportunity.title}"
    
    def save(self, *args, **kwargs):
        """Log interest creation."""
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new:
            logger.info(
                f"Investment interest created: {self.user.email} {self.interest_type} "
                f"in {self.opportunity.title}"
            )
