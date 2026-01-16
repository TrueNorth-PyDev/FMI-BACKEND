"""
Additional views for ownership transfers.
Handles transfer CRUD operations, status management, and filtering.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta

from .models import OwnershipTransfer, TransferDocument
from .serializers import (
    OwnershipTransferListSerializer,
    OwnershipTransferDetailSerializer,
    OwnershipTransferCreateSerializer,
    TransferDocumentSerializer,
)
import logging

logger = logging.getLogger('investments')


class OwnershipTransferViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing ownership transfers.
    
    Provides CRUD operations and status management for transfers.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return transfers for the current user (both outgoing and incoming)."""
        user = self.request.user
        queryset = OwnershipTransfer.objects.filter(
            models.Q(from_user=user) | models.Q(to_user=user)
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
    
    def perform_update(self, serializer):
        """Update transfer (only drafts can be updated)."""
        transfer = self.get_object()
        
        # Only allow updates to drafts
        if transfer.status != 'DRAFT':
            raise serializers.ValidationError("Only draft transfers can be updated.")
        
        # Only owner can update
        if transfer.from_user != self.request.user:
            raise serializers.ValidationError("You can only update your own transfers.")
        
        transfer = serializer.save()
        logger.info(f"Transfer updated: {transfer.id}")
    
    def perform_destroy(self, instance):
        """Cancel transfer (soft delete by changing status)."""
        # Only owner can cancel
        if instance.from_user != self.request.user:
            raise serializers.ValidationError("You can only cancel your own transfers.")
        
        # Can only cancel pending or draft transfers
        if instance.status not in ['DRAFT', 'PENDING']:
            raise serializers.ValidationError("Can only cancel draft or pending transfers.")
        
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
        user = request.user
        transfers = OwnershipTransfer.objects.filter(
            models.Q(from_user=user) | models.Q(to_user=user),
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
        user = request.user
        transfers = OwnershipTransfer.objects.filter(
            models.Q(from_user=user) | models.Q(to_user=user),
            status__in=['COMPLETED', 'CANCELLED', 'REJECTED']
        ).select_related('investment', 'from_user', 'to_user').order_by('-completion_date', '-created_at')
        
        serializer = OwnershipTransferListSerializer(transfers, many=True, context={'request': request})
        
        return Response({
            'transfer_history': serializer.data,
            'total_count': transfers.count()
        })


# Import models.Q for queryset filtering
from django.db import models
