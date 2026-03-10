"""
Admin views for Investor Profiles and Marketplace Investor Interests.
All endpoints require is_staff=True via IsAdminUser permission.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404

from accounts.models import InvestorProfile
from marketplace.models import InvestorInterest
from .permissions import IsAdminUser
from .serializers import (
    AdminInvestorProfileSerializer,
    AdminInvestorProfileUpdateSerializer,
    AdminInvestorInterestSerializer,
    AdminInvestorInterestUpdateSerializer,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Investor Profiles
# ---------------------------------------------------------------------------

class AdminInvestorProfileViewSet(viewsets.ModelViewSet):
    """
    Admin CRUD for InvestorProfile records.

    Every registered user has exactly one InvestorProfile created automatically
    on signup (via signal). The admin can read and update any profile field
    (bio, display name, sectors, visibility) and can manually link a profile
    to a different user if needed.

    Endpoints:
        GET    /api/admin/investor-profiles/          – paginated list
        GET    /api/admin/investor-profiles/{id}/     – detail
        PATCH  /api/admin/investor-profiles/{id}/     – partial update
        GET    /api/admin/investor-profiles/by-user/{user_id}/  – lookup by user
    """
    permission_classes = [IsAdminUser]
    http_method_names = ['get', 'patch', 'post', 'head', 'options']

    def get_queryset(self):
        qs = InvestorProfile.objects.select_related('user').order_by('-created_at')

        # Filters
        user_id = self.request.query_params.get('user_id')
        is_public = self.request.query_params.get('is_public')
        investor_category = self.request.query_params.get('investor_category')
        search = self.request.query_params.get('search')

        if user_id:
            qs = qs.filter(user_id=user_id)
        if is_public is not None:
            qs = qs.filter(is_public=(is_public.lower() == 'true'))
        if investor_category:
            qs = qs.filter(investor_category=investor_category)
        if search:
            qs = qs.filter(
                display_name__icontains=search
            ) | qs.filter(user__email__icontains=search)

        return qs

    def get_serializer_class(self):
        if self.request.method in ('PATCH', 'POST'):
            return AdminInvestorProfileUpdateSerializer
        return AdminInvestorProfileSerializer

    # ---- Action: Lookup by user pk ----
    @action(detail=False, methods=['get'], url_path=r'by-user/(?P<user_id>\d+)')
    def by_user(self, request, user_id=None):
        """
        GET /api/admin/investor-profiles/by-user/{user_id}/
        Returns the investor profile for a given user.
        """
        profile = get_object_or_404(InvestorProfile, user_id=user_id)
        serializer = AdminInvestorProfileSerializer(profile, context={'request': request})
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Marketplace Investor Interests
# ---------------------------------------------------------------------------

class AdminInvestorInterestViewSet(viewsets.ModelViewSet):
    """
    Admin CRUD for InvestorInterest (opportunity pledges).

    These are the "soft" investor commitments to a marketplace opportunity
    before they become real investments. Admin can:
    - List all interests across all users
    - Filter by user, opportunity, status
    - Update status (PENDING → CONVERTED / CANCELLED) or amount
    - Delete spurious/test interests

    Endpoints:
        GET    /api/admin/investor-interests/           – paginated list
        POST   /api/admin/investor-interests/           – create a new interest on behalf of a user
        GET    /api/admin/investor-interests/{id}/      – detail
        PATCH  /api/admin/investor-interests/{id}/      – update status / amount
        DELETE /api/admin/investor-interests/{id}/      – remove interest

    Actions:
        POST  /api/admin/investor-interests/{id}/convert/   – force status to CONVERTED
        POST  /api/admin/investor-interests/{id}/cancel/    – force status to CANCELLED
    """
    permission_classes = [IsAdminUser]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        qs = InvestorInterest.objects.select_related('user', 'opportunity').order_by('-created_at')

        user_id = self.request.query_params.get('user_id')
        opportunity_id = self.request.query_params.get('opportunity_id')
        status_filter = self.request.query_params.get('status')
        search = self.request.query_params.get('search')

        if user_id:
            qs = qs.filter(user_id=user_id)
        if opportunity_id:
            qs = qs.filter(opportunity_id=opportunity_id)
        if status_filter:
            qs = qs.filter(status=status_filter.upper())
        if search:
            qs = qs.filter(user__email__icontains=search) | qs.filter(
                opportunity__title__icontains=search
            )
        return qs

    def get_serializer_class(self):
        if self.request.method in ('PATCH', 'POST') and self.action != 'create':
            return AdminInvestorInterestUpdateSerializer
        return AdminInvestorInterestSerializer

    # ---- Action: convert ----
    @action(detail=True, methods=['post'], url_path='convert')
    def convert(self, request, pk=None):
        """Force-convert a PENDING interest to CONVERTED (creates investment)."""
        interest = self.get_object()
        if interest.status == 'CONVERTED':
            return Response(
                {'detail': 'Already converted.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        interest.status = 'CONVERTED'
        interest.save(update_fields=['status'])
        return Response(
            AdminInvestorInterestSerializer(interest, context={'request': request}).data,
            status=status.HTTP_200_OK,
        )

    # ---- Action: cancel ----
    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel(self, request, pk=None):
        """Cancel a PENDING interest."""
        interest = self.get_object()
        if interest.status != 'PENDING':
            return Response(
                {'detail': f'Cannot cancel interest with status {interest.status}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        interest.status = 'CANCELLED'
        interest.save(update_fields=['status'])
        return Response(
            AdminInvestorInterestSerializer(interest, context={'request': request}).data,
            status=status.HTTP_200_OK,
        )
