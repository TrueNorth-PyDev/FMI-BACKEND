"""
Account management views.
Handles profile, security, notifications, documents, and activity management.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import serializers as drf_serializers
from django.http import FileResponse
import os

from .models import UserNotificationPreference, UserDocument, UserActivity, UserSession
from .serializers import (
    UserProfileSerializer,
    ChangePasswordSerializer,
    UserNotificationPreferenceSerializer,
    UserDocumentSerializer,
    UserActivitySerializer,
    UserSessionSerializer,
)
from .session_utils import revoke_sessions
from .authentication import current_session_id
from .utils import get_client_ip
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
                    ip_address=get_client_ip(request)
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
        
        photo = request.FILES['profile_photo']
        try:
            # Rejects anything Pillow can't open as an image
            drf_serializers.ImageField().run_validation(photo)
        except drf_serializers.ValidationError as e:
            return Response({"profile_photo": e.detail}, status=status.HTTP_400_BAD_REQUEST)
        if photo.size > 5 * 1024 * 1024:
            return Response({"profile_photo": "Image too large. Maximum size is 5MB."},
                            status=status.HTTP_400_BAD_REQUEST)
        
        old_photo = user.profile_photo.name if user.profile_photo else None
        user.profile_photo = photo
        user.save(update_fields=['profile_photo', 'updated_at'])
        if old_photo and old_photo != user.profile_photo.name:
            user.profile_photo.storage.delete(old_photo)
        
        # Log activity
        UserActivity.log_activity(
            user=user,
            activity_type='PROFILE_UPDATE',
            description='Profile photo updated',
            ip_address=get_client_ip(request)
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
            user.save(update_fields=['password', 'updated_at'])
            
            # Sign out every other device; the session making this request stays
            revoke_sessions(UserSession.objects.filter(user=user).exclude(pk=current_session_id(request)))
            
            # Log activity
            UserActivity.log_activity(
                user=user,
                activity_type='PASSWORD_CHANGE',
                description='Password changed successfully',
                ip_address=get_client_ip(request)
            )
            
            logger.info(f"Password changed for {user.email}")
            return Response({"message": "Password updated successfully. Other sessions have been signed out."})
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def sessions(self, request):
        """
        Get active user sessions.
        """
        user = request.user
        sessions = UserSession.objects.filter(user=user).order_by('-last_activity')[:10]
        serializer = UserSessionSerializer(
            sessions, many=True, context={'current_session_id': current_session_id(request)}
        )
        
        return Response({
            'sessions': serializer.data,
            'total_count': len(serializer.data)
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
        
        session = UserSession.objects.filter(id=session_id, user=request.user).first()
        if session is None:
            return Response(
                {"error": "Session not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if session.pk == current_session_id(request):
            return Response(
                {"error": "Cannot revoke current session."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Blacklists the session's refresh token so it can no longer be used
        revoke_sessions(UserSession.objects.filter(pk=session.pk))
        
        logger.info(f"Session {session_id} revoked for {request.user.email}")
        return Response({"message": "Session revoked successfully."})
    
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
            # Pass request.data straight through: QueryDict.copy() deep-copies
            # uploads and fails for files streamed to a temporary file.
            serializer = UserDocumentSerializer(data=request.data, context={'request': request})
            
            if serializer.is_valid():
                document = serializer.save(user=user, file_size=serializer.validated_data['file'].size)
                
                # Log activity
                UserActivity.log_activity(
                    user=user,
                    activity_type='DOCUMENT_UPLOADED',
                    description=f"{document.title} uploaded",
                    metadata={'document_id': document.id, 'document_type': document.document_type},
                    ip_address=get_client_ip(request)
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
        
        document = UserDocument.objects.filter(id=document_id, user=request.user).first()
        if document is None or not document.file:
            return Response(
                {"error": "Document not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            file_handle = document.file.open('rb')
        except FileNotFoundError:
            return Response({"error": "Document file is missing."}, status=status.HTTP_404_NOT_FOUND)
        
        # Keep the stored file's extension so the download opens correctly
        extension = os.path.splitext(document.file.name)[1]
        filename = document.title if document.title.endswith(extension) else f"{document.title}{extension}"
        return FileResponse(file_handle, as_attachment=True, filename=filename)
    
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
        
        document = UserDocument.objects.filter(id=document_id, user=request.user).first()
        if document is None:
            return Response(
                {"error": "Document not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        document.file.delete(save=False)
        document.delete()
        
        logger.info(f"Document deleted by {request.user.email}: {document.title}")
        return Response({"message": "Document deleted successfully."})
    
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
            'total_count': len(serializer.data)
        })
