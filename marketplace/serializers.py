"""
Serializers for the marketplace app.
Handles marketplace opportunities, documents, tags, and user interests.
"""

from rest_framework import serializers
from .models import MarketplaceOpportunity, OpportunityDocument, OpportunityTag, InvestmentInterest
from decimal import Decimal
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
    
    def get_file_url(self, obj):
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
    funding_progress_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
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
    funding_progress_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
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
                  'contact_phone', 'contact_email', 'location', 'run_rate_sales_min',
                  'run_rate_sales_max', 'investment_requirements', 'disclaimer',
                  'funding_progress_percentage', 'remaining_amount', 'is_featured',
                  'documents', 'tags', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class InvestmentInterestSerializer(serializers.ModelSerializer):
    """Serializer for investment interest."""
    interest_type_display = serializers.CharField(source='get_interest_type_display', read_only=True)
    opportunity_title = serializers.CharField(source='opportunity.title', read_only=True)
    
    class Meta:
        model = InvestmentInterest
        fields = ['id', 'opportunity', 'opportunity_title', 'interest_type', 
                  'interest_type_display', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def create(self, validated_data):
        """Create investment interest with user from context."""
        validated_data['user'] = self.context['request'].user
        
        # Check if already exists
        existing = InvestmentInterest.objects.filter(
            user=validated_data['user'],
            opportunity=validated_data['opportunity'],
            interest_type=validated_data['interest_type']
        ).first()
        
        if existing:
            return existing
        
        interest = InvestmentInterest.objects.create(**validated_data)
        logger.info(
            f"Investment interest created: {interest.user.email} {interest.interest_type} "
            f"in {interest.opportunity.title}"
        )
        return interest
