"""
Admin Dashboard view — single-call platform KPIs.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Sum, Count, Q
from datetime import timedelta

from admin_api.permissions import IsAdminUser
from investments.models import Investment, OwnershipTransfer
from marketplace.models import MarketplaceOpportunity
from accounts.models import UserActivity

User = get_user_model()


class AdminDashboardView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # --- Users ---
        users_qs = User.objects.all()
        users_stats = {
            "total": users_qs.count(),
            "verified_email": users_qs.filter(is_email_verified=True).count(),
            "verified_investor": users_qs.filter(is_verified=True).count(),
            "active": users_qs.filter(is_active=True).count(),
            "locked": users_qs.filter(
                account_locked_until__gt=now
            ).count(),
            "new_this_month": users_qs.filter(created_at__gte=month_start).count(),
        }

        # --- Investments ---
        inv_qs = Investment.objects.all()
        inv_agg = inv_qs.aggregate(
            total_invested=Sum('total_invested'),
            total_value=Sum('current_value'),
        )
        investments_stats = {
            "total_count": inv_qs.count(),
            "active": inv_qs.filter(status='ACTIVE').count(),
            "exited": inv_qs.filter(status='EXITED').count(),
            "total_invested": inv_agg['total_invested'] or 0,
            "total_current_value": inv_agg['total_value'] or 0,
        }

        # --- Opportunities ---
        opp_qs = MarketplaceOpportunity.objects.all()
        opp_agg = opp_qs.aggregate(total_raised=Sum('current_raised_amount'))
        opportunities_stats = {
            "total": opp_qs.count(),
            "active": opp_qs.filter(status='ACTIVE').count(),
            "new": opp_qs.filter(status='NEW').count(),
            "closing_soon": opp_qs.filter(status='CLOSING_SOON').count(),
            "closed": opp_qs.filter(status='CLOSED').count(),
            "featured": opp_qs.filter(is_featured=True).count(),
            "total_raised": opp_agg['total_raised'] or 0,
        }

        # --- Transfers ---
        transfer_qs = OwnershipTransfer.objects.all()
        transfers_stats = {
            "total": transfer_qs.count(),
            "pending": transfer_qs.filter(status='PENDING').count(),
            "approved": transfer_qs.filter(status='APPROVED').count(),
            "completed": transfer_qs.filter(status='COMPLETED').count(),
            "completed_this_month": transfer_qs.filter(
                status='COMPLETED', updated_at__gte=month_start
            ).count(),
        }

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
