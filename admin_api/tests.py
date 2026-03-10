"""
Comprehensive tests for the admin_api app.

Covers:
- Permission guarding (non-staff → 403, unauthenticated → 401)
- Dashboard KPIs
- User management: list, detail, suspend, unsuspend, unlock, verify, make-staff
- User sessions: list, terminate
- Opportunity management: list, create, publish, close, feature toggle, documents
- Investment management: list, detail, capital-activities
- Transfer management: list, approve, complete, reject
- Secondary interest management
- Analytics endpoints (smoke tests)
- System: activity-log, sessions, audit-log
"""
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from accounts.models import UserSession, UserActivity, InvestorProfile
from marketplace.models import MarketplaceOpportunity, InvestorInterest
from investments.models import Investment, OwnershipTransfer, CapitalActivity

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(email, is_staff=False, is_active=True):
    username = email.split('@')[0]
    u = User.objects.create_user(
        username=username,
        email=email,
        password='TestPass123!',
        first_name='Test',
        last_name='User',
        is_staff=is_staff,
        is_active=is_active,
        is_email_verified=True,
    )
    return u


def make_opportunity(**kwargs):
    defaults = dict(
        title='Test Opportunity',
        sector='TECHNOLOGY',
        description='Test desc',
        status='ACTIVE',
        min_investment=Decimal('10000.00'),
        target_raise_amount=Decimal('1000000.00'),
        current_raised_amount=Decimal('200000.00'),
    )
    defaults.update(kwargs)
    return MarketplaceOpportunity.objects.create(**defaults)


def make_investment(user, opportunity=None, **kwargs):
    opp = opportunity or make_opportunity()
    defaults = dict(
        user=user,
        opportunity=opp,
        total_invested=Decimal('50000.00'),
        current_value=Decimal('55000.00'),
        investment_date='2024-01-01',
    )
    defaults.update(kwargs)
    return Investment.objects.create(**defaults)


def authed_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# ---------------------------------------------------------------------------
# Permission guard tests
# ---------------------------------------------------------------------------

