"""
Views for the investments app.
Handles investment CRUD, portfolio analytics, and capital activities.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from datetime import datetime, timedelta
from django.utils import timezone

from .models import Investment, CapitalActivity, PerformanceSnapshot, OwnershipTransfer, TransferDocument
from .serializers import (
    InvestmentListSerializer,
    InvestmentDetailSerializer,
    InvestmentCreateUpdateSerializer,
    CapitalActivitySerializer,
    PerformanceSnapshotSerializer,
    PortfolioSummarySerializer,
    SectorAllocationSerializer,
    RiskMetricsSerializer,
    PerformanceDataSerializer,
    ReturnsAnalysisSerializer,
    ReturnAttributionSerializer,
    DistributionHistorySerializer,
    OwnershipTransferListSerializer,
    OwnershipTransferDetailSerializer,
    OwnershipTransferCreateSerializer,
    QuarterlyPerformanceSerializer,
    AssetAllocationSerializer,
    RebalancingRecommendationSerializer,
    ConcentrationRiskSerializer,
    StressTestScenarioSerializer,
    PortfolioVolatilitySerializer,
)
from .utils import (
    calculate_portfolio_metrics,
    calculate_sector_allocation,
    calculate_portfolio_beta,
    calculate_sharpe_ratio,
    calculate_max_drawdown,
    calculate_value_at_risk,
    calculate_returns_analysis,
    calculate_return_attribution,
    get_distribution_history,
    calculate_quarterly_performance,
    calculate_alpha,
    calculate_asset_allocation,
    calculate_rebalancing_recommendations,
    calculate_concentration_risk,
    calculate_stress_test_scenarios,
    calculate_portfolio_volatility,
)
import logging

logger = logging.getLogger('investments')


class InvestmentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing investments.
    
    Provides CRUD operations for investments and individual investment details.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return investments for the current user."""
        return Investment.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return InvestmentListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return InvestmentCreateUpdateSerializer
        return InvestmentDetailSerializer
    
    def perform_create(self, serializer):
        """Create investment for current user."""
        investment = serializer.save()
        logger.info(f"Investment created: {investment.name} by {self.request.user.email}")
    
    def perform_update(self, serializer):
        """Update investment."""
        investment = serializer.save()
        logger.info(f"Investment updated: {investment.name} by {self.request.user.email}")
    
    def perform_destroy(self, instance):
        """Delete investment."""
        logger.info(f"Investment deleted: {instance.name} by {self.request.user.email}")
        instance.delete()
    
    @action(detail=True, methods=['get'])
    def performance_history(self, request, pk=None):
        """
        Get performance history for an investment.
        Query params: days (default 365)
        """
        investment = self.get_object()
        days = int(request.query_params.get('days', 365))
        
        snapshots = investment.get_performance_history(days=days)
        serializer = PerformanceSnapshotSerializer(snapshots, many=True)
        
        return Response({
            'investment_id': investment.id,
            'investment_name': investment.name,
            'period_days': days,
            'data': serializer.data
        })


class CapitalActivityViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing capital activities.
    
    Provides CRUD operations for capital calls and distributions.
    """
    serializer_class = CapitalActivitySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return capital activities for user's investments."""
        user_investments = Investment.objects.filter(user=self.request.user)
        queryset = CapitalActivity.objects.filter(investment__in=user_investments)
        
        # Filter by investment if provided
        investment_id = self.request.query_params.get('investment')
        if investment_id:
            queryset = queryset.filter(investment_id=investment_id)
        
        # Filter by activity type if provided
        activity_type = self.request.query_params.get('activity_type')
        if activity_type:
            queryset = queryset.filter(activity_type=activity_type)
        
        return queryset
    
    def perform_create(self, serializer):
        """Create capital activity."""
        activity = serializer.save()
        logger.info(
            f"Capital activity created: {activity.activity_type} for {activity.investment.name}, "
            f"Amount: ${activity.amount}"
        )


