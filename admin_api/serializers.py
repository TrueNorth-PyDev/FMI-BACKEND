"""
Admin API Serializers — covers Users, Opportunities, Investments, Transfers.
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from accounts.models import (
    InvestorProfile, UserSession, UserActivity,
    UserNotificationPreference, InvestorConnection,
)
from investments.models import Investment, CapitalActivity, OwnershipTransfer, SecondaryMarketInterest
from marketplace.models import MarketplaceOpportunity, OpportunityDocument, InvestorInterest

User = get_user_model()


# ---------------------------------------------------------------------------
# User serializers
# ---------------------------------------------------------------------------

class AdminUserListSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    investment_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'full_name', 'first_name', 'last_name',
            'is_active', 'is_staff', 'is_email_verified', 'is_verified',
            'investor_type', 'member_since', 'created_at', 'last_login',
            'last_login_ip', 'failed_login_attempts', 'account_locked_until',
            'investment_count',
        ]

    def get_full_name(self, obj):
        return obj.get_full_name()

    def get_investment_count(self, obj):
        return obj.investments.count()


class AdminUserDetailSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    investment_count = serializers.SerializerMethodField()
    total_invested = serializers.SerializerMethodField()
    is_locked = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'full_name', 'first_name', 'last_name',
            'phone_number', 'country', 'address',
            'is_active', 'is_staff', 'is_email_verified', 'is_verified',
            'investor_type', 'risk_tolerance', 'investment_preferences',
            'member_since', 'created_at', 'updated_at',
            'last_login', 'last_login_ip',
            'failed_login_attempts', 'account_locked_until', 'is_locked',
            'investment_count', 'total_invested',
        ]

    def get_full_name(self, obj):
        return obj.get_full_name()

    def get_investment_count(self, obj):
        return obj.investments.count()

    def get_total_invested(self, obj):
        from django.db.models import Sum
        result = obj.investments.aggregate(total=Sum('total_invested'))
        return result['total'] or 0

    def get_is_locked(self, obj):
        return obj.is_account_locked()


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'phone_number', 'country', 'address',
            'is_active', 'is_staff', 'is_verified', 'investor_type', 'risk_tolerance',
        ]


class AdminUserSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSession
        fields = [
            'id', 'device_name', 'location', 'ip_address',
            'is_current', 'created_at', 'last_activity',
        ]


class AdminUserActivitySerializer(serializers.ModelSerializer):
    activity_type_display = serializers.CharField(source='get_activity_type_display', read_only=True)

    class Meta:
        model = UserActivity
        fields = [
            'id', 'activity_type', 'activity_type_display',
            'description', 'ip_address', 'created_at',
        ]


# ---------------------------------------------------------------------------
# Opportunity serializers
# ---------------------------------------------------------------------------

class AdminOpportunityListSerializer(serializers.ModelSerializer):
    funding_progress = serializers.DecimalField(
        source='funding_progress_percentage', max_digits=6, decimal_places=2, read_only=True
    )
    investor_count = serializers.IntegerField(source='investors_count', read_only=True)

    class Meta:
        model = MarketplaceOpportunity
        fields = [
            'id', 'title', 'sector', 'status', 'verification_type',
            'target_raise_amount', 'current_raised_amount', 'funding_progress',
            'min_investment', 'target_irr', 'is_featured', 'investor_count',
            'created_at', 'updated_at',
        ]


class AdminOpportunityDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = OpportunityDocument
        fields = ['id', 'title', 'document_type', 'file', 'uploaded_at']


class AdminOpportunityDetailSerializer(serializers.ModelSerializer):
    funding_progress = serializers.DecimalField(
        source='funding_progress_percentage', max_digits=6, decimal_places=2, read_only=True
    )
    remaining_amount = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    documents = AdminOpportunityDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = MarketplaceOpportunity
        fields = '__all__'
        extra_fields = ['funding_progress', 'remaining_amount', 'documents']


class AdminOpportunityWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketplaceOpportunity
        exclude = ['created_at', 'updated_at']


# ---------------------------------------------------------------------------
# Investment serializers
# ---------------------------------------------------------------------------

class AdminInvestmentListSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    investment_name = serializers.SerializerMethodField()
    unrealized_gain = serializers.DecimalField(max_digits=20, decimal_places=2, read_only=True)

    class Meta:
        model = Investment
        fields = [
            'id', 'user_email', 'investment_name', 'sector',
            'status', 'total_invested', 'current_value',
            'unrealized_gain', 'investment_date', 'created_at',
        ]

    def get_investment_name(self, obj):
        return obj.get_name()


class AdminCapitalActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = CapitalActivity
        fields = ['id', 'activity_type', 'amount', 'date', 'details', 'created_at']


class AdminInvestmentDetailSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    investment_name = serializers.SerializerMethodField()
    capital_activities = AdminCapitalActivitySerializer(many=True, read_only=True)
    unrealized_gain = serializers.DecimalField(max_digits=20, decimal_places=2, read_only=True)
    moic = serializers.DecimalField(max_digits=10, decimal_places=4, read_only=True)

    class Meta:
        model = Investment
        fields = '__all__'

    def get_investment_name(self, obj):
        return obj.get_name()


class AdminInvestmentUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Investment
        fields = [
            'status', 'total_invested', 'current_value',
            'fund_size', 'unfunded_commitment', 'manager',
            'expected_horizon_years', 'progress_percentage',
        ]


# ---------------------------------------------------------------------------
# Transfer serializers
# ---------------------------------------------------------------------------

class AdminTransferListSerializer(serializers.ModelSerializer):
    from_user_email = serializers.EmailField(source='from_user.email', read_only=True)
    to_user_email = serializers.SerializerMethodField()
    investment_name = serializers.SerializerMethodField()

    class Meta:
        model = OwnershipTransfer
        fields = [
            'id', 'from_user_email', 'to_user_email', 'to_email',
            'investment_name', 'transfer_type', 'transfer_amount',
            'transfer_fee', 'net_amount', 'percentage',
            'status', 'is_processed', 'created_at',
        ]

    def get_to_user_email(self, obj):
        return obj.to_user.email if obj.to_user else None

    def get_investment_name(self, obj):
        return obj.investment.get_name() if obj.investment else None


class AdminTransferDetailSerializer(serializers.ModelSerializer):
    from_user_email = serializers.EmailField(source='from_user.email', read_only=True)
    to_user_email = serializers.SerializerMethodField()
    investment_name = serializers.SerializerMethodField()

    class Meta:
        model = OwnershipTransfer
        fields = '__all__'

    def get_to_user_email(self, obj):
        return obj.to_user.email if obj.to_user else None

    def get_investment_name(self, obj):
        return obj.investment.get_name() if obj.investment else None


class AdminSecondaryInterestSerializer(serializers.ModelSerializer):
    buyer_email = serializers.EmailField(source='buyer.email', read_only=True)
    transfer_investment = serializers.SerializerMethodField()

    class Meta:
        model = SecondaryMarketInterest
        fields = '__all__'

    def get_transfer_investment(self, obj):
        if obj.transfer and obj.transfer.investment:
            return obj.transfer.investment.get_name()
        return None


# ---------------------------------------------------------------------------
# Analytics serializers (plain dicts returned by views, these are for docs)
# ---------------------------------------------------------------------------

class AdminInvestorInterestSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    opportunity_title = serializers.CharField(source='opportunity.title', read_only=True)

    class Meta:
        model = InvestorInterest
        fields = [
            'id', 'user_email', 'opportunity_title',
            'amount', 'investment_date', 'status', 'created_at',
        ]
