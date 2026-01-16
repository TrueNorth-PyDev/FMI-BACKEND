"""
Views for the marketplace app.
Handles marketplace opportunity listings, details, and user actions.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.db.models import Q
from django.shortcuts import get_object_or_404

from .models import MarketplaceOpportunity, OpportunityDocument, OpportunityTag, InvestmentInterest
from .serializers import (
    MarketplaceOpportunityListSerializer,
    MarketplaceOpportunityDetailSerializer,
    InvestmentInterestSerializer,
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
        
        return queryset.prefetch_related('documents', 'tags')
    
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
        """
        opportunity = self.get_object()
        
        # Delete bookmark if exists
        deleted_count = InvestmentInterest.objects.filter(
            user=request.user,
            opportunity=opportunity,
            interest_type='BOOKMARKED'
        ).delete()[0]
        
        if deleted_count > 0:
            logger.info(
                f"Bookmark removed: {request.user.email} removed {opportunity.title} from watchlist"
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
        # Get bookmarked opportunities
        bookmarks = InvestmentInterest.objects.filter(
            user=request.user,
            interest_type='BOOKMARKED'
        ).select_related('opportunity').order_by('-created_at')
        
        # Get the opportunities
        opportunities = [bookmark.opportunity for bookmark in bookmarks]
        
        # Serialize
        serializer = MarketplaceOpportunityListSerializer(
            opportunities,
            many=True,
            context={'request': request}
        )
        
        return Response({
            'watchlist': serializer.data,
            'total_count': len(opportunities)
        })
