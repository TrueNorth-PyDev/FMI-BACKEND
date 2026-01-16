from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, OTP, UserNotificationPreference, UserDocument, UserActivity, UserSession, InvestorProfile, InvestorConnection


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom admin for User model."""
    list_display = ['email', 'first_name', 'last_name', 'is_verified', 'is_email_verified', 'is_active', 'created_at']
    list_filter = ['is_verified', 'is_email_verified', 'is_active', 'is_staff', 'investor_type', 'created_at']
    search_fields = ['email', 'first_name', 'last_name', 'username', 'phone_number']
    ordering = ['-created_at']
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'username', 'phone_number', 'country', 'address', 'profile_photo')}),
        ('Investment Profile', {'fields': ('investor_type', 'risk_tolerance', 'investment_preferences', 'is_verified', 'member_since')}),
        ('Verification', {'fields': ('is_email_verified',)}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Security', {'fields': ('failed_login_attempts', 'account_locked_until', 'last_login_ip')}),
        ('Important Dates', {'fields': ('last_login', 'created_at', 'updated_at')}),
    )
    
    readonly_fields = ['created_at', 'updated_at', 'last_login', 'member_since']
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'password1', 'password2'),
        }),
    )


@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    """Admin for OTP model."""
    list_display = ['user', 'otp_type', 'otp_code', 'is_used', 'expires_at', 'created_at']
    list_filter = ['otp_type', 'is_used', 'created_at']
    search_fields = ['user__email', 'otp_code']
    readonly_fields = ['created_at']
    ordering = ['-created_at']


@admin.register(UserNotificationPreference)
class UserNotificationPreferenceAdmin(admin.ModelAdmin):
    """Admin for notification preferences."""
    list_display = ['user', 'portfolio_updates', 'transfer_notifications', 'email_notifications', 'sms_notifications']
    list_filter = ['portfolio_updates', 'transfer_notifications', 'email_notifications']
    search_fields = ['user__email']


@admin.register(UserDocument)
class UserDocumentAdmin(admin.ModelAdmin):
    """Admin for user documents."""
    list_display = ['title', 'user', 'document_type', 'status', 'get_file_size_mb', 'uploaded_at']
    list_filter = ['document_type', 'status', 'uploaded_at']
    search_fields = ['title', 'user__email']
    readonly_fields = ['uploaded_at']


@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    """Admin for user activities."""
    list_display = ['user', 'activity_type', 'description', 'created_at']
    list_filter = ['activity_type', 'created_at']
    search_fields = ['user__email', 'description']
    readonly_fields = ['created_at']


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    """Admin for user sessions."""
    list_display = ['user', 'device_name', 'location', 'is_current', 'last_activity']
    list_filter = ['is_current', 'created_at']
    search_fields = ['user__email', 'device_name', 'location']
    readonly_fields = ['created_at', 'last_activity']


@admin.register(InvestorProfile)
class InvestorProfileAdmin(admin.ModelAdmin):
    """Admin for investor profiles."""
    list_display = ['display_name', 'user', 'investor_category', 'location_country', 'is_public', 'is_accepting_connections']
    list_filter = ['investor_category', 'risk_profile', 'is_public', 'is_accepting_connections']
    search_fields = ['display_name', 'user__email', 'location_city', 'location_country']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(InvestorConnection)
class InvestorConnectionAdmin(admin.ModelAdmin):
    """Admin for investor connections."""
    list_display = ['from_investor', 'to_investor', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['from_investor__email', 'to_investor__email']
    readonly_fields = ['created_at', 'updated_at']


