from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from .models import MarketplaceOpportunity, InvestmentInterest

User = get_user_model()

class OpportunityTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='investor',
            email='investor@example.com', password='Password123!', is_email_verified=True
        )
        self.client.force_authenticate(user=self.user)
        
        # Create opportunities
        self.opp1 = MarketplaceOpportunity.objects.create(
            title='Opp 1', description='Desc 1', sector='TECHNOLOGY',
            target_irr=15.0, min_investment=50000, status='ACTIVE',
            target_raise_amount=1000000
        )
        self.opp2 = MarketplaceOpportunity.objects.create(
            title='Opp 2', description='Desc 2', sector='REAL_ESTATE',
            target_irr=12.0, min_investment=100000, status='ACTIVE',
            target_raise_amount=2000000
        )
        # Use correct namespace 'marketplace:opportunity-list'
        self.list_url = reverse('marketplace:opportunity-list')

    def test_list_opportunities(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_filter_opportunities(self):
        # Filter by sector
        response = self.client.get(self.list_url, {'sector': 'TECHNOLOGY'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Assuming the filter matches EXACTLY what is stored (TECHNOLOGY)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['title'], 'Opp 1')

class WatchlistTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='investor',
            email='investor@example.com', password='Password123!', is_email_verified=True
        )
        self.client.force_authenticate(user=self.user)
        self.opp = MarketplaceOpportunity.objects.create(
            title='Opp 1', status='ACTIVE', min_investment=10000, sector='TECHNOLOGY',
            target_raise_amount=100000 # Required field
        )
        # Correct endpoints are actions on the opportunity viewset
        self.bookmark_url = reverse('marketplace:opportunity-bookmark', args=[self.opp.id])
        self.remove_bookmark_url = reverse('marketplace:opportunity-remove-bookmark', args=[self.opp.id])
        self.list_url = reverse('marketplace:watchlist-list')

    def test_add_to_watchlist(self):
        response = self.client.post(self.bookmark_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(InvestmentInterest.objects.filter(user=self.user, opportunity=self.opp, interest_type='BOOKMARKED').exists())

    def test_remove_from_watchlist(self):
        # Add first
        InvestmentInterest.objects.create(user=self.user, opportunity=self.opp, interest_type='BOOKMARKED')
        
        response = self.client.delete(self.remove_bookmark_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(InvestmentInterest.objects.filter(user=self.user, opportunity=self.opp, interest_type='BOOKMARKED').exists())