class AdminPermissionTests(TestCase):
    """Every admin endpoint must reject non-staff and unauthenticated users."""

    def setUp(self):
        self.admin = make_user('admin@test.com', is_staff=True)
        self.investor = make_user('investor@test.com', is_staff=False)
        self.anon_client = APIClient()
        self.ENDPOINTS = [
            ('GET', '/api/admin/dashboard/'),
            ('GET', '/api/admin/users/'),
            ('GET', '/api/admin/opportunities/'),
            ('GET', '/api/admin/investments/'),
            ('GET', '/api/admin/transfers/'),
            ('GET', '/api/admin/analytics/users/'),
            ('GET', '/api/admin/analytics/aum/'),
            ('GET', '/api/admin/analytics/opportunities/'),
            ('GET', '/api/admin/analytics/transfers/'),
            ('GET', '/api/admin/activity-log/'),
            ('GET', '/api/admin/sessions/'),
            ('GET', '/api/admin/audit-log/'),
        ]

    def test_unauthenticated_gets_401(self):
        for method, url in self.ENDPOINTS:
            response = getattr(self.anon_client, method.lower())(url)
            self.assertIn(
                response.status_code,
                [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
                f'Expected 401/403 for unauthenticated {method} {url}, got {response.status_code}',
            )

    def test_regular_investor_gets_403(self):
        client = authed_client(self.investor)
        for method, url in self.ENDPOINTS:
            response = getattr(client, method.lower())(url)
            self.assertEqual(
                response.status_code, status.HTTP_403_FORBIDDEN,
                f'Expected 403 for investor on {method} {url}, got {response.status_code}',
            )

    def test_admin_can_access_dashboard(self):
        client = authed_client(self.admin)
        response = client.get('/api/admin/dashboard/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Dashboard tests
# ---------------------------------------------------------------------------

class AdminDashboardTests(TestCase):
    def setUp(self):
        self.admin = make_user('admin@test.com', is_staff=True)
        self.client = authed_client(self.admin)
        self.investor = make_user('investor@test.com')
        self.opp = make_opportunity(title='Opp A')
        make_investment(self.investor, self.opp)

    def test_dashboard_returns_expected_keys(self):
        res = self.client.get('/api/admin/dashboard/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        for key in ('users', 'investments', 'opportunities', 'transfers', 'recent_activity'):
            self.assertIn(key, data, f'Missing key "{key}" in dashboard response')

    def test_dashboard_user_counts_are_accurate(self):
        res = self.client.get('/api/admin/dashboard/')
        data = res.json()
        # We created admin + investor = 2 users
        self.assertEqual(data['users']['total'], 2)

    def test_dashboard_opportunity_counts_are_accurate(self):
        res = self.client.get('/api/admin/dashboard/')
        data = res.json()
        self.assertEqual(data['opportunities']['total'], 1)
        self.assertEqual(data['opportunities']['active'], 1)


# ---------------------------------------------------------------------------
# User management tests
# ---------------------------------------------------------------------------

class AdminUserManagementTests(TestCase):
    def setUp(self):
        self.admin = make_user('admin@test.com', is_staff=True)
        self.client = authed_client(self.admin)
        self.user = make_user('user@test.com')

    def test_list_users(self):
        res = self.client.get('/api/admin/users/')
        self.assertEqual(res.status_code, 200)
        # Both admin and user exist
        self.assertGreaterEqual(res.json()['count'], 2)

    def test_list_users_search_filter(self):
        res = self.client.get('/api/admin/users/?search=user@test')
        self.assertEqual(res.status_code, 200)
        emails = [r['email'] for r in res.json()['results']]
        self.assertIn('user@test.com', emails)

    def test_list_users_is_staff_filter(self):
        res = self.client.get('/api/admin/users/?is_staff=true')
        self.assertEqual(res.status_code, 200)
        for r in res.json()['results']:
            self.assertTrue(r['is_staff'])

    def test_get_user_detail(self):
        res = self.client.get(f'/api/admin/users/{self.user.id}/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['email'], 'user@test.com')

    def test_patch_user(self):
        res = self.client.patch(
            f'/api/admin/users/{self.user.id}/',
            {'first_name': 'Updated'},
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Updated')

    def test_verify_user_email(self):
        self.user.is_email_verified = False
        self.user.save(update_fields=['is_email_verified'])
        res = self.client.post(f'/api/admin/users/{self.user.id}/verify/')
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_email_verified)

    def test_suspend_user(self):
        res = self.client.post(f'/api/admin/users/{self.user.id}/suspend/')
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_unsuspend_user(self):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        res = self.client.post(f'/api/admin/users/{self.user.id}/unsuspend/')
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_suspend_self_blocked(self):
        res = self.client.post(f'/api/admin/users/{self.admin.id}/suspend/')
        self.assertEqual(res.status_code, 400)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)  # unchanged

    def test_unlock_user(self):
        self.user.failed_login_attempts = 5
        self.user.account_locked_until = timezone.now() + timezone.timedelta(minutes=10)
        self.user.save(update_fields=['failed_login_attempts', 'account_locked_until'])

        res = self.client.post(f'/api/admin/users/{self.user.id}/unlock/')
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 0)
        self.assertIsNone(self.user.account_locked_until)

    def test_make_staff(self):
        res = self.client.post(f'/api/admin/users/{self.user.id}/make-staff/')
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_staff)

    def test_remove_staff_from_other_user(self):
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])
        res = self.client.post(f'/api/admin/users/{self.user.id}/remove-staff/')
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)

    def test_remove_staff_from_self_blocked(self):
        res = self.client.post(f'/api/admin/users/{self.admin.id}/remove-staff/')
        self.assertEqual(res.status_code, 400)

    def test_user_activity_log(self):
        UserActivity.log_activity(self.user, 'LOGIN', 'Logged in')
        res = self.client.get(f'/api/admin/users/{self.user.id}/activity/')
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(res.json()['count'], 1)

    def test_delete_user(self):
        res = self.client.delete(f'/api/admin/users/{self.user.id}/')
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(id=self.user.id).exists())


