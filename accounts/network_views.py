"""
Investor network views.
Handles investor directory, profiles, and connections.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Sum, Count
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter

from .models import InvestorProfile, InvestorConnection, User
from .serializers import (
    InvestorProfileSerializer,
    InvestorListSerializer,
    InvestorConnectionSerializer,
)
from investments.models import Investment
import logging

logger = logging.getLogger('accounts')


class InvestorNetworkViewSet(viewsets.ViewSet):
    """
    ViewSet for investor network functionality.
    
    Provides endpoints for investor directory, profiles, and connections.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = InvestorListSerializer  # Default serializer
    
    @action(detail=False, methods=['get'])
    def directory(self, request):
        """
        Get investor directory with search and filters.
        """
        # Base queryset - only public profiles
        queryset = InvestorProfile.objects.filter(is_public=True).select_related('user')
        
        # Search by name, bio, or sectors
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(display_name__icontains=search) |
                Q(bio__icontains=search) |
                Q(investment_philosophy__icontains=search)
            )
        
        # Filter by sector
        sector = request.query_params.get('sector')
        if sector:
            queryset = queryset.filter(preferred_sectors__contains=[sector])
        
        # Filter by min investment
        min_investment = request.query_params.get('min_investment')
        if min_investment:
            queryset = queryset.filter(min_investment__gte=min_investment)
        
        # Filter by location
        location = request.query_params.get('location')
        if location:
            queryset = queryset.filter(
                Q(location_city__icontains=location) |
                Q(location_country__icontains=location)
            )
        
        # Pagination
        page_size = int(request.query_params.get('page_size', 20))
        page = int(request.query_params.get('page', 1))
        start = (page - 1) * page_size
        end = start + page_size
        
        total_count = queryset.count()
        investors = queryset[start:end]
        
        serializer = InvestorListSerializer(investors, many=True, context={'request': request})
        
        return Response({
            'investors': serializer.data,
            'total_count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size
        })
    
    @action(detail=True, methods=['get'])
    def profile(self, request, pk=None):
        """
        Get detailed investor profile with portfolio overview and recent investments.
        """
        investor_profile = get_object_or_404(InvestorProfile, pk=pk, is_public=True)
        
        # Profile data
        profile_serializer = InvestorProfileSerializer(investor_profile)
        
        # Portfolio overview
        portfolio_overview = self.calculate_portfolio_overview(investor_profile.user)
        
        # Recent investments
        recent_investments = self.get_recent_investments(investor_profile.user)
        
        # Connection status
        connection_status = self.get_connection_status(request.user, investor_profile.user)
        
        return Response({
            'profile': profile_serializer.data,
            'portfolio_overview': portfolio_overview,
            'recent_investments': recent_investments,
            'connection_status': connection_status
        })
    
    @action(detail=False, methods=['post'])
    def connect(self, request):
        """
        Send connection request to another investor.
        """
        to_investor_id = request.data.get('to_investor')
        message = request.data.get('message', '')
        
        if not to_investor_id:
            return Response(
                {"error": "to_investor is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get target investor
        try:
            to_investor = User.objects.get(id=to_investor_id)
        except User.DoesNotExist:
            return Response(
                {"error": "Investor not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Cannot connect to self
        if to_investor == request.user:
            return Response(
                {"error": "Cannot connect to yourself."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if connection already exists
        existing_connection = InvestorConnection.objects.filter(
            Q(from_investor=request.user, to_investor=to_investor) |
            Q(from_investor=to_investor, to_investor=request.user)
        ).first()
        
        if existing_connection:
            return Response(
                {"error": f"Connection already exists with status: {existing_connection.status}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if target investor accepts connections
        try:
            target_profile = InvestorProfile.objects.get(user=to_investor)
            if not target_profile.is_accepting_connections:
                return Response(
                    {"error": "This investor is not accepting connections."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except InvestorProfile.DoesNotExist:
            pass
        
        # Create connection
        connection = InvestorConnection.objects.create(
            from_investor=request.user,
            to_investor=to_investor,
            message=message
        )
        
        serializer = InvestorConnectionSerializer(connection)
        logger.info(f"Connection request sent from {request.user.email} to {to_investor.email}")
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['get'])
    def connections(self, request):
        """
        Get user's connections.
        """
        user = request.user
        status_filter = request.query_params.get('status', 'ACCEPTED')
        
        # Get connections where user is either sender or receiver
        connections = InvestorConnection.objects.filter(
            Q(from_investor=user) | Q(to_investor=user),
            status=status_filter
        ).select_related('from_investor', 'to_investor')
        
        serializer = InvestorConnectionSerializer(connections, many=True)
        
        return Response({
            'connections': serializer.data,
            'total_count': connections.count()
        })
    
    @action(detail=True, methods=['patch'])
    def update_connection(self, request, pk=None):
        """
        Accept or reject a connection request.
        """
        connection = get_object_or_404(InvestorConnection, pk=pk, to_investor=request.user)
        
        new_status = request.data.get('status')
        
        if new_status not in ['ACCEPTED', 'REJECTED']:
            return Response(
                {"error": "Status must be ACCEPTED or REJECTED."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        connection.status = new_status
        connection.save()
        
        serializer = InvestorConnectionSerializer(connection)
        logger.info(f"Connection {pk} updated to {new_status} by {request.user.email}")
        
        return Response(serializer.data)
    
    @action(detail=False, methods=['get', 'patch'])
    def my_profile(self, request):
        """
        Get or update own investor profile.
        """
        profile, created = InvestorProfile.objects.get_or_create(user=request.user)
        
        if request.method == 'GET':
            serializer = InvestorProfileSerializer(profile)
            return Response(serializer.data)
        
        elif request.method == 'PATCH':
            serializer = InvestorProfileSerializer(profile, data=request.data, partial=True)
            
            if serializer.is_valid():
                serializer.save()
                logger.info(f"Investor profile updated for {request.user.email}")
                return Response(serializer.data)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def calculate_portfolio_overview(self, user):
        """Calculate portfolio overview with sector allocation."""
        investments = Investment.objects.filter(
            user=user,
            status__in=['ACTIVE', 'UNDERPERFORMING']
        )
        
        total_value = investments.aggregate(total=Sum('current_value'))['total'] or 0
        
        # Calculate sector allocation
        sector_allocation = {}
        for investment in investments:
            sector = investment.get_sector_display()
            if sector not in sector_allocation:
                sector_allocation[sector] = 0
            sector_allocation[sector] += float(investment.current_value)
        
        # Convert to percentages
        sector_percentages = {}
        if total_value > 0:
            for sector, value in sector_allocation.items():
                sector_percentages[sector] = round((value / float(total_value)) * 100, 1)
        
        return {
            'total_value': float(total_value),
            'sector_allocation': sector_percentages,
            'investments_count': investments.count()
        }
    
    def get_recent_investments(self, user, limit=10):
        """Get recent investments with performance."""
        investments = Investment.objects.filter(
            user=user,
            status__in=['ACTIVE', 'UNDERPERFORMING']
        ).order_by('-investment_date')[:limit]
        
        recent = []
        for inv in investments:
            recent.append({
                'name': inv.name,
                'sector': inv.get_sector_display(),
                'type': inv.get_investment_type_display(),
                'invested': float(inv.total_invested),
                'current_value': float(inv.current_value),
                'performance': float(inv.unrealized_gain_percentage),
                'date': inv.investment_date
            })
        
        return recent
    
    def get_connection_status(self, current_user, target_user):
        """Get connection status between two users."""
        if current_user == target_user:
            return 'self'
        
        connection = InvestorConnection.objects.filter(
            Q(from_investor=current_user, to_investor=target_user) |
            Q(from_investor=target_user, to_investor=current_user)
        ).first()
        
        if connection:
            return connection.status.lower()
        
        return None
