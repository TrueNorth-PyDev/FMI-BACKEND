"""
Comprehensive tests for the marketplace app.
Covers: opportunity listing/filtering/detail, watchlist, request_information,
        InvestorInterest CRUD and new status field, secondary marketplace interactions.
"""
from django.test import TestCase
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

    def test_status_can_be_updated_to_converted(self):
        interest = InvestorInterest.objects.create(
            user=self.user, opportunity=self.opp,
            amount=Decimal('5000.00'), investment_date='2026-06-01'
        )
        url = reverse('marketplace:investor-interest-detail', args=[interest.id])
        response = self.client.patch(url, {'status': 'CONVERTED'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        interest.refresh_from_db()
        self.assertEqual(interest.status, 'CONVERTED')

    def test_invalid_status_rejected(self):
        interest = InvestorInterest.objects.create(
            user=self.user, opportunity=self.opp,
            amount=Decimal('5000.00'), investment_date='2026-06-01'
        )
        url = reverse('marketplace:investor-interest-detail', args=[interest.id])
        response = self.client.patch(url, {'status': 'INVALID_STATUS'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

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