class AdminUserSessionTests(TestCase):
    def setUp(self):
        self.admin = make_user('admin@test.com', is_staff=True)
        self.client = authed_client(self.admin)
        self.user = make_user('user@test.com')
        self.session = UserSession.objects.create(
            user=self.user,
            device_name='Chrome on Windows',
            location='Lagos',
            ip_address='127.0.0.1',
            is_current=True,
            session_key='abc123-unique-key',
        )

    def test_list_user_sessions(self):
        res = self.client.get(f'/api/admin/users/{self.user.id}/sessions/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()), 1)

    def test_terminate_all_sessions(self):
        res = self.client.delete(f'/api/admin/users/{self.user.id}/terminate-sessions/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(UserSession.objects.filter(user=self.user).count(), 0)


# ---------------------------------------------------------------------------
# Opportunity tests
# ---------------------------------------------------------------------------

class AdminOpportunityTests(TestCase):
    def setUp(self):
        self.admin = make_user('admin@test.com', is_staff=True)
        self.client = authed_client(self.admin)
        self.opp = make_opportunity(title='Opp Alpha', status='NEW')

    def test_list_opportunities_includes_all_statuses(self):
        make_opportunity(title='Closed Opp', status='CLOSED')
        res = self.client.get('/api/admin/opportunities/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['count'], 2)

    def test_filter_by_status(self):
        res = self.client.get('/api/admin/opportunities/?status=NEW')
        self.assertEqual(res.status_code, 200)
        for r in res.json()['results']:
            self.assertEqual(r['status'], 'NEW')

    def test_get_opportunity_detail(self):
        res = self.client.get(f'/api/admin/opportunities/{self.opp.id}/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['title'], 'Opp Alpha')

    def test_create_opportunity(self):
        data = {
            'title': 'New Admin Opportunity',
            'sector': 'FINTECH',
            'description': 'Created via admin',
            'status': 'NEW',
            'min_investment': '5000.00',
            'target_raise_amount': '500000.00',
        }
        res = self.client.post('/api/admin/opportunities/', data, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(MarketplaceOpportunity.objects.filter(title='New Admin Opportunity').exists())

    def test_update_opportunity(self):
        res = self.client.patch(
            f'/api/admin/opportunities/{self.opp.id}/',
            {'title': 'Opp Alpha Updated'},
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.opp.refresh_from_db()
        self.assertEqual(self.opp.title, 'Opp Alpha Updated')

    def test_publish_opportunity(self):
        res = self.client.post(f'/api/admin/opportunities/{self.opp.id}/publish/')
        self.assertEqual(res.status_code, 200)
        self.opp.refresh_from_db()
        self.assertEqual(self.opp.status, 'ACTIVE')

    def test_close_opportunity(self):
        res = self.client.post(f'/api/admin/opportunities/{self.opp.id}/close/')
        self.assertEqual(res.status_code, 200)
        self.opp.refresh_from_db()
        self.assertEqual(self.opp.status, 'CLOSED')

    def test_cannot_publish_closed_opportunity(self):
        self.opp.status = 'CLOSED'
        self.opp.save(update_fields=['status'])
        res = self.client.post(f'/api/admin/opportunities/{self.opp.id}/publish/')
        self.assertEqual(res.status_code, 400)

    def test_feature_toggle(self):
        self.assertFalse(self.opp.is_featured)
        res = self.client.post(f'/api/admin/opportunities/{self.opp.id}/feature/')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['is_featured'])
        # Toggle back
        res2 = self.client.post(f'/api/admin/opportunities/{self.opp.id}/feature/')
        self.assertFalse(res2.json()['is_featured'])

    def test_delete_opportunity(self):
        res = self.client.delete(f'/api/admin/opportunities/{self.opp.id}/')
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(MarketplaceOpportunity.objects.filter(id=self.opp.id).exists())


# ---------------------------------------------------------------------------
# Investment tests
# ---------------------------------------------------------------------------

class AdminInvestmentTests(TestCase):
    def setUp(self):
        self.admin = make_user('admin@test.com', is_staff=True)
        self.client = authed_client(self.admin)
        self.investor = make_user('investor@test.com')
        self.opp = make_opportunity()
        self.inv = make_investment(self.investor, self.opp)

    def test_list_investments(self):
        res = self.client.get('/api/admin/investments/')
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(res.json()['count'], 1)

    def test_filter_by_user(self):
        res = self.client.get(f'/api/admin/investments/?user={self.investor.id}')
        self.assertEqual(res.status_code, 200)
        for r in res.json()['results']:
            self.assertEqual(r['user_email'], 'investor@test.com')

    def test_filter_by_status(self):
        res = self.client.get('/api/admin/investments/?status=ACTIVE')
        self.assertEqual(res.status_code, 200)
        for r in res.json()['results']:
            self.assertEqual(r['status'], 'ACTIVE')

    def test_get_investment_detail(self):
        res = self.client.get(f'/api/admin/investments/{self.inv.id}/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['id'], self.inv.id)

    def test_patch_investment(self):
        res = self.client.patch(
            f'/api/admin/investments/{self.inv.id}/',
            {'status': 'UNDERPERFORMING'},
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.inv.refresh_from_db()
        self.assertEqual(self.inv.status, 'UNDERPERFORMING')

    def test_list_capital_activities(self):
        CapitalActivity.objects.create(
            investment=self.inv,
            activity_type='DISTRIBUTION',
            amount=Decimal('1000.00'),
            date='2024-06-01',
        )
        res = self.client.get(f'/api/admin/investments/{self.inv.id}/capital-activities/')
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(res.json()['count'], 1)

    def test_create_capital_activity(self):
        data = {
            'activity_type': 'CAPITAL_CALL',
            'amount': '2000.00',
            'date': '2024-07-01',
        }
        res = self.client.post(
            f'/api/admin/investments/{self.inv.id}/capital-activities/',
            data,
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            CapitalActivity.objects.filter(investment=self.inv, activity_type='CAPITAL_CALL').exists()
        )


# ---------------------------------------------------------------------------
# Transfer tests
# ---------------------------------------------------------------------------

class AdminTransferTests(TestCase):
    def setUp(self):
        self.admin = make_user('admin@test.com', is_staff=True)
        self.client = authed_client(self.admin)
        self.seller = make_user('seller@test.com')
        self.buyer = make_user('buyer@test.com')
        self.opp = make_opportunity()
        self.inv = make_investment(self.seller, self.opp)
        self.transfer = OwnershipTransfer.objects.create(
            investment=self.inv,
            from_user=self.seller,
            to_user=self.buyer,
            to_email=self.buyer.email,
            transfer_amount=Decimal('25000.00'),
            transfer_fee=Decimal('0.00'),
            net_amount=Decimal('25000.00'),
            percentage=Decimal('50.00'),
            status='PENDING',
            transfer_type='PARTIAL',
        )

    def test_list_transfers(self):
        res = self.client.get('/api/admin/transfers/')
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(res.json()['count'], 1)

    def test_filter_transfers_by_status(self):
        res = self.client.get('/api/admin/transfers/?status=PENDING')
        self.assertEqual(res.status_code, 200)
        for r in res.json()['results']:
            self.assertEqual(r['status'], 'PENDING')

    def test_approve_transfer(self):
        res = self.client.post(f'/api/admin/transfers/{self.transfer.id}/approve/')
        self.assertEqual(res.status_code, 200)
        self.transfer.refresh_from_db()
        self.assertEqual(self.transfer.status, 'APPROVED')

    def test_cannot_approve_already_approved(self):
        self.transfer.status = 'APPROVED'
        self.transfer.save(update_fields=['status'])
        res = self.client.post(f'/api/admin/transfers/{self.transfer.id}/approve/')
        self.assertEqual(res.status_code, 400)

    def test_complete_transfer_requires_approved_status(self):
        # PENDING → complete should fail
        res = self.client.post(f'/api/admin/transfers/{self.transfer.id}/complete/')
        self.assertEqual(res.status_code, 400)

    def test_approve_then_complete_transfer(self):
        self.client.post(f'/api/admin/transfers/{self.transfer.id}/approve/')
        self.transfer.refresh_from_db()
        self.assertEqual(self.transfer.status, 'APPROVED')

        res = self.client.post(f'/api/admin/transfers/{self.transfer.id}/complete/')
        self.assertEqual(res.status_code, 200)
        self.transfer.refresh_from_db()
        self.assertEqual(self.transfer.status, 'COMPLETED')

    def test_reject_transfer(self):
        res = self.client.post(
            f'/api/admin/transfers/{self.transfer.id}/reject/',
            {'reason': 'Documentation incomplete'},
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.transfer.refresh_from_db()
        self.assertEqual(self.transfer.status, 'REJECTED')

    def test_cannot_reject_completed_transfer(self):
        self.transfer.status = 'COMPLETED'
        self.transfer.save(update_fields=['status'])
        res = self.client.post(f'/api/admin/transfers/{self.transfer.id}/reject/')
        self.assertEqual(res.status_code, 400)


# ---------------------------------------------------------------------------
# Analytics smoke tests
# ---------------------------------------------------------------------------

class AdminAnalyticsTests(TestCase):
    def setUp(self):
        self.admin = make_user('admin@test.com', is_staff=True)
        self.client = authed_client(self.admin)
        investor = make_user('inv@test.com')
        opp = make_opportunity()
        make_investment(investor, opp)

    def test_user_analytics(self):
        res = self.client.get('/api/admin/analytics/users/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('growth_by_month', data)
        self.assertIn('investor_type_breakdown', data)
        self.assertIn('verification_breakdown', data)

    def test_aum_analytics(self):
        res = self.client.get('/api/admin/analytics/aum/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('totals', data)
        self.assertIn('aum_by_sector', data)

    def test_opportunity_analytics(self):
        res = self.client.get('/api/admin/analytics/opportunities/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('results', res.json())

    def test_transfer_analytics(self):
        res = self.client.get('/api/admin/analytics/transfers/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('volume_by_month', data)
        self.assertIn('status_breakdown', data)


# ---------------------------------------------------------------------------
# System / audit tests
# ---------------------------------------------------------------------------

class AdminSystemTests(TestCase):
    def setUp(self):
        self.admin = make_user('admin@test.com', is_staff=True)
        self.client = authed_client(self.admin)
        self.user = make_user('user@test.com')
        UserActivity.log_activity(self.user, 'LOGIN', 'Test login')
        UserSession.objects.create(
            user=self.user,
            device_name='Chrome',
            location='Lagos',
            ip_address='127.0.0.1',
            is_current=True,
            session_key='system-test-key-unique',
        )

    def test_activity_log_returns_entries(self):
        res = self.client.get('/api/admin/activity-log/')
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(res.json()['count'], 1)

    def test_activity_log_filter_by_type(self):
        res = self.client.get('/api/admin/activity-log/?activity_type=LOGIN')
        self.assertEqual(res.status_code, 200)
        for r in res.json()['results']:
            self.assertEqual(r['activity_type'], 'LOGIN')

    def test_sessions_list(self):
        res = self.client.get('/api/admin/sessions/')
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(res.json()['count'], 1)

    def test_terminate_session_by_id(self):
        session = UserSession.objects.filter(user=self.user).first()
        res = self.client.delete(f'/api/admin/sessions/{session.id}/')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(UserSession.objects.filter(id=session.id).exists())

    def test_audit_log_returns_only_security_events(self):
        UserActivity.log_activity(self.user, 'PROFILE_UPDATE', 'Profile changed')
        res = self.client.get('/api/admin/audit-log/')
        self.assertEqual(res.status_code, 200)
        for r in res.json()['results']:
            self.assertIn(r['activity_type'], ['LOGIN', 'LOGOUT', 'PASSWORD_CHANGE', '2FA_ENABLED', '2FA_DISABLED'])


# ---------------------------------------------------------------------------
# Investor Profile tests
# ---------------------------------------------------------------------------

class AdminInvestorProfileTests(TestCase):
    """Admin can list, retrieve, patch any user's InvestorProfile."""

    def setUp(self):
        self.admin = make_user('admin@test.com', is_staff=True)
        self.client = authed_client(self.admin)
        self.investor = make_user('investor@test.com')
        # Profile auto-created by signal
        self.profile = InvestorProfile.objects.get(user=self.investor)

    def test_list_investor_profiles(self):
        res = self.client.get('/api/admin/investor-profiles/')
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(res.json()['count'], 1)

    def test_get_profile_detail(self):
        res = self.client.get(f'/api/admin/investor-profiles/{self.profile.id}/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['user_email'], 'investor@test.com')

    def test_get_profile_by_user(self):
        res = self.client.get(f'/api/admin/investor-profiles/by-user/{self.investor.id}/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['user_email'], 'investor@test.com')

    def test_get_profile_by_invalid_user_returns_404(self):
        res = self.client.get('/api/admin/investor-profiles/by-user/99999/')
        self.assertEqual(res.status_code, 404)

    def test_patch_investor_profile_bio(self):
        res = self.client.patch(
            f'/api/admin/investor-profiles/{self.profile.id}/',
            {'bio': 'Updated bio via admin panel.', 'display_name': 'New Display'},
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.bio, 'Updated bio via admin panel.')

    def test_patch_investor_category(self):
        res = self.client.patch(
            f'/api/admin/investor-profiles/{self.profile.id}/',
            {'investor_category': 'ANGEL'},
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.investor_category, 'ANGEL')

    def test_patch_preferred_sectors(self):
        res = self.client.patch(
            f'/api/admin/investor-profiles/{self.profile.id}/',
            {'preferred_sectors': ['TECHNOLOGY', 'FINTECH']},
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.profile.refresh_from_db()
        self.assertIn('TECHNOLOGY', self.profile.preferred_sectors)

    def test_filter_profiles_by_is_public(self):
        self.profile.is_public = False
        self.profile.save(update_fields=['is_public'])
        res = self.client.get('/api/admin/investor-profiles/?is_public=false')
        self.assertEqual(res.status_code, 200)
        for r in res.json()['results']:
            self.assertFalse(r['is_public'])

    def test_non_admin_cannot_access_profiles(self):
        investor_client = authed_client(self.investor)
        res = investor_client.get('/api/admin/investor-profiles/')
        self.assertEqual(res.status_code, 403)


# ---------------------------------------------------------------------------
# Investor Interest tests
# ---------------------------------------------------------------------------

class AdminInvestorInterestTests(TestCase):
    """Admin manages InvestorInterest (opportunity pledges) across all users."""

    def setUp(self):
        self.admin = make_user('admin@test.com', is_staff=True)
        self.client = authed_client(self.admin)
        self.investor = make_user('inv2@test.com')
        self.opp = make_opportunity(title='Interest Opp')
        self.interest = InvestorInterest.objects.create(
            user=self.investor,
            opportunity=self.opp,
            amount=Decimal('25000.00'),
            investment_date='2025-06-01',
            status='PENDING',
        )

    def test_list_investor_interests(self):
        res = self.client.get('/api/admin/investor-interests/')
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(res.json()['count'], 1)

    def test_get_interest_detail(self):
        res = self.client.get(f'/api/admin/investor-interests/{self.interest.id}/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['user_email'], 'inv2@test.com')
        self.assertEqual(data['opportunity_title'], 'Interest Opp')

    def test_filter_by_user_id(self):
        res = self.client.get(f'/api/admin/investor-interests/?user_id={self.investor.id}')
        self.assertEqual(res.status_code, 200)
        for r in res.json()['results']:
            self.assertEqual(r['user_email'], 'inv2@test.com')

    def test_filter_by_status(self):
        res = self.client.get('/api/admin/investor-interests/?status=PENDING')
        self.assertEqual(res.status_code, 200)
        for r in res.json()['results']:
            self.assertEqual(r['status'], 'PENDING')

    def test_filter_by_opportunity_id(self):
        res = self.client.get(f'/api/admin/investor-interests/?opportunity_id={self.opp.id}')
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(res.json()['count'], 1)

    def test_patch_interest_amount(self):
        res = self.client.patch(
            f'/api/admin/investor-interests/{self.interest.id}/',
            {'amount': '30000.00'},
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.interest.refresh_from_db()
        self.assertEqual(self.interest.amount, Decimal('30000.00'))

    def test_cancel_interest(self):
        res = self.client.post(f'/api/admin/investor-interests/{self.interest.id}/cancel/')
        self.assertEqual(res.status_code, 200)
        self.interest.refresh_from_db()
        self.assertEqual(self.interest.status, 'CANCELLED')

    def test_cancel_already_cancelled_fails(self):
        self.interest.status = 'CANCELLED'
        self.interest.save(update_fields=['status'])
        res = self.client.post(f'/api/admin/investor-interests/{self.interest.id}/cancel/')
        self.assertEqual(res.status_code, 400)

    def test_convert_interest(self):
        res = self.client.post(f'/api/admin/investor-interests/{self.interest.id}/convert/')
        self.assertEqual(res.status_code, 200)
        self.interest.refresh_from_db()
        self.assertEqual(self.interest.status, 'CONVERTED')

    def test_convert_already_converted_fails(self):
        self.interest.status = 'CONVERTED'
        self.interest.save(update_fields=['status'])
        res = self.client.post(f'/api/admin/investor-interests/{self.interest.id}/convert/')
        self.assertEqual(res.status_code, 400)

    def test_create_interest_on_behalf_of_user(self):
        data = {
            'user': self.investor.id,
            'opportunity': self.opp.id,
            'amount': '15000.00',
            'investment_date': '2025-09-01',
            'status': 'PENDING',
        }
        res = self.client.post('/api/admin/investor-interests/', data, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            InvestorInterest.objects.filter(user=self.investor, amount=Decimal('15000.00')).exists()
        )

    def test_delete_interest(self):
        res = self.client.delete(f'/api/admin/investor-interests/{self.interest.id}/')
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(InvestorInterest.objects.filter(id=self.interest.id).exists())

    def test_non_admin_cannot_access_interests(self):
        investor_client = authed_client(self.investor)
        res = investor_client.get('/api/admin/investor-interests/')
        self.assertEqual(res.status_code, 403)
