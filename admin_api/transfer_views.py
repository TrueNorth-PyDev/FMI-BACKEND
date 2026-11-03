"""
Admin Ownership Transfer & Secondary Market Interest management views.
"""
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet
from django.db import transaction
from django.utils import timezone

from admin_api.permissions import IsAdminUser
from admin_api.serializers import (
    AdminTransferListSerializer,
    AdminTransferDetailSerializer,
    AdminSecondaryInterestSerializer,
)
from investments.models import OwnershipTransfer, SecondaryMarketInterest


class AdminTransferViewSet(ReadOnlyModelViewSet):
    """
    Admin read + action-based management for ownership transfers.
    """
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = OwnershipTransfer.objects.select_related(
            'investment', 'investment__opportunity', 'from_user', 'to_user'
        ).order_by('-created_at')
        t_status = self.request.query_params.get('status')
        if t_status:
            qs = qs.filter(status=t_status)
        from_user = self.request.query_params.get('from_user')
        if from_user:
            qs = qs.filter(from_user_id=from_user)
        to_user = self.request.query_params.get('to_user')
        if to_user:
            qs = qs.filter(to_user_id=to_user)
        investment = self.request.query_params.get('investment')
        if investment:
            qs = qs.filter(investment_id=investment)
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return AdminTransferListSerializer
        return AdminTransferDetailSerializer

    # ---- Action: approve ----
    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        transfer = self.get_object()
        if transfer.status != 'PENDING':
            return Response(
                {'detail': f'Cannot approve a transfer with status "{transfer.status}". Expected PENDING.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        transfer.status = 'APPROVED'
        transfer.save(update_fields=['status', 'updated_at'])
        return Response({'detail': 'Transfer approved.', 'status': transfer.status})

    # ---- Action: complete ----
    @action(detail=True, methods=['post'], url_path='complete')
    def complete(self, request, pk=None):
        transfer = self.get_object()
        if transfer.status != 'APPROVED':
            return Response(
                {'detail': f'Cannot complete a transfer with status "{transfer.status}". Expected APPROVED.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        # The handle_transfer_completion signal moves the position; if that fails
        # (e.g. no registered recipient) the ValidationError rolls this back and
        # is returned as a 400.
        with transaction.atomic():
            transfer.status = 'COMPLETED'
            transfer.save(update_fields=['status', 'updated_at'])
        return Response({'detail': 'Transfer completed.', 'status': transfer.status})

    # ---- Action: reject ----
    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        transfer = self.get_object()
        if transfer.status not in ('PENDING', 'APPROVED'):
            return Response(
                {'detail': f'Cannot reject a transfer with status "{transfer.status}".'},
                status=status.HTTP_400_BAD_REQUEST
            )
        reason = request.data.get('reason', '')
        with transaction.atomic():
            transfer.status = 'REJECTED'
            transfer.reason = reason or transfer.reason
            transfer.save(update_fields=['status', 'reason', 'updated_at'])
            # A rejected listing can no longer be bought
            SecondaryMarketInterest.objects.filter(transfer=transfer, status='PENDING').update(
                status='CANCELLED', updated_at=timezone.now()
            )
        return Response({'detail': 'Transfer rejected.', 'status': transfer.status})


class AdminSecondaryInterestViewSet(ReadOnlyModelViewSet):
    """
    Admin read + status update for secondary market buyer interests.

    PATCH {"status": "CONVERTED"} executes the purchase (seller → buyer);
    PATCH {"status": "CANCELLED"} declines it. Only PENDING interests can change.
    """
    permission_classes = [IsAdminUser]
    serializer_class = AdminSecondaryInterestSerializer
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        qs = SecondaryMarketInterest.objects.select_related(
            'transfer', 'buyer', 'transfer__investment', 'transfer__investment__opportunity'
        ).order_by('-created_at')
        s = self.request.query_params.get('status')
        if s:
            qs = qs.filter(status=s)
        buyer = self.request.query_params.get('buyer')
        if buyer:
            qs = qs.filter(buyer_id=buyer)
        return qs

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        allowed_statuses = ['CONVERTED', 'CANCELLED']
        new_status = request.data.get('status')
        if new_status not in allowed_statuses:
            return Response(
                {'detail': f'Invalid status. Choices: {allowed_statuses}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if instance.status != 'PENDING':
            return Response(
                {'detail': f'Only pending interests can be updated (this one is {instance.status}).'},
                status=status.HTTP_400_BAD_REQUEST
            )
        # CONVERTED triggers the purchase via signal; a failure rolls back the status
        with transaction.atomic():
            instance.status = new_status
            instance.save(update_fields=['status', 'updated_at'])
        instance.refresh_from_db()
        return Response(self.get_serializer(instance).data)
