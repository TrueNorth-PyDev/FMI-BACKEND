"""
Admin Marketplace Opportunity Management views.
"""
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404

from admin_api.permissions import IsAdminUser
from admin_api.serializers import (
    AdminOpportunityListSerializer,
    AdminOpportunityDetailSerializer,
    AdminOpportunityWriteSerializer,
    AdminOpportunityDocumentSerializer,
    AdminInvestorInterestSerializer,
)
from marketplace.models import MarketplaceOpportunity, OpportunityDocument, InvestorInterest
from investments.models import Investment


class AdminOpportunityViewSet(ModelViewSet):
    """
    Admin full CRUD + lifecycle actions on marketplace opportunities.
    """
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        qs = MarketplaceOpportunity.objects.all().order_by('-created_at')
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(title__icontains=search)
        sector = self.request.query_params.get('sector')
        if sector:
            qs = qs.filter(sector=sector)
        opp_status = self.request.query_params.get('status')
        if opp_status:
            qs = qs.filter(status=opp_status)
        is_featured = self.request.query_params.get('is_featured')
        if is_featured is not None:
            qs = qs.filter(is_featured=is_featured.lower() == 'true')
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return AdminOpportunityListSerializer
        if self.action in ['create', 'update', 'partial_update']:
            return AdminOpportunityWriteSerializer
        return AdminOpportunityDetailSerializer

    # ---- Action: publish (set ACTIVE) ----
    @action(detail=True, methods=['post'], url_path='publish')
    def publish(self, request, pk=None):
        opp = self.get_object()
        if opp.status == 'CLOSED':
            return Response({'detail': 'Cannot publish a closed opportunity.'},
                            status=status.HTTP_400_BAD_REQUEST)
        opp.status = 'ACTIVE'
        opp.save(update_fields=['status'])
        return Response({'detail': f'"{opp.title}" is now ACTIVE.', 'status': opp.status})

    # ---- Action: close ----
    @action(detail=True, methods=['post'], url_path='close')
    def close(self, request, pk=None):
        opp = self.get_object()
        opp.status = 'CLOSED'
        opp.save(update_fields=['status'])
        return Response({'detail': f'"{opp.title}" has been CLOSED.', 'status': opp.status})

    # ---- Action: mark as new ----
    @action(detail=True, methods=['post'], url_path='mark-new')
    def mark_new(self, request, pk=None):
        opp = self.get_object()
        opp.status = 'NEW'
        opp.save(update_fields=['status'])
        return Response({'detail': f'"{opp.title}" status set to NEW.', 'status': opp.status})

    # ---- Action: toggle featured ----
    @action(detail=True, methods=['post'], url_path='feature')
    def feature(self, request, pk=None):
        opp = self.get_object()
        opp.is_featured = not opp.is_featured
        opp.save(update_fields=['is_featured'])
        state = 'featured' if opp.is_featured else 'unfeatured'
        return Response({'detail': f'"{opp.title}" is now {state}.', 'is_featured': opp.is_featured})

    # ---- Action: list investors in this opportunity ----
    @action(detail=True, methods=['get'], url_path='investors')
    def investors(self, request, pk=None):
        opp = self.get_object()
        interests = InvestorInterest.objects.filter(
            opportunity=opp
        ).select_related('user').order_by('-created_at')
        serializer = AdminInvestorInterestSerializer(interests, many=True)
        return Response({
            'count': interests.count(),
            'results': serializer.data,
        })

    # ---- Action: list investments linked to this opportunity ----
    @action(detail=True, methods=['get'], url_path='investments')
    def investments(self, request, pk=None):
        opp = self.get_object()
        invs = opp.investments.select_related('user').order_by('-created_at')
        from admin_api.serializers import AdminInvestmentListSerializer
        serializer = AdminInvestmentListSerializer(invs, many=True)
        return Response({'count': invs.count(), 'results': serializer.data})

    # ---- Action: upload document ----
    @action(detail=True, methods=['post'], url_path='documents')
    def upload_document(self, request, pk=None):
        opp = self.get_object()
        data = request.data.copy()
        data['opportunity'] = opp.pk
        serializer = AdminOpportunityDocumentSerializer(data=data)
        if serializer.is_valid():
            serializer.save(opportunity=opp)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # ---- Action: delete document ----
    @action(detail=True, methods=['delete'], url_path=r'documents/(?P<doc_id>\d+)')
    def delete_document(self, request, pk=None, doc_id=None):
        opp = self.get_object()
        doc = get_object_or_404(OpportunityDocument, pk=doc_id, opportunity=opp)
        doc.delete()
        return Response({'detail': 'Document deleted.'}, status=status.HTTP_200_OK)
