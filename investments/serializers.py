"""
Serializers for the investments app.
Handles investment CRUD, capital activities, and portfolio analytics.
"""

from rest_framework import serializers
from .models import Investment, CapitalActivity, PerformanceSnapshot, OwnershipTransfer, TransferDocument
from decimal import Decimal
import logging

logger = logging.getLogger('investments')


class CapitalActivitySerializer(serializers.ModelSerializer):
    """Serializer for capital activities."""
    activity_type_display = serializers.CharField(source='get_activity_type_display', read_only=True)
    
    class Meta:
        model = CapitalActivity
        fields = ['id', 'investment', 'activity_type', 'activity_type_display', 
                  'amount', 'date', 'details', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def validate_amount(self, value):
        """Validate amount based on activity type."""
        activity_type = self.initial_data.get('activity_type')
        
        if activity_type in ['INITIAL_INVESTMENT', 'CAPITAL_CALL']:
            # These should be negative (outflows)
            if value > 0:
                return -abs(value)
        elif activity_type in ['DISTRIBUTION', 'PARTIAL_EXIT']:
            # These should be positive (inflows)
            if value < 0:
                return abs(value)
        
        return value


class PerformanceSnapshotSerializer(serializers.ModelSerializer):
    """Serializer for performance snapshots."""
    
    class Meta:
        model = PerformanceSnapshot
        fields = ['id', 'investment', 'date', 'value', 'created_at']
        read_only_fields = ['id', 'created_at']


class InvestmentListSerializer(serializers.ModelSerializer):
    """Serializer for investment list view."""
    sector_display = serializers.CharField(source='get_sector_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    unrealized_gain = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    unrealized_gain_percentage = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    moic = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = Investment
        fields = ['id', 'name', 'status', 'status_display', 'sector', 'sector_display',
                  'current_value', 'total_invested', 'unrealized_gain', 
                  'unrealized_gain_percentage', 'investment_date', 'moic']


class InvestmentDetailSerializer(serializers.ModelSerializer):
    """Serializer for investment detail view."""
    sector_display = serializers.CharField(source='get_sector_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    unrealized_gain = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    unrealized_gain_percentage = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    moic = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    expected_end_date = serializers.DateField(read_only=True)
    irr = serializers.SerializerMethodField()
    capital_activities = CapitalActivitySerializer(many=True, read_only=True)
    
    class Meta:
        model = Investment
        fields = ['id', 'name', 'status', 'status_display', 'sector', 'sector_display',
                  'total_invested', 'current_value', 'fund_size', 'unfunded_commitment',
                  'manager', 'investment_date', 'expected_horizon_years', 'fund_vintage',
                  'progress_percentage', 'unrealized_gain', 'unrealized_gain_percentage',
                  'moic', 'irr', 'expected_end_date', 'capital_activities', 
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_irr(self, obj):
        """Calculate and return IRR."""
        try:
            irr = obj.calculate_irr()
            return float(irr) if irr else 0.0
        except:
            return 0.0


class InvestmentCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating investments."""
    
    class Meta:
        model = Investment
        fields = ['name', 'status', 'sector', 'total_invested', 'current_value',
                  'fund_size', 'unfunded_commitment', 'manager', 'investment_date',
                  'expected_horizon_years', 'fund_vintage', 'progress_percentage']
    
    def validate(self, attrs):
        """Validate investment data."""
        if attrs.get('current_value') and attrs.get('total_invested'):
            if attrs['current_value'] < 0:
                raise serializers.ValidationError({"current_value": "Current value cannot be negative."})
            if attrs['total_invested'] <= 0:
                raise serializers.ValidationError({"total_invested": "Total invested must be greater than zero."})
        
        if attrs.get('unfunded_commitment', Decimal('0.00')) < 0:
            raise serializers.ValidationError({"unfunded_commitment": "Unfunded commitment cannot be negative."})
        
        if attrs.get('progress_percentage'):
            if not (0 <= attrs['progress_percentage'] <= 100):
                raise serializers.ValidationError({"progress_percentage": "Progress must be between 0 and 100."})
        
        return attrs
    
    def create(self, validated_data):
        """Create investment with user from context."""
        validated_data['user'] = self.context['request'].user
        investment = Investment.objects.create(**validated_data)
        logger.info(f"Investment created: {investment.name} by {investment.user.email}")
        return investment


class PortfolioSummarySerializer(serializers.Serializer):
    """Serializer for portfolio summary data."""
    total_value = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_invested = serializers.DecimalField(max_digits=15, decimal_places=2)
    unrealized_gains = serializers.DecimalField(max_digits=15, decimal_places=2)
    unrealized_gains_percentage = serializers.DecimalField(max_digits=10, decimal_places=2)
    average_irr = serializers.DecimalField(max_digits=10, decimal_places=2)
    num_investments = serializers.IntegerField()


class SectorAllocationSerializer(serializers.Serializer):
    """Serializer for sector allocation data."""
    sector = serializers.CharField()
    sector_display = serializers.CharField()
    amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    percentage = serializers.DecimalField(max_digits=5, decimal_places=2)


class RiskMetricsSerializer(serializers.Serializer):
    """Serializer for risk metrics data."""
    portfolio_beta = serializers.DecimalField(max_digits=5, decimal_places=2)
    sharpe_ratio = serializers.DecimalField(max_digits=5, decimal_places=2)
    max_drawdown = serializers.DecimalField(max_digits=5, decimal_places=2)
    value_at_risk = serializers.DecimalField(max_digits=15, decimal_places=2)


class PerformanceDataSerializer(serializers.Serializer):
    """Serializer for performance time series data."""
    date = serializers.DateField()
    value = serializers.DecimalField(max_digits=15, decimal_places=2)


class ReturnsAnalysisSerializer(serializers.Serializer):
    """Serializer for returns analysis data."""
    realized_gains = serializers.DecimalField(max_digits=15, decimal_places=2)
    unrealized_gains = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_return = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_invested = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_current_value = serializers.DecimalField(max_digits=15, decimal_places=2)


class ReturnAttributionSerializer(serializers.Serializer):
    """Serializer for return attribution by sector."""
    sector = serializers.CharField()
    sector_display = serializers.CharField()
    invested = serializers.DecimalField(max_digits=15, decimal_places=2)
    current_value = serializers.DecimalField(max_digits=15, decimal_places=2)
    gain = serializers.DecimalField(max_digits=15, decimal_places=2)
    gain_percentage = serializers.DecimalField(max_digits=10, decimal_places=2)


class DistributionHistorySerializer(serializers.Serializer):
    """Serializer for distribution history."""
    id = serializers.IntegerField()
    investment_id = serializers.IntegerField()
    investment_name = serializers.CharField()
    amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    date = serializers.DateField()
    details = serializers.CharField()
    activity_type = serializers.CharField()
    activity_type_display = serializers.CharField()


class TransferDocumentSerializer(serializers.ModelSerializer):
    """Serializer for transfer documents."""
    document_type_display = serializers.CharField(source='get_document_type_display', read_only=True)
    file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = TransferDocument
        fields = ['id', 'document_type', 'document_type_display', 'file', 'file_url', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at']
    
    def get_file_url(self, obj):
        """Get full URL for the file."""
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None


class OwnershipTransferListSerializer(serializers.ModelSerializer):
    """Serializer for ownership transfer list view."""
    investment_name = serializers.CharField(source='investment.name', read_only=True)
    from_user_email = serializers.CharField(source='from_user.email', read_only=True)
    to_user_email = serializers.CharField(source='to_user.email', read_only=True, allow_null=True)
    recipient = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    transfer_type_display = serializers.CharField(source='get_transfer_type_display', read_only=True)
    
    class Meta:
        model = OwnershipTransfer
        fields = ['id', 'investment', 'investment_name', 'from_user_email', 'to_user_email',
                  'recipient', 'to_name', 'transfer_type', 'transfer_type_display', 'percentage',
                  'transfer_amount', 'transfer_fee', 'net_amount', 'status', 'status_display',
                  'initiated_date', 'estimated_completion_date']
    
    def get_recipient(self, obj):
        """Get recipient display name."""
        if obj.to_user:
            return obj.to_user.email
        return obj.to_email or obj.to_name


class OwnershipTransferDetailSerializer(serializers.ModelSerializer):
    """Serializer for ownership transfer detail view."""
    investment_name = serializers.CharField(source='investment.name', read_only=True)
    from_user_email = serializers.CharField(source='from_user.email', read_only=True)
    to_user_email = serializers.CharField(source='to_user.email', read_only=True, allow_null=True)
    recipient = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    transfer_type_display = serializers.CharField(source='get_transfer_type_display', read_only=True)
    documents = TransferDocumentSerializer(many=True, read_only=True)
    
    class Meta:
        model = OwnershipTransfer
        fields = ['id', 'investment', 'investment_name', 'from_user', 'from_user_email',
                  'to_user', 'to_user_email', 'to_email', 'to_name', 'recipient',
                  'transfer_type', 'transfer_type_display', 'percentage', 'transfer_amount',
                  'transfer_fee', 'net_amount', 'reason', 'status', 'status_display',
                  'initiated_date', 'completion_date', 'estimated_completion_date',
                  'documents', 'created_at', 'updated_at']
        read_only_fields = ['id', 'from_user', 'transfer_fee', 'net_amount', 'initiated_date',
                           'created_at', 'updated_at']
    
    def get_recipient(self, obj):
        """Get recipient display name."""
        if obj.to_user:
            return obj.to_user.email
        return obj.to_email or obj.to_name


class OwnershipTransferCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating ownership transfers."""
    
    class Meta:
        model = OwnershipTransfer
        fields = ['investment', 'to_user', 'to_email', 'to_name', 'transfer_type',
                  'percentage', 'transfer_amount', 'reason', 'status']
    
    def validate(self, attrs):
        """Validate transfer data."""
        request = self.context.get('request')
        investment = attrs.get('investment')
        
        # Verify user owns the investment
        if investment.user != request.user:
            raise serializers.ValidationError({"investment": "You do not own this investment."})
        
        # Verify investment is active
        if investment.status not in ['ACTIVE', 'UNDERPERFORMING']:
            raise serializers.ValidationError({"investment": "Cannot transfer inactive investments."})
        
        # Validate recipient
        if not attrs.get('to_user') and not attrs.get('to_email'):
            raise serializers.ValidationError("Either to_user or to_email must be provided.")
        
        # Cannot transfer to self
        if attrs.get('to_user') == request.user:
            raise serializers.ValidationError({"to_user": "Cannot transfer to yourself."})
        
        # Validate percentage for partial transfers
        if attrs.get('transfer_type') == 'PARTIAL':
            if not attrs.get('percentage'):
                raise serializers.ValidationError({"percentage": "Percentage is required for partial transfers."})
            if not (0 < attrs['percentage'] <= 100):
                raise serializers.ValidationError({"percentage": "Percentage must be between 0 and 100."})
        
        # Validate transfer amount
        if attrs.get('transfer_amount') <= 0:
            raise serializers.ValidationError({"transfer_amount": "Transfer amount must be greater than zero."})
        
        # Check for duplicate pending transfers
        existing_transfer = OwnershipTransfer.objects.filter(
            investment=investment,
            from_user=request.user,
            status__in=['DRAFT', 'PENDING', 'APPROVED']
        ).exists()
        
        if existing_transfer:
            raise serializers.ValidationError(
                "You already have a pending transfer for this investment. "
                "Please complete or cancel it before creating a new one."
            )
        
        return attrs
    
    def create(self, validated_data):
        """Create transfer with from_user from context."""
        validated_data['from_user'] = self.context['request'].user
        transfer = OwnershipTransfer.objects.create(**validated_data)
        logger.info(
            f"Ownership transfer created: {transfer.investment.name} by {transfer.from_user.email}, "
            f"Status: {transfer.status}"
        )
        return transfer


# Analytics Serializers

class QuarterlyPerformanceSerializer(serializers.Serializer):
    """Serializer for quarterly performance data."""
    quarter = serializers.CharField()
    portfolio_return = serializers.FloatField()
    benchmark_return = serializers.FloatField()


class AssetAllocationSerializer(serializers.Serializer):
    """Serializer for asset allocation data."""
    asset_class = serializers.CharField()
    current_value = serializers.FloatField()
    current_percentage = serializers.FloatField()
    target_percentage = serializers.IntegerField()
    difference = serializers.FloatField()


class RebalancingRecommendationSerializer(serializers.Serializer):
    """Serializer for rebalancing recommendations."""
    asset_class = serializers.CharField()
    status = serializers.CharField()
    action = serializers.CharField()
    current_percentage = serializers.FloatField()
    target_percentage = serializers.IntegerField()


class ConcentrationRiskSerializer(serializers.Serializer):
    """Serializer for concentration risk metrics."""
    top_3_concentration = serializers.FloatField()
    top_5_concentration = serializers.FloatField()
    risk_level = serializers.CharField()


class StressTestScenarioSerializer(serializers.Serializer):
    """Serializer for stress test scenarios."""
    scenario = serializers.CharField()
    impact_percentage = serializers.FloatField()
    expected_loss = serializers.FloatField()
    recovery_months = serializers.IntegerField()


class PortfolioVolatilitySerializer(serializers.Serializer):
    """Serializer for portfolio volatility metrics."""
    volatility = serializers.FloatField()
    risk_level = serializers.CharField()



