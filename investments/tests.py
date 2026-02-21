from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from .models import Investment, OwnershipTransfer, CapitalActivity

User = get_user_model()

class InvestmentTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='investor',
            email='investor@example.com', password='Password123!', is_email_verified=True
        )
        self.client.force_authenticate(user=self.user)
        self.investment = Investment.objects.create(
            user=self.user,
            name='Tech Startup A',
            status='ACTIVE',
            sector='TECHNOLOGY',
            total_invested=100000.00,
            current_value=120000.00,
            investment_date=timezone.now().date()
        )
        self.list_url = reverse('investments:investment-list')
        self.detail_url = reverse('investments:investment-detail', args=[self.investment.id])

    def test_list_investments(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['name'], 'Tech Startup A')

    def test_retrieve_investment(self):
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Tech Startup A')

class AnalyticsTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='investor',
            email='investor@example.com', password='Password123!', is_email_verified=True
        )
        self.client.force_authenticate(user=self.user)
        self.investment = Investment.objects.create(
            user=self.user, name='Inv1', sector='TECHNOLOGY',
            total_invested=50000, current_value=50000, investment_date=timezone.now().date()
        )

    def test_portfolio_overview(self):
        # Create investments to ensure non-zero value
        Investment.objects.create(
            user=self.user, name='Inv2', sector='REAL_ESTATE',
            total_invested=50000, current_value=50000, investment_date=timezone.now().date()
        )
        
        url = reverse('investments:portfolio-overview') 
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Expect key_metrics, not summary
        self.assertEqual(float(response.data['key_metrics']['portfolio_value']), 100000.0)

    def test_asset_allocation(self):
        url = reverse('investments:portfolio-asset-allocation')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should have current_allocation
        self.assertIn('current_allocation', response.data)

class TransferTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='investor',
            email='investor@example.com', password='Password123!', is_email_verified=True
        )
        self.client.force_authenticate(user=self.user)
        self.investment = Investment.objects.create(
            user=self.user, name='Inv1', sector='TECHNOLOGY',
            total_invested=50000, current_value=50000, investment_date=timezone.now().date()
        )
        self.list_url = reverse('investments:transfer-list')

    def test_create_transfer_draft(self):
        data = {
            'investment': self.investment.id,
            'to_email': 'buyer@example.com',
            'transfer_amount': '1000.00',
            'transfer_type': 'PARTIAL',
            'percentage': 10.0,
            'reason': 'Liquidity'
        }
        response = self.client.post(self.list_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        transfer = OwnershipTransfer.objects.first()
        self.assertEqual(transfer.status, 'DRAFT')
        # Check fee calculation (assuming 2.5%, but logic is in model/serializer)
        # Just check it exists
        self.assertIsNotNone(transfer.transfer_fee)

    def test_submit_transfer(self):
        transfer = OwnershipTransfer.objects.create(
            investment=self.investment, from_user=self.user, 
            transfer_amount=1000,
            transfer_type='PARTIAL',
            percentage=10.0,
            status='DRAFT',
            reason='Test'
        )
        url = reverse('investments:transfer-submit', args=[transfer.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        transfer.refresh_from_db()

    def test_transfer_completion_signal(self):
        # Create a receiver user
        buyer = User.objects.create_user(
            username='buyer', email='buyer@example.com', password='Password123!', is_email_verified=True
        )
        
        # Create a transfer
        transfer = OwnershipTransfer.objects.create(
            investment=self.investment, 
            from_user=self.user, 
            to_user=buyer,
            transfer_amount=Decimal('10000.00'), # 10000 transfer
            transfer_type='PARTIAL',
            percentage=10.0,
            status='PENDING', # Start as PENDING
            reason='Deal'
        )
        
        # Simulate approval/completion
        transfer.status = 'COMPLETED'
        transfer.save()
        
        # Verify Signal Actions
        
        # 1. Seller's Investment Reduced
        self.investment.refresh_from_db()
        # Original 50000 -> Reduced by 10000 -> 40000
        self.assertEqual(self.investment.current_value, Decimal('40000.00'))
        
        # 2. Buyer's Investment Created
        buyer_investment = Investment.objects.get(user=buyer, name=self.investment.name)
        # Should match transfer amount
        self.assertEqual(buyer_investment.current_value, Decimal('10000.00'))
        self.assertEqual(buyer_investment.status, 'ACTIVE')
        
        # 3. Capital Activities Logged
        # Seller should have PARTIAL_EXIT
        self.assertTrue(CapitalActivity.objects.filter(
            investment=self.investment, 
            activity_type='PARTIAL_EXIT',
            amount=Decimal('10000.00')
        ).exists())
        
        # Buyer should have INITIAL_INVESTMENT (amount is negative for investment)
        self.assertTrue(CapitalActivity.objects.filter(
            investment=buyer_investment, 
            activity_type='INITIAL_INVESTMENT',
            amount=Decimal('-10000.00')
        ).exists())


class SecondaryMarketplaceTests(APITestCase):
    def setUp(self):
        # Seller
        self.seller = User.objects.create_user(
            username='seller', email='seller@example.com',
            password='Password123!', is_email_verified=True
        )
        # Buyer
        self.buyer = User.objects.create_user(
            username='buyer', email='buyer@example.com',
            password='Password123!', is_email_verified=True
        )
        self.investment = Investment.objects.create(
            user=self.seller, name='Agri Fund I', sector='AGRICULTURE',
            total_invested=100000, current_value=110000,
            investment_date=timezone.now().date()
        )
        # A PENDING transfer — should appear on the marketplace
        self.pending_transfer = OwnershipTransfer.objects.create(
            investment=self.investment,
            from_user=self.seller,
            to_email='anyone@example.com',
            transfer_type='PARTIAL',
            percentage=25,
            transfer_amount=Decimal('25000.00'),
            status='PENDING',
            reason='Need liquidity',
        )
        # A DRAFT transfer — must NOT appear on the marketplace
        self.draft_transfer = OwnershipTransfer.objects.create(
            investment=self.investment,
            from_user=self.seller,
            to_email='other@example.com',
            transfer_type='PARTIAL',
            percentage=10,
            transfer_amount=Decimal('10000.00'),
            status='DRAFT',
            reason='Still drafting',
        )
        self.list_url = reverse('investments:secondary-market-list')
        self.detail_url = reverse('investments:secondary-market-detail', args=[self.pending_transfer.id])

    # --- Authentication ---

    def test_unauthenticated_request_rejected(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # --- Listing visibility ---

    def test_pending_transfer_appears_in_listing(self):
        self.client.force_authenticate(user=self.buyer)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [item['id'] for item in response.data['results']]
        self.assertIn(self.pending_transfer.id, ids)

    def test_draft_transfer_excluded_from_listing(self):
        self.client.force_authenticate(user=self.buyer)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [item['id'] for item in response.data['results']]
        self.assertNotIn(self.draft_transfer.id, ids)

    def test_detail_view_returns_listing(self):
        self.client.force_authenticate(user=self.buyer)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.pending_transfer.id)
        self.assertEqual(response.data['investment_name'], 'Agri Fund I')
        self.assertIn('transfer_amount', response.data)
        self.assertIn('seller_display_name', response.data)

    # --- Filtering ---

    def test_filter_by_transfer_type(self):
        self.client.force_authenticate(user=self.buyer)
        response = self.client.get(self.list_url, {'transfer_type': 'FULL'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    def test_filter_by_min_amount(self):
        self.client.force_authenticate(user=self.buyer)
        response = self.client.get(self.list_url, {'min_amount': '30000'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    # --- express_interest ---

    def test_buyer_can_express_interest(self):
        self.client.force_authenticate(user=self.buyer)
        # Attach an opportunity so the action has something to link to
        from marketplace.models import MarketplaceOpportunity
        opp = MarketplaceOpportunity.objects.create(
            title='Agri Fund I Opp', description='desc', sector='AGRICULTURE',
            min_investment=Decimal('1000.00'), target_raise_amount=Decimal('500000.00'),
        )
        self.investment.opportunity = opp
        self.investment.save()

        url = reverse('investments:secondary-market-express-interest', args=[self.pending_transfer.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['created'])
        self.assertIn('interest_id', response.data)

    def test_seller_cannot_express_interest_in_own_listing(self):
        self.client.force_authenticate(user=self.seller)
        url = reverse('investments:secondary-market-express-interest', args=[self.pending_transfer.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

