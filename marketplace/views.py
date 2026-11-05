"""
Views for the marketplace app.
Handles marketplace opportunity listings, details, and user actions.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from decimal import Decimal, InvalidOperation
from django.db.models import Case, DecimalField, ExpressionWrapper, F, IntegerField, Q, Value, When
from django.db.models.functions import Lower
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.exceptions import ValidationError

from core.utils import query_list, resolve_ordering

from .models import MarketplaceOpportunity, InvestmentInterest, InvestorInterest
from .serializers import (
    MarketplaceOpportunityListSerializer,
    MarketplaceOpportunityDetailSerializer,
    InvestorInterestSerializer,
)
import logging

logger = logging.getLogger('marketplace')


class MarketplaceOpportunityViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for browsing marketplace opportunities.
    
    Provides list and detail views with search and filtering.
    """
    permission_classes = [AllowAny]  # Public marketplace
    
    # ?ordering= values (prefix '-' to reverse). There is no closing date on an
    # opportunity, so "closing" means CLOSING_SOON first, then the most funded.
    ORDERING_OPTIONS = {
        'featured': ['-is_featured', '-created_at', '-id'],
        'closing': ['closing_rank', '-funding_progress', '-created_at', '-id'],
        'closing_soon': ['closing_rank', '-funding_progress', '-created_at', '-id'],
        'min_investment': ['min_investment', 'title_sort', 'id'],
        'title': ['title_sort', 'id'],
        'name': ['title_sort', 'id'],
        'newest': ['-created_at', '-id'],
    }

    @extend_schema(parameters=[
        OpenApiParameter('search', str, description='Text match on title, description, sector and investment type '
                         '(codes or display labels).'),
        OpenApiParameter('sector', str, description='Sector code(s), e.g. HEALTHCARE. Repeat the parameter or '
                         'comma-separate for several; matches any.'),
        OpenApiParameter('risk_level', str, description='LOW | MEDIUM | HIGH. Multi-value, matches any.'),
        OpenApiParameter('investment_type', str, description='FIXED | VARIABLE. Multi-value, matches any.'),
        OpenApiParameter('status', str, description='NEW | ACTIVE | CLOSING_SOON. Multi-value, matches any.'),
        OpenApiParameter('max_min_investment', float, description='Only opportunities whose min_investment is '
                         '<= this amount.'),
        OpenApiParameter('ordering', str, description='featured (default) | closing | min_investment | title | '
                         'newest. Prefix with - to reverse.'),
    ])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        """
        Return open opportunities with optional filtering, search and ordering.

        Multi-value params accept repeated keys or comma-separated codes; values
        within one param are OR'ed, different params are AND'ed. Missing or
        empty params apply no filter.
        """
        queryset = MarketplaceOpportunity.objects.filter(status__in=['NEW', 'ACTIVE', 'CLOSING_SOON'])
        if self.action != 'list':
            # Detail lookups ignore list filters
            return queryset.prefetch_related('documents', 'tags')

        params = self.request.query_params
        
        search = params.get('search', '').strip()
        if search:
            term = search.lower()
            sectors = [code for code, label in MarketplaceOpportunity.SECTOR_CHOICES if term in label.lower()]
            types = [code for code, label in MarketplaceOpportunity.INVESTMENT_TYPE_CHOICES if term in label.lower()]
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(sector__icontains=search) |
                Q(sector__in=sectors) |
                Q(investment_type__icontains=search) |
                Q(investment_type__in=types)
            )
        
        for param, field in (('sector', 'sector'), ('risk_level', 'risk_level'),
                             ('investment_type', 'investment_type'), ('status', 'status')):
            values = query_list(params, param)
            if values:
                queryset = queryset.filter(**{f'{field}__in': values})
        
        max_min_investment = params.get('max_min_investment', '').strip()
        if max_min_investment:
            try:
                queryset = queryset.filter(min_investment__lte=Decimal(max_min_investment))
            except InvalidOperation:
                raise ValidationError({'max_min_investment': 'Must be a number.'})
        
        ordering = resolve_ordering(params.get('ordering'), self.ORDERING_OPTIONS, 'featured')
        if any(f.lstrip('-') in ('closing_rank', 'funding_progress') for f in ordering):
            queryset = queryset.annotate(
                closing_rank=Case(When(status='CLOSING_SOON', then=Value(0)), default=Value(1),
                                  output_field=IntegerField()),
                funding_progress=ExpressionWrapper(
                    F('current_raised_amount') / F('target_raise_amount'), output_field=DecimalField()
                ),
            )
        if any(f.lstrip('-') == 'title_sort' for f in ordering):
            queryset = queryset.annotate(title_sort=Lower('title'))
        
        return queryset.order_by(*ordering).prefetch_related('tags')
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'retrieve':
            return MarketplaceOpportunityDetailSerializer
        return MarketplaceOpportunityListSerializer
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def request_information(self, request, pk=None):
        """
        Request information about an opportunity.
        Creates an investment interest record.
        """
        opportunity = self.get_object()
        
        # Create or get investment interest
        interest, created = InvestmentInterest.objects.get_or_create(
            user=request.user,
            opportunity=opportunity,
            interest_type='REQUESTED_INFO'
        )
        
        if created:
            logger.info(
                f"Information requested: {request.user.email} for {opportunity.title}"
            )
            message = "Information request submitted successfully."
        else:
            message = "You have already requested information for this opportunity."
        
        return Response({
            'success': True,
            'message': message,
            'interest_id': interest.id
        })
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def bookmark(self, request, pk=None):
        """
        Bookmark an opportunity (add to watchlist).
        """
        opportunity = self.get_object()
        
        # Create or get bookmark
        interest, created = InvestmentInterest.objects.get_or_create(
            user=request.user,
            opportunity=opportunity,
            interest_type='BOOKMARKED'
        )
        
        if created:
            logger.info(
                f"Opportunity bookmarked: {request.user.email} bookmarked {opportunity.title}"
            )
            message = "Opportunity added to your watchlist."
        else:
            message = "This opportunity is already in your watchlist."
        
        return Response({
            'success': True,
            'message': message,
            'interest_id': interest.id
        })
    
    @action(detail=True, methods=['delete'], permission_classes=[IsAuthenticated])
    def remove_bookmark(self, request, pk=None):
        """
        Remove bookmark from an opportunity.
        Works for closed opportunities too, which no longer appear in the listing.
        """
        if not str(pk).isdigit():
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        # Delete bookmark if exists
        deleted_count = InvestmentInterest.objects.filter(
            user=request.user,
            opportunity_id=pk,
            interest_type='BOOKMARKED'
        ).delete()[0]
        
        if deleted_count > 0:
            logger.info(
                f"Bookmark removed: {request.user.email} removed opportunity {pk} from watchlist"
            )
            message = "Opportunity removed from your watchlist."
        else:
            message = "This opportunity was not in your watchlist."
        
        return Response({
            'success': True,
            'message': message
        })


