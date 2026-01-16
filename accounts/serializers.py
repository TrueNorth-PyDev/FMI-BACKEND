"""
Serializers for the accounts app.
Handles user registration, authentication, email verification, and password reset.
"""

from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from django.db.models import Q, Sum
from .models import User, OTP
from .utils import send_verification_email, send_password_reset_email, send_welcome_email, log_auth_event
import logging

logger = logging.getLogger('accounts')


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration."""
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True, required=True)
    
    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'username', 'password', 'password_confirm']
        extra_kwargs = {
            'username': {'required': False},
            'first_name': {'required': True},
            'last_name': {'required': True},
        }
    
    def validate(self, attrs):
        """Validate password confirmation."""
        if attrs['password'] != attrs.pop('password_confirm'):
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs
    
    def validate_email(self, value):
        """Validate email uniqueness."""
        if User.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower()
    
    def create(self, validated_data):
        """Create user and send verification email."""
        username = validated_data.get('username')
        if not username:
             username = validated_data['email'].split('@')[0]

        user = User.objects.create_user(
            email=validated_data['email'],
            username=username,
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            password=validated_data['password'],
            is_email_verified=False
        )
        
        # Create and send OTP
        otp = OTP.create_otp(user, 'EMAIL_VERIFICATION')
        send_verification_email(user, otp)
        
        logger.info(f"New user registered: {user.email}")
        return user


class EmailVerificationSerializer(serializers.Serializer):
    """Serializer for email verification."""
    email = serializers.EmailField(required=True)
    otp_code = serializers.CharField(required=True, max_length=6, min_length=6)
    
    def validate(self, attrs):
        """Validate OTP code."""
        email = attrs.get('email').lower()
        otp_code = attrs.get('otp_code')
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "User not found."})
        
        if user.is_email_verified:
            raise serializers.ValidationError({"email": "Email is already verified."})
        
        try:
            otp = OTP.objects.get(
                user=user,
                otp_code=otp_code,
                otp_type='EMAIL_VERIFICATION',
                is_used=False
            )
        except OTP.DoesNotExist:
            raise serializers.ValidationError({"otp_code": "Invalid verification code."})
        
        if not otp.is_valid():
            raise serializers.ValidationError({"otp_code": "Verification code has expired."})
        
        attrs['user'] = user
        attrs['otp'] = otp
        return attrs
    
    def save(self):
        """Mark email as verified."""
        user = self.validated_data['user']
        otp = self.validated_data['otp']
        
        user.is_email_verified = True
        user.save(update_fields=['is_email_verified'])
        
        otp.mark_as_used()
        send_welcome_email(user)
        
        logger.info(f"Email verified for user: {user.email}")
        return user


class ResendOTPSerializer(serializers.Serializer):
    """Serializer for resending OTP."""
    email = serializers.EmailField(required=True)
    otp_type = serializers.ChoiceField(choices=['EMAIL_VERIFICATION', 'PASSWORD_RESET'], required=True)
    
    def validate(self, attrs):
        """Validate user exists."""
        email = attrs.get('email').lower()
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "User not found."})
        
        attrs['user'] = user
        return attrs
    
    def save(self):
        """Create and send new OTP."""
        user = self.validated_data['user']
        otp_type = self.validated_data['otp_type']
        
        otp = OTP.create_otp(user, otp_type)
        
        if otp_type == 'EMAIL_VERIFICATION':
            send_verification_email(user, otp)
        else:
            send_password_reset_email(user, otp)
        
        logger.info(f"OTP resent to {user.email} for {otp_type}")
        return user


class LoginSerializer(serializers.Serializer):
    """Serializer for user login."""
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True)
    
    def validate(self, attrs):
        """Validate credentials and account status."""
        email = attrs.get('email').lower()
        password = attrs.get('password')
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"detail": "Invalid credentials."})
        
        # Check if account is locked
        if user.is_account_locked():
            raise serializers.ValidationError({
                "detail": f"Account is locked due to multiple failed login attempts. "
                         f"Please try again after {user.account_locked_until.strftime('%Y-%m-%d %H:%M:%S')}."
            })
        
        # Check if email is verified
        if not user.is_email_verified:
            raise serializers.ValidationError({
                "detail": "Please verify your email before logging in.",
                "email_verified": False
            })
        
        # Authenticate user
        user_auth = authenticate(username=email, password=password)
        
        if user_auth is None:
            user.increment_failed_login()
            raise serializers.ValidationError({"detail": "Invalid credentials."})
        
        # Reset failed login attempts on successful authentication
        user.reset_failed_login()
        
        attrs['user'] = user
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer for password reset request."""
    email = serializers.EmailField(required=True)
    
    def validate_email(self, value):
        """Validate user exists."""
        email = value.lower()
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Don't reveal if email exists or not for security
            raise serializers.ValidationError("If this email exists, you will receive a password reset code.")
        return email
    
    def save(self):
        """Create and send password reset OTP."""
        email = self.validated_data['email']
        
        try:
            user = User.objects.get(email=email)
            otp = OTP.create_otp(user, 'PASSWORD_RESET')
            send_password_reset_email(user, otp)
            logger.info(f"Password reset requested for {user.email}")
        except User.DoesNotExist:
            # Silently fail for security
            pass
        
        return True


