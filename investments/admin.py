from django.contrib import admin
from .models import Investment, CapitalActivity, PerformanceSnapshot, OwnershipTransfer, TransferDocument


@admin.register(Investment)
class InvestmentAdmin(admin.ModelAdmin):
    """Admin interface for Investment model."""
    list_display = ['name', 'user', 'status', 'sector', 'current_value', 'total_invested', 
                    'unrealized_gain_percentage', 'investment_date']
    list_filter = ['status', 'sector', 'investment_date']
    search_fields = ['name', 'user__email', 'manager']
    readonly_fields = ['created_at', 'updated_at', 'unrealized_gain', 'unrealized_gain_percentage', 'moic']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'name', 'status', 'sector')
        }),
        ('Financial Details', {
            'fields': ('total_invested', 'current_value', 'fund_size', 'unfunded_commitment')
        }),
        ('Fund Information', {
            'fields': ('manager', 'investment_date', 'expected_horizon_years', 'fund_vintage', 'progress_percentage')
        }),
        ('Calculated Metrics', {
            'fields': ('unrealized_gain', 'unrealized_gain_percentage', 'moic'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def unrealized_gain_percentage(self, obj):
        return f"{obj.unrealized_gain_percentage:.2f}%"
    unrealized_gain_percentage.short_description = 'Gain %'


@admin.register(CapitalActivity)
class CapitalActivityAdmin(admin.ModelAdmin):
    """Admin interface for CapitalActivity model."""
    list_display = ['investment', 'activity_type', 'amount', 'date', 'created_at']
    list_filter = ['activity_type', 'date']
    search_fields = ['investment__name', 'details']
    readonly_fields = ['created_at']
    
    fieldsets = (
        (None, {
            'fields': ('investment', 'activity_type', 'amount', 'date', 'details')
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(PerformanceSnapshot)
class PerformanceSnapshotAdmin(admin.ModelAdmin):
    """Admin interface for PerformanceSnapshot model."""
    list_display = ['investment', 'date', 'value', 'created_at']
    list_filter = ['date']
    search_fields = ['investment__name']
    readonly_fields = ['created_at']
    
    fieldsets = (
        (None, {
            'fields': ('investment', 'date', 'value')
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


class TransferDocumentInline(admin.TabularInline):
    """Inline admin for transfer documents."""
    model = TransferDocument
    extra = 0


@admin.register(OwnershipTransfer)
class OwnershipTransferAdmin(admin.ModelAdmin):
    """Admin interface for OwnershipTransfer model."""
    list_display = ['investment', 'from_user', 'get_recipient', 'transfer_amount', 
                    'transfer_fee', 'status', 'initiated_date']
    list_filter = ['status', 'transfer_type', 'initiated_date']
    search_fields = ['investment__name', 'from_user__email', 'to_user__email', 'to_email']
    readonly_fields = ['transfer_fee', 'net_amount', 'initiated_date', 'created_at', 'updated_at']
    inlines = [TransferDocumentInline]
    
    fieldsets = (
        ('Investment & Users', {
            'fields': ('investment', 'from_user', 'to_user', 'to_email', 'to_name')
        }),
        ('Transfer Details', {
            'fields': ('transfer_type', 'percentage', 'transfer_amount', 'transfer_fee', 'net_amount')
        }),
        ('Compliance', {
            'fields': ('reason',)
        }),
        ('Status & Dates', {
            'fields': ('status', 'initiated_date', 'completion_date', 'estimated_completion_date')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_recipient(self, obj):
        return obj.to_user.email if obj.to_user else obj.to_email
    get_recipient.short_description = 'Recipient'


@admin.register(TransferDocument)
class TransferDocumentAdmin(admin.ModelAdmin):
    """Admin interface for TransferDocument model."""
    list_display = ['transfer', 'document_type', 'uploaded_at']
    list_filter = ['document_type', 'uploaded_at']
    search_fields = ['transfer__investment__name']
    readonly_fields = ['uploaded_at']

