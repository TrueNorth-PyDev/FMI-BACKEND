"""
Admin System / Audit views — platform-wide activity log, sessions, audit trail.
"""
from rest_framework.views import APIView
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from admin_api.permissions import IsAdminUser
from admin_api.serializers import AdminUserActivitySerializer
from accounts.models import UserSession, UserActivity
from accounts.session_utils import revoke_sessions
from admin_api.utils import paginate


class AdminActivityLogView(APIView):
    """Platform-wide activity log (all users, paginated, filterable)."""
    permission_classes = [IsAdminUser]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        qs = UserActivity.objects.select_related('user').order_by('-created_at')

        # Filters
        activity_type = request.query_params.get('activity_type')
        if activity_type:
            qs = qs.filter(activity_type=activity_type)
        user_id = request.query_params.get('user')
        if user_id:
            qs = qs.filter(user_id=user_id)
        email = request.query_params.get('email')
        if email:
            qs = qs.filter(user__email__icontains=email)

        items, meta = paginate(request, qs)
        serializer = AdminUserActivitySerializer(items, many=True)
        return Response({**meta, 'results': serializer.data})


class AdminSessionListView(APIView):
    """All active sessions across all users."""
    permission_classes = [IsAdminUser]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        qs = UserSession.objects.select_related('user').order_by('-last_activity')
        email = request.query_params.get('email')
        if email:
            qs = qs.filter(user__email__icontains=email)
        is_current = request.query_params.get('is_current')
        if is_current is not None:
            qs = qs.filter(is_current=is_current.lower() == 'true')

        items, meta = paginate(request, qs)
        data = list(items.values(
            'id', 'device_name', 'location', 'ip_address',
            'is_current', 'created_at', 'last_activity',
            'user__email', 'user__id',
        ))
        return Response({**meta, 'results': data})


class AdminSessionDetailView(APIView):
    """Terminate any session by ID."""
    permission_classes = [IsAdminUser]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def delete(self, request, session_id):
        session = get_object_or_404(UserSession.objects.select_related('user'), pk=session_id)
        user_email = session.user.email
        revoke_sessions(UserSession.objects.filter(pk=session.pk))
        return Response({'detail': f'Session for {user_email} terminated.'}, status=status.HTTP_200_OK)


class AdminAuditLogView(APIView):
    """
    Combined security audit trail:
    login events, password changes, lockouts, admin actions.
    """
    permission_classes = [IsAdminUser]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        SECURITY_TYPES = ['LOGIN', 'LOGOUT', 'PASSWORD_CHANGE', '2FA_ENABLED', '2FA_DISABLED']
        qs = UserActivity.objects.filter(
            activity_type__in=SECURITY_TYPES
        ).select_related('user').order_by('-created_at')

        email = request.query_params.get('email')
        if email:
            qs = qs.filter(user__email__icontains=email)
        activity_type = request.query_params.get('activity_type')
        if activity_type:
            qs = qs.filter(activity_type=activity_type)

        items, meta = paginate(request, qs)
        serializer = AdminUserActivitySerializer(items, many=True)
        return Response({**meta, 'results': serializer.data})
