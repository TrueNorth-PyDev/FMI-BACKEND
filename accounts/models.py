from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger('accounts')


class User(AbstractUser):
    """
    Custom User model for PrivCap Hub investors.
    Extends Django's AbstractUser with investor-specific fields and security features.
    """
    email = models.EmailField(unique=True, db_index=True)
    username = models.CharField(max_length=150, unique=True, blank=True, null=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    
    # Profile fields
    phone_number = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    profile_photo = models.ImageField(upload_to='profiles/', blank=True, null=True)
    is_verified = models.BooleanField(default=False, help_text="Premium investor verification status")
    member_since = models.DateField(auto_now_add=True)
    
    # Investment profile
    INVESTOR_TYPE_CHOICES = [
        ('ACCREDITED', 'Accredited Investor'),
        ('QUALIFIED', 'Qualified Purchaser'),
        ('INSTITUTIONAL', 'Institutional Investor'),
    ]
    
    RISK_TOLERANCE_CHOICES = [
        ('CONSERVATIVE', 'Conservative'),
        ('MODERATE', 'Moderate'),
        ('AGGRESSIVE', 'Aggressive'),
        ('MODERATE_TO_AGGRESSIVE', 'Moderate to Aggressive'),
    ]
    
    investor_type = models.CharField(max_length=20, choices=INVESTOR_TYPE_CHOICES, blank=True)
    risk_tolerance = models.CharField(max_length=30, choices=RISK_TOLERANCE_CHOICES, blank=True)
    investment_preferences = models.JSONField(default=list, blank=True, help_text="List of preferred sectors")
    
    # Email verification
    is_email_verified = models.BooleanField(default=False)
    
    # Security fields
    failed_login_attempts = models.IntegerField(default=0)
    account_locked_until = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Use email as the primary authentication field
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']
    
    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.email
    
    def get_full_name(self):
        """Return the user's full name."""
        return f"{self.first_name} {self.last_name}".strip()
    
    def is_account_locked(self):
        """Check if the account is currently locked."""
        if self.account_locked_until:
            if timezone.now() < self.account_locked_until:
                return True
            else:
                # Unlock account if lockout period has passed
                self.account_locked_until = None
                self.failed_login_attempts = 0
                self.save(update_fields=['account_locked_until', 'failed_login_attempts'])
        return False
    
    def increment_failed_login(self):
        """Increment failed login attempts and lock account if threshold exceeded."""
        from django.conf import settings
        
        self.failed_login_attempts += 1
        
        if self.failed_login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
            self.account_locked_until = timezone.now() + timedelta(minutes=settings.ACCOUNT_LOCKOUT_DURATION)
            logger.warning(
                f"Account locked for user {self.email} after {self.failed_login_attempts} failed attempts. "
                f"Locked until {self.account_locked_until}"
            )
        
        self.save(update_fields=['failed_login_attempts', 'account_locked_until'])
    
    def reset_failed_login(self):
        """Reset failed login attempts on successful login."""
        if self.failed_login_attempts > 0 or self.account_locked_until:
            self.failed_login_attempts = 0
            self.account_locked_until = None
            self.save(update_fields=['failed_login_attempts', 'account_locked_until'])
    
    def save(self, *args, **kwargs):
        # Generate username from email if not provided
        if not self.username:
            self.username = self.email.split('@')[0]
            # Ensure uniqueness
            base_username = self.username
            counter = 1
            while User.objects.filter(username=self.username).exclude(pk=self.pk).exists():
                self.username = f"{base_username}{counter}"
                counter += 1
        
        super().save(*args, **kwargs)


class OTP(models.Model):
    """
    One-Time Password model for email verification and password reset.
    """
    OTP_TYPE_CHOICES = [
        ('EMAIL_VERIFICATION', 'Email Verification'),
        ('PASSWORD_RESET', 'Password Reset'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otps')
    otp_code = models.CharField(max_length=6)
    otp_type = models.CharField(max_length=20, choices=OTP_TYPE_CHOICES)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'otps'
        verbose_name = 'OTP'
        verbose_name_plural = 'OTPs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'otp_type', 'is_used']),
            models.Index(fields=['otp_code', 'otp_type']),
        ]
    
    def __str__(self):
        return f"{self.otp_type} OTP for {self.user.email}"
    
    def is_valid(self):
        """Check if OTP is still valid (not used and not expired)."""
        return not self.is_used and timezone.now() < self.expires_at
    
    def mark_as_used(self):
        """Mark OTP as used."""
        self.is_used = True
        self.save(update_fields=['is_used'])
        logger.info(f"OTP {self.otp_code} marked as used for {self.user.email}")
    
    @classmethod
    def create_otp(cls, user, otp_type):
        """
        Create a new OTP for the user.
        Invalidates any existing unused OTPs of the same type.
        """
        from django.conf import settings
        import random
        
        # Invalidate existing unused OTPs of the same type
        cls.objects.filter(
            user=user,
            otp_type=otp_type,
            is_used=False
        ).update(is_used=True)
        
        # Generate OTP code
        otp_code = ''.join([str(random.randint(0, 9)) for _ in range(settings.OTP_LENGTH)])
        
        # Create new OTP
        otp = cls.objects.create(
            user=user,
            otp_code=otp_code,
            otp_type=otp_type,
            expires_at=timezone.now() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)
        )
        
        logger.info(f"Created {otp_type} OTP for {user.email}")
        return otp


class UserNotificationPreference(models.Model):
    """
    User notification preferences for different types of notifications.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='notification_preferences')
    
    # Notification types
    portfolio_updates = models.BooleanField(default=True, help_text="Quarterly valuations and performance reports")
    transfer_notifications = models.BooleanField(default=True, help_text="Updates on ownership transfers")
    market_opportunities = models.BooleanField(default=False, help_text="New investment opportunities")
    distribution_notices = models.BooleanField(default=True, help_text="Cash distributions and dividend payments")
    security_alerts = models.BooleanField(default=True, help_text="Login attempts and security activities")
    
    # Delivery methods
    email_notifications = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_notification_preferences'
        verbose_name = 'Notification Preference'
        verbose_name_plural = 'Notification Preferences'
    
    def __str__(self):
        return f"Notification preferences for {self.user.email}"


class UserDocument(models.Model):
    """
    Documents uploaded by or for users (investment agreements, reports, tax docs, etc.).
    """
    DOCUMENT_TYPE_CHOICES = [
        ('LEGAL', 'Legal'),
        ('REPORT', 'Report'),
        ('TAX', 'Tax'),
        ('OTHER', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('NEW', 'New'),
        ('REQUIRED', 'Required'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents')
    title = models.CharField(max_length=255)
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPE_CHOICES)
    file = models.FileField(upload_to='user_documents/')
    file_size = models.IntegerField(help_text="File size in bytes")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NEW')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'user_documents'
        verbose_name = 'User Document'
        verbose_name_plural = 'User Documents'
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.title} - {self.user.email}"
    
    def get_file_size_mb(self):
        """Return file size in MB."""
        if self.file_size:
            return round(self.file_size / (1024 * 1024), 1)
        return 0.0


class UserActivity(models.Model):
    """
    Log of user activities for audit trail and activity feed.
    """
    ACTIVITY_TYPE_CHOICES = [
        ('PROFILE_UPDATE', 'Profile Updated'),
        ('PASSWORD_CHANGE', 'Password Changed'),
        ('TRANSFER_INITIATED', 'Transfer Initiated'),
        ('DOCUMENT_UPLOADED', 'Document Uploaded'),
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
        ('PORTFOLIO_UPDATE', 'Portfolio Value Updated'),
        ('2FA_ENABLED', 'Two-Factor Authentication Enabled'),
        ('2FA_DISABLED', 'Two-Factor Authentication Disabled'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=30, choices=ACTIVITY_TYPE_CHOICES)
    description = models.TextField()
    metadata = models.JSONField(default=dict, blank=True, help_text="Additional activity data")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'user_activities'
        verbose_name = 'User Activity'
        verbose_name_plural = 'User Activities'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['activity_type']),
        ]
    
    def __str__(self):
        return f"{self.get_activity_type_display()} - {self.user.email}"
    
    @classmethod
    def log_activity(cls, user, activity_type, description, metadata=None, ip_address=None):
        """Helper method to log user activity."""
        activity = cls.objects.create(
            user=user,
            activity_type=activity_type,
            description=description,
            metadata=metadata or {},
            ip_address=ip_address
        )
        logger.info(f"Activity logged: {activity_type} for {user.email}")
        return activity


class UserSession(models.Model):
    """
    Track active user sessions for security monitoring.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    device_name = models.CharField(max_length=255, help_text="Device identifier (e.g., MacBook Pro)")
    location = models.CharField(max_length=255, help_text="Location (e.g., New York, NY)")
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    is_current = models.BooleanField(default=False)
    session_key = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_sessions'
        verbose_name = 'User Session'
        verbose_name_plural = 'User Sessions'
        ordering = ['-last_activity']
        indexes = [
            models.Index(fields=['user', '-last_activity']),
            models.Index(fields=['session_key']),
        ]
    
    def __str__(self):
        return f"{self.device_name} - {self.user.email}"


class InvestorProfile(models.Model):
    """
    Public investor profile for networking and discovery.
    """
    INVESTOR_CATEGORY_CHOICES = [
        ('FAMILY_OFFICE', 'Family Office'),
        ('ANGEL', 'Angel Investor'),
        ('VC', 'Venture Capital'),
        ('PE', 'Private Equity'),
        ('INSTITUTIONAL', 'Institutional Investor'),
        ('INDIVIDUAL', 'Individual Investor'),
    ]
    
    RISK_PROFILE_CHOICES = [
        ('CONSERVATIVE', 'Conservative'),
        ('BALANCED', 'Balanced'),
        ('GROWTH_FOCUSED', 'Growth-focused'),
        ('AGGRESSIVE', 'Aggressive'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='investor_profile')
    display_name = models.CharField(max_length=255, help_text="Public display name")
    investor_category = models.CharField(max_length=20, choices=INVESTOR_CATEGORY_CHOICES)
    bio = models.TextField(blank=True, help_text="About the investor")
    investment_philosophy = models.TextField(blank=True)
    
    # Location
    location_city = models.CharField(max_length=100, blank=True)
    location_country = models.CharField(max_length=100, blank=True)
    
    # Investment preferences
    min_investment = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    max_investment = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    preferred_sectors = models.JSONField(default=list, blank=True, help_text="List of preferred sectors")
    preferred_stages = models.JSONField(default=list, blank=True, help_text="Seed, Series A, B, etc.")
    risk_profile = models.CharField(max_length=20, choices=RISK_PROFILE_CHOICES, blank=True)
    
    # Privacy settings
    is_public = models.BooleanField(default=True, help_text="Show in investor directory")
    is_accepting_connections = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'investor_profiles'
        verbose_name = 'Investor Profile'
        verbose_name_plural = 'Investor Profiles'
        indexes = [
            models.Index(fields=['is_public', 'is_accepting_connections']),
            models.Index(fields=['location_country', 'location_city']),
        ]
    
    def __str__(self):
        return f"{self.display_name} ({self.user.email})"
    
    def get_location(self):
        """Get formatted location string."""
        if self.location_city and self.location_country:
            return f"{self.location_city}, {self.location_country}"
        return self.location_country or self.location_city or "Not specified"


class InvestorConnection(models.Model):
    """
    Connection requests between investors.
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('ACCEPTED', 'Accepted'),
        ('REJECTED', 'Rejected'),
    ]
    
    from_investor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_connections')
    to_investor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_connections')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    message = models.TextField(blank=True, help_text="Connection request message")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'investor_connections'
        verbose_name = 'Investor Connection'
        verbose_name_plural = 'Investor Connections'
        unique_together = ['from_investor', 'to_investor']
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['from_investor', 'status']),
            models.Index(fields=['to_investor', 'status']),
        ]
    
    def __str__(self):
        return f"{self.from_investor.email} -> {self.to_investor.email} ({self.status})"


