"""
Admin Analytics views — growth charts, AUM, funding funnels, transfer volume.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth, TruncWeek
from datetime import timedelta

from admin_api.permissions import IsAdminUser
from investments.models import Investment, OwnershipTransfer
from marketplace.models import MarketplaceOpportunity, InvestorInterest

User = get_user_model()


class AdminUserAnalyticsView(APIView):
    """User growth and investor type breakdown."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        # Growth: new users per month for the last 12 months
        twelve_months_ago = timezone.now() - timedelta(days=365)
        growth = list(
            User.objects.filter(created_at__gte=twelve_months_ago)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(count=Count('id'))
            .order_by('month')
            .values('month', 'count')
        )

        # Investor type breakdown
        investor_types = list(
            User.objects.values('investor_type')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # Verification breakdown
        verification = {
            'email_verified': User.objects.filter(is_email_verified=True).count(),
            'email_unverified': User.objects.filter(is_email_verified=False).count(),
            'investor_verified': User.objects.filter(is_verified=True).count(),
        }

        return Response({
            'growth_by_month': growth,
            'investor_type_breakdown': investor_types,
            'verification_breakdown': verification,
        })


class AdminAUMAnalyticsView(APIView):
    """AUM over time and per sector."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        # Total AUM per sector
        aum_by_sector = list(
            Investment.objects.filter(status='ACTIVE')
            .values('sector')
            .annotate(
                total_invested=Sum('total_invested'),
                total_value=Sum('current_value'),
                count=Count('id'),
            )
            .order_by('-total_value')
        )

        # AUM growth: investments created per month for last 12 months
        twelve_months_ago = timezone.now() - timedelta(days=365)
        aum_growth = list(
            Investment.objects.filter(created_at__gte=twelve_months_ago)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(
                new_investments=Count('id'),
                capital_deployed=Sum('total_invested'),
            )
            .order_by('month')
        )

        # Summary
        totals = Investment.objects.aggregate(
            total_aum=Sum('current_value'),
            total_invested=Sum('total_invested'),
        )

        return Response({
            'totals': totals,
            'aum_by_sector': aum_by_sector,
            'aum_growth_by_month': aum_growth,
        })


class AdminOpportunityAnalyticsView(APIView):
    """Funding funnel stats per opportunity."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        opps = MarketplaceOpportunity.objects.annotate(
            interest_count=Count('investor_interest_pledges'),
            converted_count=Count(
                'investor_interest_pledges',
                filter=Q(investor_interest_pledges__status='CONVERTED')
            ),
        ).order_by('-created_at')

        results = []
        for opp in opps:
            results.append({
                'id': opp.id,
                'title': opp.title,
                'sector': opp.sector,
                'status': opp.status,
                'target_raise_amount': opp.target_raise_amount,
                'current_raised_amount': opp.current_raised_amount,
                'funding_progress_pct': float(opp.funding_progress_percentage),
                'investors_count': opp.investors_count,
                'interest_count': opp.interest_count,
                'converted_count': opp.converted_count,
                'conversion_rate_pct': round(
                    (opp.converted_count / opp.interest_count * 100)
                    if opp.interest_count else 0, 1
                ),
            })

        return Response({'count': len(results), 'results': results})


class AdminTransferAnalyticsView(APIView):
    """Transfer volume and value over time."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        twelve_months_ago = timezone.now() - timedelta(days=365)

        volume_by_month = list(
            OwnershipTransfer.objects.filter(created_at__gte=twelve_months_ago)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(
                count=Count('id'),
                total_value=Sum('transfer_amount'),
                completed=Count('id', filter=Q(status='COMPLETED')),
            )
            .order_by('month')
        )

        status_breakdown = list(
            OwnershipTransfer.objects.values('status')
            .annotate(count=Count('id'), total_value=Sum('transfer_amount'))
            .order_by('status')
        )

        type_breakdown = list(
            OwnershipTransfer.objects.values('transfer_type')
            .annotate(count=Count('id'), total_value=Sum('transfer_amount'))
        )

        return Response({
            'volume_by_month': volume_by_month,
            'status_breakdown': status_breakdown,
            'type_breakdown': type_breakdown,
        })
