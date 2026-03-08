"""
Admin Investment Management views.
"""
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from admin_api.permissions import IsAdminUser
from admin_api.serializers import (
    AdminInvestmentListSerializer,
    AdminInvestmentDetailSerializer,
    AdminInvestmentUpdateSerializer,
    AdminCapitalActivitySerializer,
)
from investments.models import Investment, CapitalActivity


class AdminInvestmentViewSet(ModelViewSet):
    """
    Admin read/update/delete for investments across all users.
    """
    permission_classes = [IsAdminUser]
    http_method_names = ['get', 'patch', 'post', 'delete', 'head', 'options']

    def get_queryset(self):
        qs = Investment.objects.select_related('user', 'opportunity').order_by('-created_at')
        user_id = self.request.query_params.get('user')
        if user_id:
            qs = qs.filter(user_id=user_id)
        sector = self.request.query_params.get('sector')
        if sector:
            qs = qs.filter(sector=sector)
        inv_status = self.request.query_params.get('status')
        if inv_status:
            qs = qs.filter(status=inv_status)
        opportunity_id = self.request.query_params.get('opportunity')
        if opportunity_id:
            qs = qs.filter(opportunity_id=opportunity_id)
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return AdminInvestmentListSerializer
        if self.action == 'partial_update':
            return AdminInvestmentUpdateSerializer
        return AdminInvestmentDetailSerializer

    # ---- Action: capital activities for an investment ----
    @action(detail=True, methods=['get', 'post'], url_path='capital-activities')
    def capital_activities(self, request, pk=None):
        investment = self.get_object()
        if request.method == 'GET':
            qs = CapitalActivity.objects.filter(investment=investment).order_by('-date')
            serializer = AdminCapitalActivitySerializer(qs, many=True)
            return Response({'count': qs.count(), 'results': serializer.data})

        # POST — manually record a capital activity
        data = request.data.copy()
        data['investment'] = investment.pk
        serializer = AdminCapitalActivitySerializer(data=data)
        if serializer.is_valid():
            serializer.save(investment=investment)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
