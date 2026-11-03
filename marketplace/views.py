"""
Views for the marketplace app.
Handles marketplace opportunity listings, details, and user actions.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.db.models import Q

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
    
    def get_queryset(self):
        """Return opportunities with optional filtering and search."""
        queryset = MarketplaceOpportunity.objects.filter(status__in=['NEW', 'ACTIVE', 'CLOSING_SOON'])
        
        # Search
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(sector__icontains=search)
            )
        
        # Filter by sector
        sector = self.request.query_params.get('sector', None)
        if sector:
            queryset = queryset.filter(sector=sector)
        
        # Filter by investment type
        investment_type = self.request.query_params.get('investment_type', None)
        if investment_type:
            queryset = queryset.filter(investment_type=investment_type)
        
        # Filter by status
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Featured first
        queryset = queryset.order_by('-is_featured', '-created_at')
        
        # Only the detail view renders documents
        if self.action == 'retrieve':
            return queryset.prefetch_related('documents', 'tags')
        return queryset.prefetch_related('tags')
    
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
