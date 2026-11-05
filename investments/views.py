"""
Views for the investments app.
Handles investment CRUD, portfolio analytics, and capital activities.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter

from core.utils import query_list, resolve_ordering
from .models import Investment, CapitalActivity, OwnershipTransfer, TransferDocument, SecondaryMarketInterest
from .serializers import (
    InvestmentListSerializer,
    InvestmentDetailSerializer,
    CapitalActivitySerializer,
    PerformanceSnapshotSerializer,
    OwnershipTransferListSerializer,
    OwnershipTransferDetailSerializer,
    OwnershipTransferCreateSerializer,
    SecondaryMarketListingSerializer,
    SecondaryMarketInterestSerializer,
    SecondaryMarketInterestCreateSerializer,
    QuarterlyPerformanceSerializer,
)
from .utils import (
    calculate_portfolio_metrics,
    calculate_sector_allocation,
    calculate_portfolio_beta,
    calculate_sharpe_ratio,
    calculate_max_drawdown,
    calculate_value_at_risk,
    calculate_returns_analysis,
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


class InvestmentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only view of the current user's investments.

    Investments are created by staff converting a marketplace pledge, by
    completed ownership transfers / secondary purchases, or via the admin API.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return investments for the current user."""
        if getattr(self, 'swagger_fake_view', False):  # OpenAPI schema generation
            return Investment.objects.none()
        queryset = Investment.objects.filter(
            user=self.request.user
        ).select_related('opportunity')
        if self.action == 'retrieve':
            # Nested capital activities (each also renders its investment)
            queryset = queryset.prefetch_related('capital_activities')
        return queryset
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return InvestmentListSerializer
        return InvestmentDetailSerializer
    
    @action(detail=True, methods=['get'])
    def performance_history(self, request, pk=None):
        """
        Get performance history for an investment.
        Query params: days (default 365)
        """
        investment = self.get_object()
        try:
            days = min(max(int(request.query_params.get('days', 365)), 1), 3650)
        except ValueError:
            return Response({"error": "days must be an integer."}, status=status.HTTP_400_BAD_REQUEST)
        
        snapshots = investment.get_performance_history(days=days)
        serializer = PerformanceSnapshotSerializer(snapshots, many=True)
        
        return Response({
            'investment_id': investment.id,
            'investment_name': investment.get_name(),
            'period_days': days,
            'data': serializer.data
        })


class CapitalActivityViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only view of capital activities (calls, distributions, exits) on the
    current user's investments. Staff record activities via the admin API.
    """
    serializer_class = CapitalActivitySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return capital activities for user's investments."""
        if getattr(self, 'swagger_fake_view', False):  # OpenAPI schema generation
            return CapitalActivity.objects.none()
        # Filter via JOIN (investment__user) instead of a subquery to avoid
        # a separate IN (...) query for every request.
        queryset = CapitalActivity.objects.filter(
            investment__user=self.request.user
        ).select_related('investment', 'investment__opportunity')

        # Filter by investment if provided
        investment_id = self.request.query_params.get('investment')
        if investment_id:
            if not investment_id.isdigit():
                raise ValidationError({"investment": "Must be an investment ID."})
            queryset = queryset.filter(investment_id=investment_id)

        # Filter by activity type if provided
        activity_type = self.request.query_params.get('activity_type')
        if activity_type:
            queryset = queryset.filter(activity_type=activity_type)

        return queryset


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
        
        # Individual investment performance — select_related avoids N+1 from
        # get_name() / get_sector() / unrealized_gain_percentage calling opportunity.
        investments = request.user.investments.filter(
            status__in=['ACTIVE', 'UNDERPERFORMING']
        ).select_related('opportunity')
        total_value = metrics['total_value']
        investment_performance = [
            {
                'name': inv.get_name(),
                'value': float(inv.current_value),
                'percentage': float(inv.current_value / total_value * 100) if total_value > 0 else 0.0,
                'return_percentage': float(inv.unrealized_gain_percentage),
            }
            for inv in investments
        ]
        
        return Response({
            'key_metrics': {
                'total_portfolio_return': float(metrics.get('unrealized_gains_percentage', 0)),
                'annualized_irr': float(metrics.get('average_irr', 0)),
                'portfolio_value': float(metrics.get('total_value', 0)),
                'distributions_received': float(calculate_returns_analysis(request.user)['cash_received'])
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
        recommendations = calculate_rebalancing_recommendations(request.user, allocation=allocation)
        
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
    Ownership transfers created by an investment's owner.

    Owners create transfers as DRAFT (or PENDING to submit straight away), edit
    drafts, submit them and cancel them. A PENDING transfer without a recipient
    (to_user) is listed on the secondary market. Approval and completion are
    staff actions: /api/admin/transfers/{id}/approve|complete|reject/.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return transfers for the current user (both outgoing and incoming)."""
        if getattr(self, 'swagger_fake_view', False):  # OpenAPI schema generation
            return OwnershipTransfer.objects.none()
        user = self.request.user
        queryset = OwnershipTransfer.objects.filter(
            Q(from_user=user) | Q(to_user=user)
        ).select_related('investment', 'investment__opportunity', 'from_user', 'to_user')
        
        if self.action == 'retrieve':
            queryset = queryset.prefetch_related('documents')
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter.upper())
        
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
    
    def perform_update(self, serializer):
        """Only the owner may edit, and only while the transfer is a draft."""
        transfer = serializer.instance
        if transfer.from_user_id != self.request.user.id:
            raise PermissionDenied("You can only update your own transfers.")
        if transfer.status != 'DRAFT':
            raise ValidationError("Only draft transfers can be updated.")
        transfer = serializer.save()
        logger.info(f"Transfer updated: {transfer.id} by {self.request.user.email}")
    
    def perform_destroy(self, instance):
        """Cancel transfer (soft delete by changing status)."""
        if instance.from_user_id != self.request.user.id:
            raise PermissionDenied("You can only cancel your own transfers.")
        
        with transaction.atomic():
            # Lock and re-check so a cancel can't race a purchase of the listing
            instance = OwnershipTransfer.objects.select_for_update().get(pk=instance.pk)
            if instance.status not in ['DRAFT', 'PENDING']:
                raise ValidationError("Can only cancel draft or pending transfers.")
            instance.status = 'CANCELLED'
            instance.save(update_fields=['status', 'updated_at'])
            SecondaryMarketInterest.objects.filter(transfer=instance, status='PENDING').update(
                status='CANCELLED', updated_at=timezone.now()
            )
        logger.info(f"Transfer cancelled: {instance.id} by {self.request.user.email}")
    
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """
        Submit a draft transfer for approval.
        Changes status from DRAFT to PENDING.
        """
        transfer = self.get_object()
        
        # Only owner can submit
        if transfer.from_user_id != request.user.id:
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
        
        transfer.status = 'PENDING'
        transfer.estimated_completion_date = timezone.now() + timedelta(days=10)
        transfer.save(update_fields=['status', 'estimated_completion_date', 'updated_at'])
        
        logger.info(f"Transfer submitted: {transfer.id}")
        
        return Response({
            "message": "Transfer submitted successfully.",
            "transfer": OwnershipTransferListSerializer(transfer, context={'request': request}).data
        })
    
    @action(detail=False, methods=['get'])
    def pending(self, request):
        """
        Get all pending transfers (both outgoing and incoming).
        """
        user = request.user
        transfers = OwnershipTransfer.objects.filter(
            Q(from_user=user) | Q(to_user=user),
            status__in=['PENDING', 'APPROVED']
        ).select_related('investment', 'investment__opportunity', 'from_user', 'to_user').order_by('-created_at')
        
        serializer = OwnershipTransferListSerializer(transfers, many=True, context={'request': request})

        return Response({
            'pending_transfers': serializer.data,
            'total_count': len(serializer.data),
        })
    
    @action(detail=False, methods=['get'])
    def history(self, request):
        """
        Get transfer history (completed and cancelled transfers).
        """
        user = request.user
        transfers = OwnershipTransfer.objects.filter(
            Q(from_user=user) | Q(to_user=user),
            status__in=['COMPLETED', 'CANCELLED', 'REJECTED']
        ).select_related('investment', 'investment__opportunity', 'from_user', 'to_user').order_by(
            '-completion_date', '-created_at'
        )
        
        serializer = OwnershipTransferListSerializer(transfers, many=True, context={'request': request})

        return Response({
            'transfer_history': serializer.data,
            'total_count': len(serializer.data),
        })
    
    @action(detail=True, methods=['get'], url_path=r'documents/(?P<document_id>\d+)/download')
    def download_document(self, request, pk=None, document_id=None):
        """Download a transfer document (sender and recipient only)."""
        transfer = self.get_object()
        document = get_object_or_404(TransferDocument, pk=document_id, transfer=transfer)
        try:
            return FileResponse(document.file.open('rb'), as_attachment=True,
                                filename=document.file.name.rsplit('/', 1)[-1])
        except FileNotFoundError:
            return Response({"error": "Document file is missing."}, status=status.HTTP_404_NOT_FOUND)


class SecondaryMarketplaceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only ViewSet exposing PENDING ownership transfers without a named
    recipient as secondary-market listings.

    Any authenticated user can browse investments that other users have put up for sale.
    Filtering is supported via query params (multi-value params accept repeated
    keys or comma-separated codes; OR within a param, AND across params):
      - search       : listing / investment name, sector code or label
      - sector       : sector code(s), e.g. TECHNOLOGY
      - transfer_type: FULL | PARTIAL
      - min_amount   : minimum transfer_amount (same currency/decimal format as transfer_amount)
      - max_amount   : maximum transfer_amount
      - ordering     : featured / newest (default) | asking | transfer_amount | name; prefix - to reverse

    Extra action:
      POST /secondary-market/{id}/express_interest/
        Registers the buyer's interest (SecondaryMarketInterest) for staff to review.
    """
    serializer_class = SecondaryMarketListingSerializer
    permission_classes = [permissions.IsAuthenticated]

    ORDERING_OPTIONS = {
        'featured': ['-initiated_date', '-id'],
        'newest': ['-initiated_date', '-id'],
        'asking': ['-transfer_amount', '-initiated_date', '-id'],  # highest asking first
        'transfer_amount': ['transfer_amount', '-initiated_date', '-id'],
        'name': ['listing_name', '-initiated_date', '-id'],
        'investment_name': ['listing_name', '-initiated_date', '-id'],
    }

    @extend_schema(parameters=[
        OpenApiParameter('search', str, description='Match listing / investment name and sector (code or label).'),
        OpenApiParameter('sector', str, description='Sector code(s). Repeat or comma-separate; matches any.'),
        OpenApiParameter('transfer_type', str, description='FULL | PARTIAL. Multi-value, matches any.'),
        OpenApiParameter('min_amount', float, description='Minimum transfer_amount.'),
        OpenApiParameter('max_amount', float, description='Maximum transfer_amount.'),
        OpenApiParameter('ordering', str, description='featured / newest (default) | asking (highest first) | '
                         'transfer_amount (lowest first) | name. Prefix with - to reverse.'),
    ])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        """Return all PENDING public listings (platform-wide, not scoped to current user)."""
        from django.db.models.functions import Coalesce, Lower

        # Direct transfers to a named recipient are not for sale
        qs = OwnershipTransfer.objects.filter(
            status='PENDING',
            to_user__isnull=True,
        ).select_related(
            'investment',
            'investment__opportunity',
            'from_user',
        )
        if self.action != 'list':
            return qs

        params = self.request.query_params

        # A listing's sector comes from its opportunity, or from the investment
        # itself when it isn't linked to one.
        def sector_in(codes):
            return (
                Q(investment__opportunity__sector__in=codes)
                | Q(investment__opportunity__isnull=True, investment__sector__in=codes)
            )

        search = params.get('search', '').strip()
        if search:
            term = search.lower()
            sectors = [code for code, label in Investment.SECTOR_CHOICES
                       if term in label.lower() or term in code.lower()]
            qs = qs.filter(
                Q(investment__opportunity__title__icontains=search)
                | Q(investment__name__icontains=search)
                | sector_in(sectors)
            )

        sectors = query_list(params, 'sector')
        if sectors:
            qs = qs.filter(sector_in(sectors))

        transfer_types = query_list(params, 'transfer_type')
        if transfer_types:
            qs = qs.filter(transfer_type__in=transfer_types)

        for param, lookup in (('min_amount', 'transfer_amount__gte'), ('max_amount', 'transfer_amount__lte')):
            raw = params.get(param, '').strip()
            if raw:
                try:
                    qs = qs.filter(**{lookup: Decimal(raw)})
                except InvalidOperation:
                    raise ValidationError({param: "Must be a number."})

        ordering = resolve_ordering(params.get('ordering'), self.ORDERING_OPTIONS, 'featured')
        if any(f.lstrip('-') == 'listing_name' for f in ordering):
            qs = qs.annotate(listing_name=Lower(Coalesce('investment__opportunity__title', 'investment__name')))
        return qs.order_by(*ordering)

    @action(detail=True, methods=['post'])
    def express_interest(self, request, pk=None):
        """
        Register buyer interest in a secondary-market listing.

        Creates a SecondaryMarketInterest record (PENDING) tied directly to the
        OwnershipTransfer so that when the status is updated to CONVERTED the
        system can automatically deduct from the seller and credit the buyer.

        Optional request body:
          amount (Decimal): how much the buyer wants — defaults to the full
                            transfer_amount of the listing.
        """
        transfer = self.get_object()

        # Seller cannot express interest in their own listing
        if transfer.from_user == request.user:
            return Response(
                {"error": "You cannot express interest in your own listing."},
                status=status.HTTP_403_FORBIDDEN,
            )

        existing = SecondaryMarketInterest.objects.filter(transfer=transfer, buyer=request.user).first()
        if existing and existing.status != 'CANCELLED':
            return Response(
                {
                    "message": "Interest registered successfully.",
                    "interest_id": existing.id,
                    "created": False,
                    "transfer_id": transfer.id,
                    "amount": str(existing.amount),
                    "status": existing.status,
                    "note": "You already have a registered interest for this listing.",
                },
                status=status.HTTP_200_OK,
            )

        amount = request.data.get('amount', transfer.transfer_amount)
        serializer = SecondaryMarketInterestCreateSerializer(
            instance=None,
            data={
                'transfer':       transfer.pk,
                'amount':         amount,
                'interest_date':  timezone.now().date().isoformat(),
            },
            context={'request': request},
        )
        with transaction.atomic():
            if existing:
                # A previously cancelled interest is replaced by a fresh one
                existing.delete()
            serializer.is_valid(raise_exception=True)
            interest = serializer.save(buyer=request.user)
        created = True

        logger.info(
            f"Secondary market interest: {request.user.email} → "
            f"transfer #{transfer.id} (${interest.amount}), created={created}"
        )

        return Response(
            {
                "message": "Interest registered successfully.",
                "interest_id": interest.id,
                "created": created,
                "transfer_id": transfer.id,
                "amount": str(interest.amount),
                "status": interest.status,
                "note": "Your interest will be reviewed; the purchase executes once approved by staff.",
            },
            status=status.HTTP_200_OK,
        )


class SecondaryMarketInterestViewSet(viewsets.ModelViewSet):
    """
    ViewSet for a buyer to view and manage their own SecondaryMarketInterest records.

    Buyers can register interest, change the amount while PENDING, and cancel.
    The purchase itself executes when staff set the status to CONVERTED via
    PATCH /api/admin/secondary-interests/{id}/.

    List    : GET   /secondary-market-interests/
    Create  : POST  /secondary-market-interests/          { transfer, amount }
    Retrieve: GET   /secondary-market-interests/{id}/
    Update  : PATCH /secondary-market-interests/{id}/     { amount }
    Cancel  : POST  /secondary-market-interests/{id}/cancel/
    """
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):  # OpenAPI schema generation
            return SecondaryMarketInterest.objects.none()
        return SecondaryMarketInterest.objects.filter(
            buyer=self.request.user
        ).select_related('buyer', 'transfer', 'transfer__investment', 'transfer__from_user')

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return SecondaryMarketInterestCreateSerializer
        return SecondaryMarketInterestSerializer

    def perform_create(self, serializer):
        serializer.save(buyer=self.request.user)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Withdraw a PENDING interest."""
        interest = self.get_object()
        if interest.status != 'PENDING':
            return Response(
                {"error": f"Cannot cancel an interest with status {interest.status}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        interest.status = 'CANCELLED'
        interest.save(update_fields=['status', 'updated_at'])
        return Response(SecondaryMarketInterestSerializer(interest).data)

