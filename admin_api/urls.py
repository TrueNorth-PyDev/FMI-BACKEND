"""
URL configuration for the admin_api app.
All endpoints require is_staff=True (enforced per-view).
Mounted at: /api/admin/
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .dashboard_views import AdminDashboardView
from .user_views import AdminUserViewSet
from .marketplace_views import AdminOpportunityViewSet
from .investment_views import AdminInvestmentViewSet
from .transfer_views import AdminTransferViewSet, AdminSecondaryInterestViewSet
from .analytics_views import (
    AdminUserAnalyticsView,
    AdminAUMAnalyticsView,
    AdminOpportunityAnalyticsView,
    AdminTransferAnalyticsView,
)
from .system_views import (
    AdminActivityLogView,
    AdminSessionListView,
    AdminSessionDetailView,
    AdminAuditLogView,
)

app_name = 'admin_api'

router = DefaultRouter()
router.register(r'users', AdminUserViewSet, basename='admin-user')
router.register(r'opportunities', AdminOpportunityViewSet, basename='admin-opportunity')
router.register(r'investments', AdminInvestmentViewSet, basename='admin-investment')
router.register(r'transfers', AdminTransferViewSet, basename='admin-transfer')
router.register(r'secondary-interests', AdminSecondaryInterestViewSet, basename='admin-secondary-interest')

urlpatterns = [
    # --- Dashboard ---
    path('dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),

    # --- Resource ViewSets ---
    path('', include(router.urls)),

    # --- Analytics ---
    path('analytics/users/', AdminUserAnalyticsView.as_view(), name='admin-analytics-users'),
    path('analytics/aum/', AdminAUMAnalyticsView.as_view(), name='admin-analytics-aum'),
    path('analytics/opportunities/', AdminOpportunityAnalyticsView.as_view(), name='admin-analytics-opportunities'),
    path('analytics/transfers/', AdminTransferAnalyticsView.as_view(), name='admin-analytics-transfers'),

    # --- System / Audit ---
    path('activity-log/', AdminActivityLogView.as_view(), name='admin-activity-log'),
    path('sessions/', AdminSessionListView.as_view(), name='admin-sessions'),
    path('sessions/<int:session_id>/', AdminSessionDetailView.as_view(), name='admin-session-detail'),
    path('audit-log/', AdminAuditLogView.as_view(), name='admin-audit-log'),
]