class PasswordResetVerifySerializer(serializers.Serializer):
    """Serializer for verifying password reset OTP."""
    email = serializers.EmailField(required=True)
    otp_code = serializers.CharField(required=True, max_length=6, min_length=6)
    
    def validate(self, attrs):
        """Validate OTP code."""
        email = attrs.get('email').lower()
        otp_code = attrs.get('otp_code')
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "User not found."})
        
        try:
            otp = OTP.objects.get(
                user=user,
                otp_code=otp_code,
                otp_type='PASSWORD_RESET',
                is_used=False
            )
        except OTP.DoesNotExist:
            raise serializers.ValidationError({"otp_code": "Invalid reset code."})
        
        if not otp.is_valid():
            raise serializers.ValidationError({"otp_code": "Reset code has expired."})
        
        attrs['user'] = user
        attrs['otp'] = otp
        return attrs


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer for confirming password reset."""
    email = serializers.EmailField(required=True)
    otp_code = serializers.CharField(required=True, max_length=6, min_length=6)
    new_password = serializers.CharField(required=True, write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(required=True, write_only=True)
    
    def validate(self, attrs):
        """Validate passwords match and OTP is valid."""
        if attrs['new_password'] != attrs.pop('new_password_confirm'):
            raise serializers.ValidationError({"new_password": "Password fields didn't match."})
        
        email = attrs.get('email').lower()
        otp_code = attrs.get('otp_code')
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "User not found."})
        
        try:
            otp = OTP.objects.get(
                user=user,
                otp_code=otp_code,
                otp_type='PASSWORD_RESET',
                is_used=False
            )
        except OTP.DoesNotExist:
            raise serializers.ValidationError({"otp_code": "Invalid reset code."})
        
        if not otp.is_valid():
            raise serializers.ValidationError({"otp_code": "Reset code has expired."})
        
        attrs['user'] = user
        attrs['otp'] = otp
        return attrs
    
    def save(self):
        """Reset password."""
        user = self.validated_data['user']
        otp = self.validated_data['otp']
        new_password = self.validated_data['new_password']
        
        user.set_password(new_password)
        user.save()
        
        otp.mark_as_used()
        
        logger.info(f"Password reset completed for {user.email}")
        return user


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user profile."""
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'full_name', 
                  'is_email_verified', 'created_at', 'updated_at']
        read_only_fields = ['id', 'email', 'is_email_verified', 'created_at', 'updated_at']


# Account Management Serializers

class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for extended user profile information."""
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    portfolio_value = serializers.SerializerMethodField()
    active_investments_count = serializers.SerializerMethodField()
    investor_type_display = serializers.CharField(source='get_investor_type_display', read_only=True)
    risk_tolerance_display = serializers.CharField(source='get_risk_tolerance_display', read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'full_name',
            'phone_number', 'country', 'address', 'profile_photo',
            'is_verified', 'member_since', 'investor_type', 'investor_type_display',
            'risk_tolerance', 'risk_tolerance_display', 'investment_preferences',
            'portfolio_value', 'active_investments_count'
        ]
        read_only_fields = ['id', 'email', 'is_verified', 'member_since']
    
    def get_portfolio_value(self, obj):
        """Get total portfolio value."""
        from investments.models import Investment
        # Sum import handled by top usage if needed, or locally
        from django.db.models import Sum
        
        total = Investment.objects.filter(
            user=obj,
            status__in=['ACTIVE', 'UNDERPERFORMING']
        ).aggregate(total=Sum('current_value'))['total']
        
        return float(total) if total else 0.0
    
    def get_active_investments_count(self, obj):
        """Get count of active investments."""
        from investments.models import Investment
        
        return Investment.objects.filter(
            user=obj,
            status__in=['ACTIVE', 'UNDERPERFORMING']
        ).count()


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for password change."""
    current_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(required=True, write_only=True)
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs


from .models import UserNotificationPreference, UserDocument, UserActivity, UserSession


class UserNotificationPreferenceSerializer(serializers.ModelSerializer):
    """Serializer for notification preferences."""
    
    class Meta:
        model = UserNotificationPreference
        fields = [
            'portfolio_updates', 'transfer_notifications', 'market_opportunities',
            'distribution_notices', 'security_alerts', 'email_notifications', 'sms_notifications'
        ]