class PortfolioAnalyticsViewSet(viewsets.ViewSet):
    """
    ViewSet for comprehensive portfolio analytics.
    
    Provides endpoints for portfolio overview, performance analysis, asset allocation, and risk metrics.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = QuarterlyPerformanceSerializer  # Default serializer
    
    @action(detail=False, methods=['get'])
    def overview(self, request):
        """
        Portfolio overview with key metrics, sector performance, and individual investments.
        """
        # Key metrics
        metrics = calculate_portfolio_metrics(request.user)
        
        # Sector performance
        sector_allocation = calculate_sector_allocation(request.user)
        
        # Individual investment performance
        investments = request.user.investments.filter(status__in=['ACTIVE', 'UNDERPERFORMING'])
        investment_performance = []
        
        for inv in investments:
            investment_performance.append({
                'name': inv.name,
                'value': float(inv.current_value),
                'percentage': float((inv.current_value / metrics['total_value'] * 100) if metrics['total_value'] > 0 else 0),
                'return_percentage': float(inv.unrealized_gain_percentage)
            })
        
        return Response({
            'key_metrics': {
                'total_portfolio_return': float(metrics.get('unrealized_gains_percentage', 0)),
                'annualized_irr': float(metrics.get('average_irr', 0)),
                'portfolio_value': float(metrics.get('total_value', 0)),
                'distributions_received': float(calculate_returns_analysis(request.user).get('realized_gains', 0))
            },
            'sector_performance': sector_allocation,
            'investment_performance': investment_performance
        })
    
    @action(detail=False, methods=['get'])
    def performance_analysis(self, request):
        """
        Performance analysis with historical data and risk-adjusted metrics.
        """
        # Quarterly performance
        quarterly_perf = calculate_quarterly_performance(request.user)
        
        # Risk-adjusted metrics
        metrics = calculate_portfolio_metrics(request.user)
        sharpe = calculate_sharpe_ratio(request.user)
        alpha = calculate_alpha(request.user)
        beta = calculate_portfolio_beta(request.user)
        max_dd = calculate_max_drawdown(request.user)
        var = calculate_value_at_risk(request.user)
        
        return Response({
            'historical_performance': quarterly_perf,
            'performance_metrics': {
                'sharpe_ratio': float(sharpe),
                'alpha': float(alpha),
                'beta': float(beta),
                'max_drawdown': float(max_dd),
                'value_at_risk': float(var),
            }
        })
    
    @action(detail=False, methods=['get'])
    def asset_allocation(self, request):
        """
        Asset allocation with current vs target and rebalancing recommendations.
        """
        # Current allocation
        allocation = calculate_asset_allocation(request.user)
        
        # Rebalancing recommendations
        recommendations = calculate_rebalancing_recommendations(request.user)
        
        return Response({
            'current_allocation': allocation,
            'rebalancing_recommendations': recommendations
        })
    
    @action(detail=False, methods=['get'])
    def risk_metrics(self, request):
        """
        Risk assessment with volatility, concentration, and stress testing.
        """
        # Volatility
        volatility = calculate_portfolio_volatility(request.user)
        
        # Concentration risk
        concentration = calculate_concentration_risk(request.user)
        
        # Stress testing
        stress_tests = calculate_stress_test_scenarios(request.user)
        
        return Response({
            'risk_assessment': {
                'portfolio_volatility': volatility['volatility'],
                'volatility_level': volatility['risk_level'],
                'concentration_risk': {
                    'top_3_holdings': concentration['top_3_concentration'],
                    'risk_level': concentration['risk_level']
                },
                'liquidity_risk': 'High',  # Private equity nature
                'geographic_risk': 'Low'  # Assumed well diversified
            },
            'stress_testing': stress_tests
        })





class OwnershipTransferViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing ownership transfers.
    
    Provides CRUD operations and status management for transfers.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return transfers for the current user (both outgoing and incoming)."""
        from django.db.models import Q
        
        user = self.request.user
        queryset = OwnershipTransfer.objects.filter(
            Q(from_user=user) | Q(to_user=user)
        ).select_related('investment', 'from_user', 'to_user')
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by direction
        direction = self.request.query_params.get('direction')
        if direction == 'outgoing':
            queryset = queryset.filter(from_user=user)
        elif direction == 'incoming':
            queryset = queryset.filter(to_user=user)
        
        return queryset.order_by('-created_at')
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'retrieve':
            return OwnershipTransferDetailSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return OwnershipTransferCreateSerializer
        return OwnershipTransferListSerializer
    
    def perform_create(self, serializer):
        """Create transfer."""
        transfer = serializer.save()
        logger.info(f"Transfer created: {transfer.id} by {self.request.user.email}")
    
    def perform_destroy(self, instance):
        """Cancel transfer (soft delete by changing status)."""
        # Only owner can cancel
        if instance.from_user != self.request.user:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You can only cancel your own transfers.")
        
        # Can only cancel pending or draft transfers
        if instance.status not in ['DRAFT', 'PENDING']:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Can only cancel draft or pending transfers.")
        
        instance.status = 'CANCELLED'
        instance.save()
        logger.info(f"Transfer cancelled: {instance.id} by {self.request.user.email}")
    
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """
        Submit a draft transfer for approval.
        Changes status from DRAFT to PENDING.
        """
        transfer = self.get_object()
        
        # Only owner can submit
        if transfer.from_user != request.user:
            return Response(
                {"error": "You can only submit your own transfers."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Can only submit drafts
        if transfer.status != 'DRAFT':
            return Response(
                {"error": "Only draft transfers can be submitted."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update status
        transfer.status = 'PENDING'
        transfer.estimated_completion_date = timezone.now() + timedelta(days=10)
        transfer.save()
        
        logger.info(f"Transfer submitted: {transfer.id}")
        
        serializer = self.get_serializer(transfer)
        return Response({
            "message": "Transfer submitted successfully.",
            "transfer": serializer.data
        })
    
    @action(detail=False, methods=['get'])
    def pending(self, request):
        """
        Get all pending transfers (both outgoing and incoming).
        """
        from django.db.models import Q
        
        user = request.user
        transfers = OwnershipTransfer.objects.filter(
            Q(from_user=user) | Q(to_user=user),
            status__in=['PENDING', 'APPROVED']
        ).select_related('investment', 'from_user', 'to_user').order_by('-created_at')
        
        serializer = OwnershipTransferListSerializer(transfers, many=True, context={'request': request})
        
        return Response({
            'pending_transfers': serializer.data,
            'total_count': transfers.count()
        })
    
    @action(detail=False, methods=['get'])
    def history(self, request):
        """
        Get transfer history (completed and cancelled transfers).
        """
        from django.db.models import Q
        
        user = request.user
        transfers = OwnershipTransfer.objects.filter(
            Q(from_user=user) | Q(to_user=user),
            status__in=['COMPLETED', 'CANCELLED', 'REJECTED']
        ).select_related('investment', 'from_user', 'to_user').order_by('-completion_date', '-created_at')
        
        serializer = OwnershipTransferListSerializer(transfers, many=True, context={'request': request})
        
        return Response({
            'transfer_history': serializer.data,
            'total_count': transfers.count()
        })
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def approve(self, request, pk=None):
        """
        Approve a pending transfer (Admin only).
        Changes status from PENDING to APPROVED.
        """
        transfer = self.get_object()
        
        if transfer.status != 'PENDING':
            return Response(
                {"error": "Only pending transfers can be approved."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        transfer.status = 'APPROVED'
        transfer.save()
        
        logger.info(f"Transfer approved: {transfer.id} by {request.user.email}")
        
        serializer = self.get_serializer(transfer)
        return Response({
            "message": "Transfer approved successfully.",
            "transfer": serializer.data
        })
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def complete(self, request, pk=None):
        """
        Complete an approved transfer (Admin only).
        Changes status from APPROVED to COMPLETED.
        This triggers the signal to execute the asset transfer.
        """
        transfer = self.get_object()
        
        if transfer.status != 'APPROVED':
            return Response(
                {"error": "Only approved transfers can be completed."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        transfer.status = 'COMPLETED'
        transfer.save()  # Signal will handle the rest
        
        logger.info(f"Transfer completed: {transfer.id} by {request.user.email}")
        
        serializer = self.get_serializer(transfer)
        return Response({
            "message": "Transfer completed successfully.",
            "transfer": serializer.data
        })


