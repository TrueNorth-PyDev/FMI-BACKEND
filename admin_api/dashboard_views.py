"""
Admin Dashboard view — single-call platform KPIs.
"""
from rest_framework.views import APIView
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Sum, Count, Q

from admin_api.permissions import IsAdminUser
from investments.models import Investment, OwnershipTransfer
from marketplace.models import MarketplaceOpportunity
from accounts.models import UserActivity

User = get_user_model()


class AdminDashboardView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # One aggregate query per table instead of a COUNT per figure
        users_stats = User.objects.aggregate(
            total=Count('id'),
            verified_email=Count('id', filter=Q(is_email_verified=True)),
            verified_investor=Count('id', filter=Q(is_verified=True)),
            active=Count('id', filter=Q(is_active=True)),
            locked=Count('id', filter=Q(account_locked_until__gt=now)),
            new_this_month=Count('id', filter=Q(created_at__gte=month_start)),
        )

        investments_stats = Investment.objects.aggregate(
            total_count=Count('id'),
            active=Count('id', filter=Q(status='ACTIVE')),
            exited=Count('id', filter=Q(status='EXITED')),
            total_invested=Sum('total_invested'),
            total_current_value=Sum('current_value'),
        )
        investments_stats['total_invested'] = investments_stats['total_invested'] or 0
        investments_stats['total_current_value'] = investments_stats['total_current_value'] or 0

        opportunities_stats = MarketplaceOpportunity.objects.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status='ACTIVE')),
            new=Count('id', filter=Q(status='NEW')),
            closing_soon=Count('id', filter=Q(status='CLOSING_SOON')),
            closed=Count('id', filter=Q(status='CLOSED')),
            featured=Count('id', filter=Q(is_featured=True)),
            total_raised=Sum('current_raised_amount'),
        )
        opportunities_stats['total_raised'] = opportunities_stats['total_raised'] or 0

        transfers_stats = OwnershipTransfer.objects.aggregate(
            total=Count('id'),
            pending=Count('id', filter=Q(status='PENDING')),
            approved=Count('id', filter=Q(status='APPROVED')),
            completed=Count('id', filter=Q(status='COMPLETED')),
            completed_this_month=Count('id', filter=Q(status='COMPLETED', completion_date__gte=month_start)),
        )

        # --- Recent Platform Activity ---
        recent_activity = list(
            UserActivity.objects.select_related('user')
            .order_by('-created_at')[:10]
            .values('id', 'activity_type', 'description', 'created_at', 'user__email')
        )

        return Response({
            "users": users_stats,
            "investments": investments_stats,
            "opportunities": opportunities_stats,
            "transfers": transfers_stats,
            "recent_activity": recent_activity,
        })
