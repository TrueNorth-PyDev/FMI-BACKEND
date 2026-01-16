"""
Account management views.
Handles profile, security, notifications, documents, and activity management.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.contrib.auth import update_session_auth_hash
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse

from .models import User, UserNotificationPreference, UserDocument, UserActivity, UserSession
from .serializers import (
    UserProfileSerializer,
    ChangePasswordSerializer,
    UserNotificationPreferenceSerializer,
    UserDocumentSerializer,
    UserActivitySerializer,
    UserSessionSerializer,
)
import logging

logger = logging.getLogger('accounts')


class AccountManagementViewSet(viewsets.ViewSet):
    """
    ViewSet for comprehensive account management.
    
    Provides endpoints for profile, security, notifications, documents, and activity.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserProfileSerializer  # Default serializer
    
    @action(detail=False, methods=['get', 'patch'])
    def profile(self, request):
        """
        Get or update user profile.
        """
        user = request.user
        
        if request.method == 'GET':
            serializer = UserProfileSerializer(user, context={'request': request})
            return Response(serializer.data)
        
        elif request.method == 'PATCH':
            serializer = UserProfileSerializer(user, data=request.data, partial=True, context={'request': request})
            
            if serializer.is_valid():
                serializer.save()
                
                # Log activity
                UserActivity.log_activity(
                    user=user,
                    activity_type='PROFILE_UPDATE',
                    description='Profile information updated',
                    ip_address=self.get_client_ip(request)
                )
                
                logger.info(f"Profile updated for {user.email}")
                return Response(serializer.data)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload_photo(self, request):
        """
        Upload profile photo.
        """
        user = request.user
        
        if 'profile_photo' not in request.FILES:
            return Response(
                {"error": "No photo file provided."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user.profile_photo = request.FILES['profile_photo']
        user.save()
        
        # Log activity
        UserActivity.log_activity(
            user=user,
            activity_type='PROFILE_UPDATE',
            description='Profile photo updated',
            ip_address=self.get_client_ip(request)
        )
        
        serializer = UserProfileSerializer(user, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def change_password(self, request):
        """
        Change user password.
        """
        user = request.user
        serializer = ChangePasswordSerializer(data=request.data)
        
        if serializer.is_valid():
            # Verify current password
            if not user.check_password(serializer.validated_data['current_password']):
                return Response(
                    {"current_password": "Current password is incorrect."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Set new password
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            
            # Update session to prevent logout
            update_session_auth_hash(request, user)
            
            # Log activity
            UserActivity.log_activity(
                user=user,
                activity_type='PASSWORD_CHANGE',
                description='Password changed successfully',
                ip_address=self.get_client_ip(request)
            )
            
            logger.info(f"Password changed for {user.email}")
            return Response({"message": "Password updated successfully."})
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def sessions(self, request):
        """
        Get active user sessions.
        """
        user = request.user
        sessions = UserSession.objects.filter(user=user).order_by('-last_activity')[:10]
        serializer = UserSessionSerializer(sessions, many=True)
        
        return Response({
            'sessions': serializer.data,
            'total_count': sessions.count()
        })
    
    @action(detail=False, methods=['delete'])
    def revoke_session(self, request):
        """
        Revoke a specific session.
        """
        session_id = request.data.get('session_id')
        
        if not session_id:
            return Response(
                {"error": "Session ID is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            session = UserSession.objects.get(id=session_id, user=request.user)
            
            if session.is_current:
                return Response(
                    {"error": "Cannot revoke current session."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            session.delete()
            
            logger.info(f"Session {session_id} revoked for {request.user.email}")
            return Response({"message": "Session revoked successfully."})
        
        except UserSession.DoesNotExist:
            return Response(
                {"error": "Session not found."},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['get', 'patch'])
    def notification_preferences(self, request):
        """
        Get or update notification preferences.
        """
        user = request.user
        
        # Get or create preferences
        preferences, created = UserNotificationPreference.objects.get_or_create(user=user)
        
        if request.method == 'GET':
            serializer = UserNotificationPreferenceSerializer(preferences)
            return Response(serializer.data)
        
        elif request.method == 'PATCH':
            serializer = UserNotificationPreferenceSerializer(preferences, data=request.data, partial=True)
            
            if serializer.is_valid():
                serializer.save()
                logger.info(f"Notification preferences updated for {user.email}")
                return Response(serializer.data)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get', 'post'])
    def documents(self, request):
        """
        List or upload user documents.
        """
        user = request.user
        
        if request.method == 'GET':
            documents = UserDocument.objects.filter(user=user).order_by('-uploaded_at')
            serializer = UserDocumentSerializer(documents, many=True, context={'request': request})
            
            return Response({
                'documents': serializer.data,
                'total_count': documents.count()
            })
        
        elif request.method == 'POST':
            data = request.data.copy()
            
            # Get file size
            if 'file' in request.FILES:
                data['file_size'] = request.FILES['file'].size
            
            serializer = UserDocumentSerializer(data=data, context={'request': request})
            
            if serializer.is_valid():
                document = serializer.save(user=user)
                
                # Log activity
                UserActivity.log_activity(
                    user=user,
                    activity_type='DOCUMENT_UPLOADED',
                    description=f"{document.title} uploaded",
                    metadata={'document_id': document.id, 'document_type': document.document_type},
                    ip_address=self.get_client_ip(request)
                )
                
                logger.info(f"Document uploaded by {user.email}: {document.title}")
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def document_download(self, request):
        """
        Download a specific document.
        """
        document_id = request.query_params.get('id')
        
        if not document_id:
            return Response(
                {"error": "Document ID is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            document = UserDocument.objects.get(id=document_id, user=request.user)
            
            from django.http import FileResponse
            return FileResponse(document.file.open('rb'), as_attachment=True, filename=document.title)
        
        except UserDocument.DoesNotExist:
            return Response(
                {"error": "Document not found."},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['delete'])
    def delete_document(self, request):
        """
        Delete a specific document.
        """
        document_id = request.data.get('id')
        
        if not document_id:
            return Response(
                {"error": "Document ID is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            document = UserDocument.objects.get(id=document_id, user=request.user)
            document.delete()
            
            logger.info(f"Document deleted by {request.user.email}: {document.title}")
            return Response({"message": "Document deleted successfully."})
        
        except UserDocument.DoesNotExist:
            return Response(
                {"error": "Document not found."},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['get'])
    def activity(self, request):
        """
        Get user activity log.
        """
        user = request.user
        activities = UserActivity.objects.filter(user=user).order_by('-created_at')[:50]
        serializer = UserActivitySerializer(activities, many=True)
        
        return Response({
            'activities': serializer.data,
            'total_count': activities.count()
        })
    
    def get_client_ip(self, request):
        """Get client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
