"""
Admin User Management views.
"""
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404

from admin_api.permissions import IsAdminUser
from admin_api.serializers import (
    AdminUserListSerializer,
    AdminUserDetailSerializer,
    AdminUserUpdateSerializer,
    AdminUserSessionSerializer,
    AdminUserActivitySerializer,
)
from accounts.models import UserSession, UserActivity
from accounts.session_utils import revoke_sessions
from admin_api.utils import paginate
from django.db.models import Count, Q

User = get_user_model()


# Actions that change a staff/superuser account, or grant/remove staff rights,
# are reserved for superusers so a staff member can't escalate or lock out others.
PRIVILEGED_ACTIONS = {'partial_update', 'destroy', 'suspend', 'unsuspend', 'unlock',
                      'terminate_session', 'terminate_all_sessions'}


class AdminUserViewSet(ModelViewSet):
    """
    Full CRUD + admin actions for user accounts.
    """
    permission_classes = [IsAdminUser]
    http_method_names = ['get', 'patch', 'post', 'delete', 'head', 'options']

    def get_object(self):
        user = super().get_object()
        actor = self.request.user
        if actor.is_superuser or user == actor:
            return user
        if self.action in ('make_staff', 'remove_staff'):
            raise PermissionDenied('Only superusers can grant or remove staff rights.')
        if self.action in PRIVILEGED_ACTIONS and (user.is_staff or user.is_superuser):
            raise PermissionDenied('Only superusers can modify staff accounts.')
        return user

    def get_queryset(self):
        qs = User.objects.annotate(investment_count=Count('investments')).order_by('-created_at')
        # Filters
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == 'true')
        is_verified = self.request.query_params.get('is_email_verified')
        if is_verified is not None:
            qs = qs.filter(is_email_verified=is_verified.lower() == 'true')
        investor_type = self.request.query_params.get('investor_type')
        if investor_type:
            qs = qs.filter(investor_type=investor_type)
        is_staff = self.request.query_params.get('is_staff')
        if is_staff is not None:
            qs = qs.filter(is_staff=is_staff.lower() == 'true')
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return AdminUserListSerializer
        if self.action in ['partial_update']:
            return AdminUserUpdateSerializer
        return AdminUserDetailSerializer

    def create(self, request, *args, **kwargs):
        # Accounts are created through registration, which sets a password and
        # sends the verification email.
        return Response({'detail': 'Users sign up via /api/accounts/register/.'},
                        status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def perform_update(self, serializer):
        if 'is_staff' in serializer.validated_data and not self.request.user.is_superuser:
            raise PermissionDenied('Only superusers can grant or remove staff rights.')
        if serializer.instance == self.request.user:
            for field in ('is_active', 'is_staff'):
                if field in serializer.validated_data and not serializer.validated_data[field]:
                    raise ValidationError({field: 'You cannot remove this from your own account.'})
        serializer.save()

    def perform_destroy(self, instance):
        if instance == self.request.user:
            raise ValidationError('You cannot delete your own account.')
        instance.delete()

    # ---- Action: verify email manually ----
    @action(detail=True, methods=['post'], url_path='verify')
    def verify(self, request, pk=None):
        user = self.get_object()
        user.is_email_verified = True
        user.save(update_fields=['is_email_verified'])
        return Response({'detail': f'{user.email} email verified successfully.'})

    # ---- Action: suspend user ----
    @action(detail=True, methods=['post'], url_path='suspend')
    def suspend(self, request, pk=None):
        user = self.get_object()
        if user == request.user:
            return Response({'detail': 'You cannot suspend your own account.'},
                            status=status.HTTP_400_BAD_REQUEST)
        user.is_active = False
        user.save(update_fields=['is_active'])
        revoke_sessions(UserSession.objects.filter(user=user))
        UserActivity.log_activity(
            user=user,
            activity_type='PROFILE_UPDATE',
            description=f'Account suspended by admin {request.user.email}',
        )
        return Response({'detail': f'{user.email} has been suspended.'})

    # ---- Action: unsuspend (reactivate) user ----
    @action(detail=True, methods=['post'], url_path='unsuspend')
    def unsuspend(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=['is_active'])
        UserActivity.log_activity(
            user=user,
            activity_type='PROFILE_UPDATE',
            description=f'Account reactivated by admin {request.user.email}',
        )
        return Response({'detail': f'{user.email} has been reactivated.'})

    # ---- Action: unlock account ----
    @action(detail=True, methods=['post'], url_path='unlock')
    def unlock(self, request, pk=None):
        user = self.get_object()
        user.failed_login_attempts = 0
        user.account_locked_until = None
        user.save(update_fields=['failed_login_attempts', 'account_locked_until'])
        return Response({'detail': f'{user.email} account lockout cleared.'})

    # ---- Action: make staff ----
    @action(detail=True, methods=['post'], url_path='make-staff')
    def make_staff(self, request, pk=None):
        user = self.get_object()
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        return Response({'detail': f'{user.email} is now a staff member.'})

    # ---- Action: remove staff ----
    @action(detail=True, methods=['post'], url_path='remove-staff')
    def remove_staff(self, request, pk=None):
        user = self.get_object()
        if user == request.user:
            return Response({'detail': 'You cannot remove your own staff status.'},
                            status=status.HTTP_400_BAD_REQUEST)
        user.is_staff = False
        user.save(update_fields=['is_staff'])
        return Response({'detail': f'{user.email} staff status removed.'})

    # ---- Action: user sessions ----
    @action(detail=True, methods=['get'], url_path='sessions')
    def sessions(self, request, pk=None):
        user = self.get_object()
        qs = UserSession.objects.filter(user=user).order_by('-last_activity')
        serializer = AdminUserSessionSerializer(qs, many=True)
        return Response(serializer.data)

    # ---- Action: terminate specific session ----
    @action(detail=True, methods=['delete'], url_path=r'sessions/(?P<session_id>\d+)')
    def terminate_session(self, request, pk=None, session_id=None):
        user = self.get_object()
        get_object_or_404(UserSession, pk=session_id, user=user)
        revoke_sessions(UserSession.objects.filter(pk=session_id))
        return Response({'detail': 'Session terminated.'}, status=status.HTTP_200_OK)

    # ---- Action: terminate all sessions for user ----
    @action(detail=True, methods=['delete'], url_path='terminate-sessions')
    def terminate_all_sessions(self, request, pk=None):
        user = self.get_object()
        count = revoke_sessions(UserSession.objects.filter(user=user))
        return Response({'detail': f'{count} session(s) terminated.'})

    # ---- Action: activity log ----
    @action(detail=True, methods=['get'], url_path='activity')
    def activity(self, request, pk=None):
        user = self.get_object()
        qs = UserActivity.objects.filter(user=user).order_by('-created_at')
        items, meta = paginate(request, qs, default_page_size=20)
        serializer = AdminUserActivitySerializer(items, many=True)
        return Response({**meta, 'results': serializer.data})
