"""
Comprehensive tests for the marketplace app.
Covers: opportunity listing/filtering/detail, watchlist, request_information,
        InvestorInterest CRUD and new status field, secondary marketplace interactions.
"""
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from decimal import Decimal
from .models import MarketplaceOpportunity, InvestmentInterest, InvestorInterest

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(email='investor@example.com', **kwargs):
    defaults = dict(username=email.split('@')[0], password='Password123!', is_email_verified=True)
    defaults.update(kwargs)
    return User.objects.create_user(email=email, **defaults)


def make_opportunity(**kwargs):
    defaults = dict(
        title='Test Opp', description='desc', sector='TECHNOLOGY',
        min_investment=Decimal('10000.00'), target_raise_amount=Decimal('500000.00'),
        status='ACTIVE',
    )
    defaults.update(kwargs)
    return MarketplaceOpportunity.objects.create(**defaults)


# ---------------------------------------------------------------------------
# OpportunityTests
# ---------------------------------------------------------------------------

class OpportunityTests(APITestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_authenticate(user=self.user)
        self.opp1 = make_opportunity(title='Opp 1', sector='TECHNOLOGY', target_irr=15.0, min_investment=50000, target_raise_amount=1000000)
        self.opp2 = make_opportunity(title='Opp 2', sector='REAL_ESTATE', target_irr=12.0, min_investment=100000, target_raise_amount=2000000)
        self.list_url = reverse('marketplace:opportunity-list')

    def test_list_opportunities(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_filter_by_sector(self):
        response = self.client.get(self.list_url, {'sector': 'TECHNOLOGY'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['title'], 'Opp 1')

    def test_filter_by_status(self):
        # Only ACTIVE/NEW/CLOSING_SOON appear
        make_opportunity(title='Closed Opp', status='CLOSED')
        response = self.client.get(self.list_url)
        titles = [r['title'] for r in response.data['results']]
        self.assertNotIn('Closed Opp', titles)

    def test_search_by_title(self):
        response = self.client.get(self.list_url, {'search': 'Opp 1'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    def test_detail_view(self):
        url = reverse('marketplace:opportunity-detail', args=[self.opp1.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('detailed_description', response.data)
        self.assertIn('documents', response.data)

    def test_unauthenticated_can_list(self):
        """Marketplace listing is public."""
        self.client.force_authenticate(user=None)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_request_information(self):
        url = reverse('marketplace:opportunity-request-information', args=[self.opp1.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            InvestmentInterest.objects.filter(
                user=self.user, opportunity=self.opp1, interest_type='REQUESTED_INFO'
            ).exists()
        )

    def test_request_information_idempotent(self):
        """Duplicate requests should not create duplicate records."""
        url = reverse('marketplace:opportunity-request-information', args=[self.opp1.id])
        self.client.post(url)
        self.client.post(url)
        count = InvestmentInterest.objects.filter(
            user=self.user, opportunity=self.opp1, interest_type='REQUESTED_INFO'
        ).count()
        self.assertEqual(count, 1)

    def test_funding_progress_in_list(self):
        response = self.client.get(self.list_url)
        self.assertIn('funding_progress_percentage', response.data['results'][0])


# ---------------------------------------------------------------------------
# WatchlistTests
# ---------------------------------------------------------------------------

class WatchlistTests(APITestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_authenticate(user=self.user)
        self.opp = make_opportunity(title='Opp 1', status='ACTIVE', min_investment=10000, target_raise_amount=100000)
        self.bookmark_url = reverse('marketplace:opportunity-bookmark', args=[self.opp.id])
        self.remove_bookmark_url = reverse('marketplace:opportunity-remove-bookmark', args=[self.opp.id])
        self.list_url = reverse('marketplace:watchlist-list')

    def test_add_to_watchlist(self):
        response = self.client.post(self.bookmark_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(InvestmentInterest.objects.filter(user=self.user, opportunity=self.opp, interest_type='BOOKMARKED').exists())

    def test_add_to_watchlist_idempotent(self):
        self.client.post(self.bookmark_url)
        self.client.post(self.bookmark_url)
        self.assertEqual(InvestmentInterest.objects.filter(user=self.user, opportunity=self.opp, interest_type='BOOKMARKED').count(), 1)

    def test_remove_from_watchlist(self):
        InvestmentInterest.objects.create(user=self.user, opportunity=self.opp, interest_type='BOOKMARKED')
        response = self.client.delete(self.remove_bookmark_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(InvestmentInterest.objects.filter(user=self.user, opportunity=self.opp, interest_type='BOOKMARKED').exists())

    def test_remove_nonexistent_bookmark_is_graceful(self):
        response = self.client.delete(self.remove_bookmark_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_watchlist_only_shows_current_user(self):
        other = make_user(email='other@example.com')
        InvestmentInterest.objects.create(user=other, opportunity=self.opp, interest_type='BOOKMARKED')
        InvestmentInterest.objects.create(user=self.user, opportunity=self.opp, interest_type='BOOKMARKED')
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_count'], 1)


# ---------------------------------------------------------------------------
# InvestorInterestTests  (pledge/status field)
# ---------------------------------------------------------------------------

class InvestorInterestTests(APITestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_authenticate(user=self.user)
        self.opp = make_opportunity()
        self.list_url = reverse('marketplace:investor-interest-list')

    def test_create_investor_interest(self):
        data = {
            'opportunity': self.opp.id,
            'amount': '25000.00',
            'investment_date': '2026-06-01',
        }
        response = self.client.post(self.list_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'PENDING')
        self.assertIn('status_display', response.data)

    def test_default_status_is_pending(self):
        interest = InvestorInterest.objects.create(
            user=self.user, opportunity=self.opp,
            amount=Decimal('5000.00'), investment_date='2026-06-01'
        )
        self.assertEqual(interest.status, 'PENDING')

    def test_user_cannot_convert_own_pledge(self):
        """Status is read-only for investors: a CONVERTED patch is ignored."""
        interest = InvestorInterest.objects.create(
            user=self.user, opportunity=self.opp,
            amount=Decimal('15000.00'), investment_date='2026-06-01'
        )
        url = reverse('marketplace:investor-interest-detail', args=[interest.id])
        response = self.client.patch(url, {'status': 'CONVERTED'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        interest.refresh_from_db()
        self.assertEqual(interest.status, 'PENDING')
        from investments.models import Investment
        self.assertFalse(Investment.objects.filter(user=self.user).exists())

    def test_user_can_cancel_pending_pledge(self):
        interest = InvestorInterest.objects.create(
            user=self.user, opportunity=self.opp,
            amount=Decimal('15000.00'), investment_date='2026-06-01'
        )
        url = reverse('marketplace:investor-interest-cancel', args=[interest.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        interest.refresh_from_db()
        self.assertEqual(interest.status, 'CANCELLED')

    def test_cancelled_pledge_cannot_be_edited(self):
        interest = InvestorInterest.objects.create(
            user=self.user, opportunity=self.opp, status='CANCELLED',
            amount=Decimal('15000.00'), investment_date='2026-06-01'
        )
        url = reverse('marketplace:investor-interest-detail', args=[interest.id])
        response = self.client.patch(url, {'amount': '20000.00'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pledge_below_minimum_rejected(self):
        data = {'opportunity': self.opp.id, 'amount': '500.00', 'investment_date': '2026-06-01'}
        response = self.client.post(self.list_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pledge_above_remaining_capacity_rejected(self):
        data = {'opportunity': self.opp.id, 'amount': '600000.00', 'investment_date': '2026-06-01'}
        response = self.client.post(self.list_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pledge_on_closed_opportunity_rejected(self):
        closed = make_opportunity(title='Closed', status='CLOSED')
        data = {'opportunity': closed.id, 'amount': '20000.00', 'investment_date': '2026-06-01'}
        response = self.client.post(self.list_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pledge_cannot_be_deleted_by_user(self):
        interest = InvestorInterest.objects.create(
            user=self.user, opportunity=self.opp,
            amount=Decimal('15000.00'), investment_date='2026-06-01'
        )
        url = reverse('marketplace:investor-interest-detail', args=[interest.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_user_only_sees_own_interests(self):
        other = make_user(email='other@example.com')
        InvestorInterest.objects.create(user=other, opportunity=self.opp, amount=Decimal('1000'), investment_date='2026-01-01')
        InvestorInterest.objects.create(user=self.user, opportunity=self.opp, amount=Decimal('2000'), investment_date='2026-01-01')
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_amount_must_be_positive(self):
        data = {'opportunity': self.opp.id, 'amount': '-1000.00', 'investment_date': '2026-06-01'}
        response = self.client.post(self.list_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_str_includes_status(self):
        interest = InvestorInterest.objects.create(
            user=self.user, opportunity=self.opp,
            amount=Decimal('5000.00'), investment_date='2026-06-01'
        )
        self.assertIn('Pending', str(interest))


# ---------------------------------------------------------------------------
# InvestorInterestConversionTests  (auto-create Investment on CONVERTED)
# ---------------------------------------------------------------------------

class InvestorInterestConversionTests(APITestCase):
    """
    Staff converting an InvestorInterest (pledge) creates or tops up the
    investor's Investment and records a CapitalActivity.
    """

    def setUp(self):
        from investments.models import Investment, CapitalActivity
        self.Investment = Investment
        self.CapitalActivity = CapitalActivity

        self.user = make_user(email='converter@example.com')
        self.admin = make_user(email='staff@example.com', is_staff=True)
        self.client.force_authenticate(user=self.admin)
        self.opp = make_opportunity(
            title='Auto-Convert Opp',
            sector='FINTECH',
            min_investment=Decimal('5000.00'),
            target_raise_amount=Decimal('200000.00'),
        )
        self.interest = InvestorInterest.objects.create(
            user=self.user,
            opportunity=self.opp,
            amount=Decimal('10000.00'),
            investment_date='2026-07-01',
        )
        self.convert_url = f'/api/admin/investor-interests/{self.interest.id}/convert/'

    def test_conversion_creates_investment(self):
        response = self.client.post(self.convert_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        inv = self.Investment.objects.filter(user=self.user, opportunity=self.opp).first()
        self.assertIsNotNone(inv, "Investment should have been created on CONVERTED transition")
        self.assertEqual(inv.total_invested, Decimal('10000.00'))
        self.assertEqual(inv.current_value, Decimal('10000.00'))
        self.assertEqual(str(inv.investment_date), '2026-07-01')
        self.assertEqual(inv.status, 'ACTIVE')

        self.opp.refresh_from_db()
        self.assertEqual(self.opp.current_raised_amount, Decimal('10000.00'))
        self.assertEqual(self.opp.investors_count, 1)

    def test_conversion_creates_capital_activity(self):
        self.client.post(self.convert_url)
        inv = self.Investment.objects.get(user=self.user, opportunity=self.opp)
        activity = self.CapitalActivity.objects.filter(
            investment=inv,
            activity_type='INITIAL_INVESTMENT',
        ).first()
        self.assertIsNotNone(activity, "CapitalActivity(INITIAL_INVESTMENT) should be created")
        self.assertEqual(activity.amount, -Decimal('10000.00'))

    def test_conversion_is_idempotent(self):
        self.client.post(self.convert_url)
        response = self.client.post(self.convert_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        inv = self.Investment.objects.get(user=self.user, opportunity=self.opp)
        self.assertEqual(inv.total_invested, Decimal('10000.00'), "total_invested should not be doubled")

    def test_converted_status_is_final(self):
        """Toggling CONVERTED → PENDING → CONVERTED must not credit the investor twice."""
        from django.core.exceptions import ValidationError
        self.client.post(self.convert_url)
        self.interest.refresh_from_db()
        self.interest.status = 'PENDING'
        with self.assertRaises(ValidationError):
            self.interest.save()
        inv = self.Investment.objects.get(user=self.user, opportunity=self.opp)
        self.assertEqual(inv.total_invested, Decimal('10000.00'))

    def test_second_pledge_tops_up_existing_investment(self):
        self.client.post(self.convert_url)
        second = InvestorInterest.objects.create(
            user=self.user, opportunity=self.opp,
            amount=Decimal('5000.00'), investment_date='2026-08-01',
        )
        response = self.client.post(f'/api/admin/investor-interests/{second.id}/convert/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        inv = self.Investment.objects.get(user=self.user, opportunity=self.opp)
        self.assertEqual(inv.total_invested, Decimal('15000.00'))
        self.opp.refresh_from_db()
        self.assertEqual(self.opp.current_raised_amount, Decimal('15000.00'))
        self.assertEqual(self.opp.investors_count, 1)

    def test_conversion_beyond_capacity_rolls_back(self):
        """Over-funding is reported as a 400 and the pledge stays PENDING."""
        self.opp.current_raised_amount = Decimal('195000.00')
        self.opp.save(update_fields=['current_raised_amount'])
        response = self.client.post(self.convert_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.interest.refresh_from_db()
        self.assertEqual(self.interest.status, 'PENDING')
        self.assertFalse(self.Investment.objects.filter(user=self.user).exists())

    def test_reaching_target_closes_opportunity(self):
        self.interest.amount = Decimal('200000.00')
        self.interest.save(update_fields=['amount'])
        self.client.post(self.convert_url)
        self.opp.refresh_from_db()
        self.assertEqual(self.opp.status, 'CLOSED')

    def test_no_conversion_on_cancelled(self):
        """Cancelling must NOT create an Investment."""
        self.client.post(f'/api/admin/investor-interests/{self.interest.id}/cancel/')
        exists = self.Investment.objects.filter(user=self.user, opportunity=self.opp).exists()
        self.assertFalse(exists, "No Investment should be created when status is CANCELLED")


class RemoveBookmarkClosedOpportunityTests(APITestCase):
    def test_can_remove_bookmark_of_closed_opportunity(self):
        user = make_user()
        self.client.force_authenticate(user=user)
        opp = make_opportunity(status='CLOSED')
        InvestmentInterest.objects.create(user=user, opportunity=opp, interest_type='BOOKMARKED')
        response = self.client.delete(reverse('marketplace:opportunity-remove-bookmark', args=[opp.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(InvestmentInterest.objects.filter(user=user, opportunity=opp).exists())
