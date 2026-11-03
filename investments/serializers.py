"""
Serializers for the investments app.
Handles investment CRUD, capital activities, and portfolio analytics.
"""

from typing import Optional

from rest_framework import serializers
from .models import Investment, CapitalActivity, PerformanceSnapshot, OwnershipTransfer, TransferDocument, SecondaryMarketInterest
from decimal import Decimal
import logging

logger = logging.getLogger('investments')


class CapitalActivitySerializer(serializers.ModelSerializer):
    """Read-only serializer for capital activities (recorded by staff or by the system)."""
    activity_type_display = serializers.CharField(source='get_activity_type_display', read_only=True)
    
    class Meta:
        model = CapitalActivity
        fields = ['id', 'investment', 'activity_type', 'activity_type_display', 
                  'amount', 'date', 'details', 'created_at']
        read_only_fields = fields
        depth = 1


class PerformanceSnapshotSerializer(serializers.ModelSerializer):
    """Serializer for performance snapshots."""
    
    class Meta:
        model = PerformanceSnapshot
        fields = ['id', 'investment', 'date', 'value', 'created_at']
        read_only_fields = ['id', 'created_at']
        depth = 1


class InvestmentListSerializer(serializers.ModelSerializer):
    """Serializer for investment list view."""
    name = serializers.SerializerMethodField()
    sector = serializers.SerializerMethodField()
    sector_display = serializers.CharField(source='get_sector_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    unrealized_gain = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    unrealized_gain_percentage = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    moic = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    opportunity_id = serializers.IntegerField(source='opportunity.id', read_only=True, allow_null=True)
    
    class Meta:
        model = Investment
        fields = ['id', 'name', 'status', 'status_display', 'sector', 'sector_display',
                  'current_value', 'total_invested', 'unrealized_gain', 
                  'unrealized_gain_percentage', 'investment_date', 'moic', 'opportunity_id']
    
    def get_name(self, obj) -> str:
        return obj.get_name()
    
    def get_sector(self, obj) -> str:
        return obj.get_sector()


class InvestmentDetailSerializer(serializers.ModelSerializer):
    """Serializer for investment detail view."""
    name = serializers.SerializerMethodField()
    sector = serializers.SerializerMethodField()
    sector_display = serializers.CharField(source='get_sector_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    unrealized_gain = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    unrealized_gain_percentage = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    moic = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    expected_end_date = serializers.DateField(read_only=True)
    calculated_irr = serializers.SerializerMethodField()
    target_irr = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    capital_activities = CapitalActivitySerializer(many=True, read_only=True)
    opportunity_id = serializers.IntegerField(source='opportunity.id', read_only=True, allow_null=True)
    
    class Meta:
        model = Investment
        fields = ['id', 'name', 'status', 'status_display', 'sector', 'sector_display',
                  'total_invested', 'current_value', 'fund_size', 'unfunded_commitment',
                  'manager', 'investment_date', 'expected_horizon_years', 'fund_vintage',
                  'progress_percentage', 'unrealized_gain', 'unrealized_gain_percentage',
                  'moic', 'calculated_irr', 'target_irr', 'expected_end_date', 'capital_activities', 
                  'opportunity_id', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_name(self, obj) -> str:
        return obj.get_name()
    
    def get_sector(self, obj) -> str:
        return obj.get_sector()
    
    def get_calculated_irr(self, obj) -> float:
        """Calculate and return IRR from capital activities."""
        irr = obj.calculate_irr()  # returns 0 on any calculation failure
        return float(irr) if irr else 0.0


class TransferDocumentSerializer(serializers.ModelSerializer):
    """Serializer for transfer documents."""
    document_type_display = serializers.CharField(source='get_document_type_display', read_only=True)
    file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = TransferDocument
        fields = ['id', 'document_type', 'document_type_display', 'file', 'file_url', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at']
    
    def get_file_url(self, obj) -> Optional[str]:
        """Transfer documents are private: link to the authenticated download endpoint."""
        request = self.context.get('request')
        if obj.file and request:
            from django.urls import reverse
            url = reverse('investments:transfer-download-document', args=[obj.transfer_id, obj.pk])
            return request.build_absolute_uri(url)
        return None


class OwnershipTransferListSerializer(serializers.ModelSerializer):
    """Serializer for ownership transfer list view."""
    investment_name = serializers.CharField(source='investment.get_name', read_only=True)
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
    
    def get_recipient(self, obj) -> str:
        """Get recipient display name."""
        if obj.to_user:
            return obj.to_user.email
        return obj.to_email or obj.to_name


class OwnershipTransferDetailSerializer(serializers.ModelSerializer):
    """Serializer for ownership transfer detail view."""
    investment_name = serializers.CharField(source='investment.get_name', read_only=True)
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
    
    def get_recipient(self, obj) -> str:
        """Get recipient display name."""
        if obj.to_user:
            return obj.to_user.email
        return obj.to_email or obj.to_name


class OwnershipTransferCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and editing ownership transfers.

    Owners may only create a transfer as DRAFT or PENDING (submitted); approval
    and completion are staff actions in the admin API.
    """
    status = serializers.ChoiceField(choices=['DRAFT', 'PENDING'], required=False, default='DRAFT')
    
    class Meta:
        model = OwnershipTransfer
        fields = ['investment', 'to_user', 'to_email', 'to_name', 'transfer_type',
                  'percentage', 'transfer_amount', 'reason', 'status']
    
    def validate(self, attrs):
        """Validate transfer data, falling back to stored values on partial updates."""
        request = self.context.get('request')
        instance = self.instance
        
        def value(field):
            if field in attrs:
                return attrs[field]
            return getattr(instance, field, None) if instance else None
        
        investment = value('investment')
        transfer_type = value('transfer_type')
        transfer_amount = value('transfer_amount')
        to_user = value('to_user')
        
        # Verify user owns the investment
        if investment.user_id != request.user.id:
            raise serializers.ValidationError({"investment": "You do not own this investment."})
        
        # Verify investment is active
        if investment.status not in ['ACTIVE', 'UNDERPERFORMING']:
            raise serializers.ValidationError({"investment": "Cannot transfer inactive investments."})
        
        # Cannot transfer to self
        if to_user is not None and to_user.pk == request.user.pk:
            raise serializers.ValidationError({"to_user": "Cannot transfer to yourself."})
        
        # Validate percentage for partial transfers
        if transfer_type == 'PARTIAL':
            percentage = value('percentage')
            if not percentage:
                raise serializers.ValidationError({"percentage": "Percentage is required for partial transfers."})
            if not (0 < percentage <= 100):
                raise serializers.ValidationError({"percentage": "Percentage must be between 0 and 100."})
        elif transfer_type == 'FULL':
            # A full transfer always moves the whole position
            attrs['percentage'] = Decimal('100.00')
        
        # Validate transfer amount
        if transfer_amount is None or transfer_amount <= 0:
            raise serializers.ValidationError({"transfer_amount": "Transfer amount must be greater than zero."})
        if transfer_amount > investment.current_value:
            raise serializers.ValidationError({
                "transfer_amount": f"Transfer amount exceeds the investment's current value (${investment.current_value})."
            })
        
        # Check for duplicate open transfers
        open_transfers = OwnershipTransfer.objects.filter(
            investment=investment,
            from_user=request.user,
            status__in=['DRAFT', 'PENDING', 'APPROVED']
        )
        if instance:
            open_transfers = open_transfers.exclude(pk=instance.pk)
        
        if open_transfers.exists():
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
            f"Ownership transfer created: {transfer.investment.get_name()} by {transfer.from_user.email}, "
            f"Status: {transfer.status}"
        )
        return transfer


class SecondaryMarketListingSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for the secondary market.
    Surfaces PENDING OwnershipTransfers as investment listings visible to all users.
    """
    # Investment / opportunity detail
    investment_name = serializers.SerializerMethodField()
    investment_sector = serializers.SerializerMethodField()
    investment_sector_display = serializers.SerializerMethodField()
    opportunity_id = serializers.IntegerField(source='investment.opportunity.id', read_only=True, allow_null=True)
    opportunity_title = serializers.CharField(source='investment.opportunity.title', read_only=True, allow_null=True)
    opportunity_target_irr = serializers.DecimalField(
        source='investment.opportunity.target_irr', max_digits=5, decimal_places=2, read_only=True, allow_null=True
    )
    opportunity_min_investment = serializers.DecimalField(
        source='investment.opportunity.min_investment', max_digits=15, decimal_places=2, read_only=True, allow_null=True
    )
    opportunity_investment_term_years = serializers.IntegerField(
        source='investment.opportunity.investment_term_years', read_only=True, allow_null=True
    )
    opportunity_risk_level = serializers.CharField(
        source='investment.opportunity.risk_level', read_only=True, allow_null=True
    )
    opportunity_payout_frequency = serializers.CharField(
        source='investment.opportunity.payout_frequency', read_only=True, allow_null=True
    )

    # Transfer terms
    transfer_type_display = serializers.CharField(source='get_transfer_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    # Seller info — display name only, no PII email
    seller_display_name = serializers.SerializerMethodField()

    # Convenience flag
    is_partial = serializers.SerializerMethodField()

    # Listed timestamp alias
    listed_at = serializers.DateTimeField(source='initiated_date', read_only=True)

    class Meta:
        model = OwnershipTransfer
        fields = [
            'id',
            # Investment / opportunity
            'investment', 'investment_name', 'investment_sector', 'investment_sector_display',
            'opportunity_id', 'opportunity_title', 'opportunity_target_irr',
            'opportunity_min_investment', 'opportunity_investment_term_years',
            'opportunity_risk_level', 'opportunity_payout_frequency',
            # Transfer terms
            'transfer_type', 'transfer_type_display', 'is_partial',
            'percentage', 'transfer_amount', 'transfer_fee', 'net_amount',
            'reason',
            # Seller
            'seller_display_name',
            # Dates
            'status', 'status_display', 'listed_at', 'estimated_completion_date',
        ]
        read_only_fields = fields

    def get_investment_name(self, obj) -> str:
        return obj.investment.get_name()

    def get_investment_sector(self, obj) -> str:
        return obj.investment.get_sector()

    def get_investment_sector_display(self, obj) -> str:
        return obj.investment.get_sector_display()

    def get_seller_display_name(self, obj) -> str:
        """Return seller's first name, or a masked email (e.g. j***@example.com)."""
        user = obj.from_user
        if user.first_name:
            return user.first_name
        email = user.email
        local, domain = email.split('@', 1)
        masked = local[0] + '***'
        return f"{masked}@{domain}"

    def get_is_partial(self, obj) -> bool:
        return obj.transfer_type == 'PARTIAL'


# Analytics Serializers

class QuarterlyPerformanceSerializer(serializers.Serializer):
    """Serializer for quarterly performance data."""
    quarter = serializers.CharField()
    portfolio_return = serializers.FloatField()
    benchmark_return = serializers.FloatField()


class SecondaryMarketInterestSerializer(serializers.ModelSerializer):
    """Read serializer — used for listing / retrieving interests."""
    buyer_email    = serializers.EmailField(source='buyer.email', read_only=True)
    transfer_id    = serializers.IntegerField(source='transfer.id', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model  = SecondaryMarketInterest
        fields = [
            'id', 'transfer_id', 'buyer_email', 'amount',
            'interest_date', 'status', 'status_display',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'buyer_email', 'transfer_id', 'status_display',
            'created_at', 'updated_at',
        ]


class SecondaryMarketInterestCreateSerializer(serializers.ModelSerializer):
    """
    Write serializer for a buyer's interest. Buyers set the listing, amount and
    date; the status is managed by staff (CONVERTED executes the purchase) or by
    the buyer's cancel action.
    """

    class Meta:
        model  = SecondaryMarketInterest
        fields = ['id', 'transfer', 'amount', 'interest_date', 'status']
        read_only_fields = ['id', 'status']

    def validate(self, data):
        request  = self.context['request']
        instance = self.instance
        if instance is not None:
            if instance.status != 'PENDING':
                raise serializers.ValidationError(
                    f"This interest is {instance.status.lower()} and can no longer be changed."
                )
            if 'transfer' in data and data['transfer'].pk != instance.transfer_id:
                raise serializers.ValidationError({"transfer": "The listing of an interest cannot be changed."})
        transfer = data.get('transfer') or getattr(instance, 'transfer', None)
        amount   = data.get('amount')   or getattr(instance, 'amount', None)

        if transfer:
            # Buyer cannot be the seller
            if transfer.from_user_id == request.user.id:
                raise serializers.ValidationError(
                    "You cannot express interest in your own listing."
                )
            # Transfer must be an open, public listing
            if transfer.status != 'PENDING' or transfer.to_user_id is not None:
                raise serializers.ValidationError(
                    "You can only express interest in PENDING listings."
                )
            # Amount must not exceed what the seller is offering
            if amount and amount > transfer.transfer_amount:
                raise serializers.ValidationError(
                    f"Amount ({amount}) exceeds the listing amount ({transfer.transfer_amount})."
                )
            if instance is None and SecondaryMarketInterest.objects.filter(
                transfer=transfer, buyer=request.user
            ).exists():
                raise serializers.ValidationError(
                    "You already have a registered interest for this listing."
                )
        return data

    def create(self, validated_data):
        validated_data['buyer'] = self.context['request'].user
        return super().create(validated_data)
