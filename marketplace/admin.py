from django.contrib import admin
from .models import MarketplaceOpportunity, OpportunityDocument, OpportunityTag, InvestmentInterest


class OpportunityDocumentInline(admin.TabularInline):
    """Inline admin for opportunity documents."""
    model = OpportunityDocument
    extra = 1


class OpportunityTagInline(admin.TabularInline):
    """Inline admin for opportunity tags."""
    model = OpportunityTag
    extra = 1


@admin.register(MarketplaceOpportunity)
class MarketplaceOpportunityAdmin(admin.ModelAdmin):
    """Admin interface for MarketplaceOpportunity model."""
    list_display = ['title', 'sector', 'status', 'min_investment', 'target_raise_amount', 
                    'current_raised_amount', 'funding_progress_percentage', 'rating', 'is_featured']
    list_filter = ['status', 'sector', 'investment_type', 'risk_level', 'is_featured']
    search_fields = ['title', 'description', 'location']
    readonly_fields = ['created_at', 'updated_at', 'funding_progress_percentage', 'remaining_amount']
    inlines = [OpportunityDocumentInline, OpportunityTagInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'detailed_description', 'sector', 'status', 'is_featured')
        }),
        ('Financial Details', {
            'fields': ('min_investment', 'target_raise_amount', 'current_raised_amount', 
                      'target_irr', 'currency')
        }),
        ('Investment Terms', {
            'fields': ('investment_term_years', 'investment_type', 'risk_level', 'payout_frequency')
        }),
        ('Metrics & Rating', {
            'fields': ('rating', 'investors_count', 'platform_rating', 'verification_type')
        }),
        ('Contact Information', {
            'fields': ('contact_phone', 'contact_email', 'location')
        }),
        ('Additional Details', {
            'fields': ('run_rate_sales_min', 'run_rate_sales_max', 'investment_requirements', 'disclaimer'),
            'classes': ('collapse',)
        }),
        ('Calculated Fields', {
            'fields': ('funding_progress_percentage', 'remaining_amount'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def funding_progress_percentage(self, obj):
        return f"{obj.funding_progress_percentage:.2f}%"
    funding_progress_percentage.short_description = 'Progress %'


@admin.register(OpportunityDocument)
class OpportunityDocumentAdmin(admin.ModelAdmin):
    """Admin interface for OpportunityDocument model."""
    list_display = ['title', 'opportunity', 'document_type', 'uploaded_at']
    list_filter = ['document_type', 'uploaded_at']
    search_fields = ['title', 'opportunity__title']
    readonly_fields = ['uploaded_at']


@admin.register(OpportunityTag)
class OpportunityTagAdmin(admin.ModelAdmin):
    """Admin interface for OpportunityTag model."""
    list_display = ['tag_name', 'tag_type', 'opportunity']
    list_filter = ['tag_type']
    search_fields = ['tag_name', 'opportunity__title']


@admin.register(InvestmentInterest)
class InvestmentInterestAdmin(admin.ModelAdmin):
    """Admin interface for InvestmentInterest model."""
    list_display = ['user', 'opportunity', 'interest_type', 'created_at']
    list_filter = ['interest_type', 'created_at']
    search_fields = ['user__email', 'opportunity__title']
    readonly_fields = ['created_at']