class WatchlistViewSet(viewsets.ViewSet):
    """
    ViewSet for user's watchlist (bookmarked opportunities).
    """
    permission_classes = [IsAuthenticated]
    serializer_class = MarketplaceOpportunityListSerializer  # Default serializer
    
    def list(self, request):
        """
        Get user's watchlist.
        """
        # Step 1: fetch the bookmarked opportunity IDs in a single lightweight query.
        # Using values_list avoids loading full model instances just to extract a FK.
        # Step 2: query opportunities directly with prefetch — avoids materialising
        # a Python list from a bookmark queryset (previous code's overhead).
        bookmarked_ids = InvestmentInterest.objects.filter(
            user=request.user,
            interest_type='BOOKMARKED',
        ).values_list('opportunity_id', flat=True)

        from .models import MarketplaceOpportunity
        opportunities = MarketplaceOpportunity.objects.filter(
            pk__in=bookmarked_ids,
        ).prefetch_related('tags').order_by('-created_at')

        serializer = MarketplaceOpportunityListSerializer(
            opportunities,
            many=True,
            context={'request': request}
        )

        return Response({
            'watchlist': serializer.data,
            'total_count': len(serializer.data)
        })


class InvestorInterestViewSet(viewsets.ModelViewSet):
    """
    ViewSet for tracking specific investor intent (pledges).

    Investors create pledges and may edit or cancel them while PENDING. Staff
    convert a pledge into an investment via the admin API.
    """
    serializer_class = InvestorInterestSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        """Users can only see their own interest expressions."""
        if getattr(self, 'swagger_fake_view', False):  # OpenAPI schema generation
            return InvestorInterest.objects.none()
        return InvestorInterest.objects.filter(user=self.request.user).select_related('user', 'opportunity')

    def perform_create(self, serializer):
        """Log interest creation."""
        interest = serializer.save()
        logger.info(
            f"Investor pledged interest: {self.request.user.email} pledged "
            f"${interest.amount} for {interest.opportunity.title}"
        )

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Withdraw a PENDING pledge."""
        interest = self.get_object()
        if interest.status != 'PENDING':
            return Response(
                {"error": f"Cannot cancel a pledge with status {interest.status}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        interest.status = 'CANCELLED'
        interest.save(update_fields=['status', 'updated_at'])
        return Response(InvestorInterestSerializer(interest, context={'request': request}).data)