class UserDocumentSerializer(serializers.ModelSerializer):
    """Serializer for user documents."""
    document_type_display = serializers.CharField(source='get_document_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    file_size_mb = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = UserDocument
        fields = [
            'id', 'title', 'document_type', 'document_type_display',
            'status', 'status_display', 'file', 'file_url', 'file_size',
            'file_size_mb', 'uploaded_at'
        ]
        read_only_fields = ['id', 'uploaded_at', 'file_size']
    
    def get_file_size_mb(self, obj):
        return obj.get_file_size_mb()
    
    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None


class UserActivitySerializer(serializers.ModelSerializer):
    """Serializer for user activity log."""
    activity_type_display = serializers.CharField(source='get_activity_type_display', read_only=True)
    time_ago = serializers.SerializerMethodField()
    
    class Meta:
        model = UserActivity
        fields = [
            'id', 'activity_type', 'activity_type_display',
            'description', 'metadata', 'created_at', 'time_ago'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_time_ago(self, obj):
        """Get human-readable time ago."""
        from django.utils import timezone
        from datetime import timedelta
        
        now = timezone.now()
        diff = now - obj.created_at
        
        if diff < timedelta(hours=1):
            minutes = int(diff.total_seconds() / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago" if minutes > 0 else "Just now"
        elif diff < timedelta(days=1):
            hours = int(diff.total_seconds() / 3600)
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif diff < timedelta(days=7):
            days = diff.days
            return f"{days} day{'s' if days != 1 else ''} ago"
        elif diff < timedelta(days=30):
            weeks = diff.days // 7
            return f"{weeks} week{'s' if weeks != 1 else ''} ago"
        else:
            months = diff.days // 30
            return f"{months} month{'s' if months != 1 else ''} ago"


class UserSessionSerializer(serializers.ModelSerializer):
    """Serializer for user sessions."""
    
    class Meta:
        model = UserSession
        fields = [
            'id', 'device_name', 'location', 'ip_address',
            'is_current', 'created_at', 'last_activity'
        ]
        read_only_fields = ['id', 'created_at', 'last_activity']


# Investor Network Serializers

from .models import InvestorProfile, InvestorConnection


class InvestorProfileSerializer(serializers.ModelSerializer):
    """Serializer for investor profiles."""
    investor_category_display = serializers.CharField(source='get_investor_category_display', read_only=True)
    risk_profile_display = serializers.CharField(source='get_risk_profile_display', read_only=True)
    location = serializers.CharField(source='get_location', read_only=True)
    
    class Meta:
        model = InvestorProfile
        fields = [
            'id', 'display_name', 'investor_category', 'investor_category_display',
            'bio', 'investment_philosophy', 'location_city', 'location_country', 'location',
            'min_investment', 'max_investment', 'preferred_sectors', 'preferred_stages',
            'risk_profile', 'risk_profile_display', 'is_public', 'is_accepting_connections'
        ]


class InvestorListSerializer(serializers.ModelSerializer):
    """Serializer for investor directory listing."""
    investor_category_display = serializers.CharField(source='get_investor_category_display', read_only=True)
    location = serializers.CharField(source='get_location', read_only=True)
    investments_count = serializers.SerializerMethodField()
    total_invested = serializers.SerializerMethodField()
    current_value = serializers.SerializerMethodField()
    connection_status = serializers.SerializerMethodField()
    
    class Meta:
        model = InvestorProfile
        fields = [
            'id', 'display_name', 'investor_category', 'investor_category_display',
            'location', 'investments_count', 'total_invested', 'current_value',
            'preferred_sectors', 'connection_status'
        ]
    
    def get_investments_count(self, obj):
        """Get number of investments."""
        from investments.models import Investment
        return Investment.objects.filter(
            user=obj.user,
            status__in=['ACTIVE', 'UNDERPERFORMING']
        ).count()
    
    def get_total_invested(self, obj):
        """Get total invested amount."""
        from investments.models import Investment
        
        total = Investment.objects.filter(
            user=obj.user,
            status__in=['ACTIVE', 'UNDERPERFORMING']
        ).aggregate(total=Sum('total_invested'))['total']
        
        return float(total) if total else 0.0
    
    def get_current_value(self, obj):
        """Get current portfolio value."""
        from investments.models import Investment
        
        total = Investment.objects.filter(
            user=obj.user,
            status__in=['ACTIVE', 'UNDERPERFORMING']
        ).aggregate(total=Sum('current_value'))['total']
        
        return float(total) if total else 0.0
    
    def get_connection_status(self, obj):
        """Get connection status with current user."""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        
        if obj.user == request.user:
            return 'self'
        
        # Check if connection exists
        connection = InvestorConnection.objects.filter(
            Q(from_investor=request.user, to_investor=obj.user) |
            Q(from_investor=obj.user, to_investor=request.user)
        ).first()
        
        if connection:
            return connection.status.lower()
        
        return None


class InvestorConnectionSerializer(serializers.ModelSerializer):
    """Serializer for investor connections."""
    from_investor_name = serializers.CharField(source='from_investor.get_full_name', read_only=True)
    to_investor_name = serializers.CharField(source='to_investor.get_full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = InvestorConnection
        fields = [
            'id', 'from_investor', 'from_investor_name',
            'to_investor', 'to_investor_name',
            'status', 'status_display', 'message', 'created_at'
        ]
        read_only_fields = ['id', 'from_investor', 'created_at']
