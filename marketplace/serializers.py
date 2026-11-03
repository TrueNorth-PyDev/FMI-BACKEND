"""
Serializers for the marketplace app.
Handles marketplace opportunities, documents, tags, and user interests.
"""

from typing import Optional

from rest_framework import serializers
from .models import MarketplaceOpportunity, OpportunityDocument, OpportunityTag, InvestorInterest
import logging

logger = logging.getLogger('marketplace')


class OpportunityDocumentSerializer(serializers.ModelSerializer):
    """Serializer for opportunity documents."""
    document_type_display = serializers.CharField(source='get_document_type_display', read_only=True)
    file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = OpportunityDocument
        fields = ['id', 'title', 'file', 'file_url', 'document_type', 'document_type_display', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at']
    
    def get_file_url(self, obj) -> Optional[str]:
        """Get full URL for the file."""
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None


class OpportunityTagSerializer(serializers.ModelSerializer):
    """Serializer for opportunity tags."""
    tag_type_display = serializers.CharField(source='get_tag_type_display', read_only=True)
    
    class Meta:
        model = OpportunityTag
        fields = ['id', 'tag_name', 'tag_type', 'tag_type_display']
        read_only_fields = ['id']


class MarketplaceOpportunityListSerializer(serializers.ModelSerializer):
    """Serializer for marketplace opportunity list view."""
    sector_display = serializers.CharField(source='get_sector_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    investment_type_display = serializers.CharField(source='get_investment_type_display', read_only=True)
    funding_progress_percentage = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    remaining_amount = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    tags = OpportunityTagSerializer(many=True, read_only=True)
    
    class Meta:
        model = MarketplaceOpportunity
        fields = ['id', 'title', 'description', 'sector', 'sector_display', 'status', 'status_display',
                  'min_investment', 'target_raise_amount', 'current_raised_amount', 'target_irr',
                  'investment_term_years', 'investment_type', 'investment_type_display',
                  'rating', 'investors_count', 'funding_progress_percentage', 'remaining_amount',
                  'is_featured', 'tags']


class MarketplaceOpportunityDetailSerializer(serializers.ModelSerializer):
    """Serializer for marketplace opportunity detail view."""
    sector_display = serializers.CharField(source='get_sector_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    investment_type_display = serializers.CharField(source='get_investment_type_display', read_only=True)
    risk_level_display = serializers.CharField(source='get_risk_level_display', read_only=True)
    payout_frequency_display = serializers.CharField(source='get_payout_frequency_display', read_only=True)
    verification_type_display = serializers.CharField(source='get_verification_type_display', read_only=True)
    funding_progress_percentage = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    remaining_amount = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    documents = OpportunityDocumentSerializer(many=True, read_only=True)
    tags = OpportunityTagSerializer(many=True, read_only=True)
    
    class Meta:
        model = MarketplaceOpportunity
        fields = ['id', 'title', 'description', 'detailed_description', 'sector', 'sector_display',
                  'status', 'status_display', 'min_investment', 'target_raise_amount', 
                  'current_raised_amount', 'target_irr', 'investment_term_years', 'investment_type',
                  'investment_type_display', 'risk_level', 'risk_level_display', 'payout_frequency',
                  'payout_frequency_display', 'currency', 'rating', 'investors_count', 
                  'platform_rating', 'verification_type', 'verification_type_display',
                  'contact_phone', 'contact_email', 'location', 
                  'monthly_revenue', 'operating_expenses', 'net_cash_flow', 'cash_runway',
                  'total_staff_count', 'staff_departments', 'leadership_experience_years',
                  'current_capacity', 'utilization_rate_pct', 'growth_capacity',
                  'investment_requirements', 'disclaimer',
                  'funding_progress_percentage', 'remaining_amount', 'is_featured',
                  'documents', 'tags', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class InvestorInterestSerializer(serializers.ModelSerializer):
    """Serializer for investor interest expression."""
    user_email = serializers.EmailField(source='user.email', read_only=True)
    opportunity_title = serializers.CharField(source='opportunity.title', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = InvestorInterest
        fields = [
            'id', 'opportunity', 'opportunity_title', 'user_email',
            'amount', 'investment_date', 'status', 'status_display',
            'created_at', 'updated_at'
        ]
        # Investors can create, edit and cancel pledges; converting a pledge into an
        # investment is a staff action (/api/admin/investor-interests/{id}/convert/).
        read_only_fields = ['id', 'status', 'created_at', 'updated_at']

    OPEN_STATUSES = ('NEW', 'ACTIVE', 'CLOSING_SOON')

    def validate_amount(self, value):
        """Ensure investment amount is positive."""
        if value <= 0:
            raise serializers.ValidationError("Investment amount must be greater than zero.")
        return value

    def validate(self, attrs):
        instance = self.instance
        if instance is not None:
            if instance.status != 'PENDING':
                raise serializers.ValidationError(
                    f"This pledge is {instance.status.lower()} and can no longer be changed."
                )
            if 'opportunity' in attrs and attrs['opportunity'].pk != instance.opportunity_id:
                raise serializers.ValidationError({"opportunity": "The opportunity of a pledge cannot be changed."})

        opportunity = attrs.get('opportunity') or getattr(instance, 'opportunity', None)
        amount = attrs.get('amount')
        if opportunity is not None:
            if instance is None and opportunity.status not in self.OPEN_STATUSES:
                raise serializers.ValidationError({"opportunity": "This opportunity is not open for investment."})
            if amount is not None:
                if amount < opportunity.min_investment:
                    raise serializers.ValidationError(
                        {"amount": f"Minimum investment is {opportunity.min_investment}."}
                    )
                if amount > opportunity.remaining_amount:
                    raise serializers.ValidationError(
                        {"amount": f"Amount exceeds the remaining capacity ({opportunity.remaining_amount})."}
                    )
        return attrs

    def create(self, validated_data):
        """Create investor interest with user from context."""
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)
