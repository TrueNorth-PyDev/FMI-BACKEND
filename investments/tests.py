from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from .models import Investment, OwnershipTransfer, CapitalActivity, SecondaryMarketInterest

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
        url = reverse('investments:secondary-market-express-interest', args=[self.pending_transfer.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['created'])
        self.assertIn('interest_id', response.data)
        # Should create a SecondaryMarketInterest (not InvestorInterest)
        self.assertTrue(
            SecondaryMarketInterest.objects.filter(
                transfer=self.pending_transfer, buyer=self.buyer
            ).exists()
        )

    def test_seller_cannot_express_interest_in_own_listing(self):
        self.client.force_authenticate(user=self.seller)
        url = reverse('investments:secondary-market-express-interest', args=[self.pending_transfer.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class SecondaryMarketInterestConversionTests(APITestCase):
    """
    Tests that converting a SecondaryMarketInterest deducts from the seller's
    Investment and creates/tops-up the buyer's Investment.
    """

    def setUp(self):
        self.seller = User.objects.create_user(
            username='seller2', email='seller2@example.com',
            password='Password123!', is_email_verified=True
        )
        self.buyer = User.objects.create_user(
            username='buyer2', email='buyer2@example.com',
            password='Password123!', is_email_verified=True
        )
        self.client.force_authenticate(user=self.buyer)

        self.seller_investment = Investment.objects.create(
            user=self.seller,
            name='Real Estate Fund II',
            sector='REAL_ESTATE',
            total_invested=Decimal('100000.00'),
            current_value=Decimal('110000.00'),
            investment_date=timezone.now().date(),
        )
        self.transfer = OwnershipTransfer.objects.create(
            investment=self.seller_investment,
            from_user=self.seller,
            transfer_amount=Decimal('30000.00'),
            transfer_type='PARTIAL',
            percentage=30,
            status='PENDING',
            reason='Liquidity',
        )
        self.interest = SecondaryMarketInterest.objects.create(
            transfer=self.transfer,
            buyer=self.buyer,
            amount=Decimal('30000.00'),
        )
        self.detail_url = reverse(
            'investments:secondary-market-interest-detail', args=[self.interest.id]
        )

    def test_conversion_deducts_from_seller(self):
        """CONVERTED status should deduct from the seller's investment."""
        response = self.client.patch(self.detail_url, {'status': 'CONVERTED'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.seller_investment.refresh_from_db()
        self.assertEqual(self.seller_investment.current_value, Decimal('80000.00'))
        self.assertEqual(self.seller_investment.total_invested, Decimal('70000.00'))

    def test_conversion_creates_buyer_investment(self):
        """CONVERTED status should create a new Investment for the buyer."""
        self.client.patch(self.detail_url, {'status': 'CONVERTED'})

        buyer_inv = Investment.objects.filter(user=self.buyer).first()
        self.assertIsNotNone(buyer_inv, 'Buyer Investment should be created')
        self.assertEqual(buyer_inv.current_value, Decimal('30000.00'))
        self.assertEqual(buyer_inv.total_invested, Decimal('30000.00'))
        self.assertEqual(buyer_inv.status, 'ACTIVE')

    def test_conversion_creates_capital_activities(self):
        """Both a PARTIAL_EXIT (seller) and INITIAL_INVESTMENT (buyer) should be logged."""
        self.client.patch(self.detail_url, {'status': 'CONVERTED'})

        buyer_inv = Investment.objects.get(user=self.buyer)

        seller_activity = CapitalActivity.objects.filter(
            investment=self.seller_investment,
            activity_type='PARTIAL_EXIT',
            amount=Decimal('30000.00'),
        ).first()
        self.assertIsNotNone(seller_activity, 'Seller PARTIAL_EXIT activity should exist')

        buyer_activity = CapitalActivity.objects.filter(
            investment=buyer_inv,
            activity_type='INITIAL_INVESTMENT',
            amount=Decimal('-30000.00'),
        ).first()
        self.assertIsNotNone(buyer_activity, 'Buyer INITIAL_INVESTMENT activity should exist')

    def test_transfer_marked_completed(self):
        """The OwnershipTransfer should be COMPLETED and is_processed=True after conversion."""
        self.client.patch(self.detail_url, {'status': 'CONVERTED'})

        self.transfer.refresh_from_db()
        self.assertEqual(self.transfer.status, 'COMPLETED')
        self.assertTrue(self.transfer.is_processed)

    def test_full_transfer_exits_seller(self):
        """If the transferred amount equals seller's entire current_value, mark seller EXITED
        and log a FULL_EXIT (not PARTIAL_EXIT) CapitalActivity."""
        # Set interest to full current_value
        self.interest.amount = Decimal('110000.00')
        self.interest.save(update_fields=['amount'])

        # Also update the transfer amount to match so validation passes
        self.transfer.transfer_amount = Decimal('110000.00')
        self.transfer.save(update_fields=['transfer_amount', 'transfer_fee', 'net_amount'])

        self.client.patch(self.detail_url, {'status': 'CONVERTED'})

        self.seller_investment.refresh_from_db()
        self.assertEqual(self.seller_investment.status, 'EXITED')
        self.assertEqual(self.seller_investment.current_value, Decimal('0.00'))

        # Should have FULL_EXIT, not PARTIAL_EXIT
        self.assertTrue(
            CapitalActivity.objects.filter(
                investment=self.seller_investment,
                activity_type='FULL_EXIT',
                amount=Decimal('110000.00'),
            ).exists(),
            'A FULL_EXIT CapitalActivity should be created on complete buyout',
        )
        self.assertFalse(
            CapitalActivity.objects.filter(
                investment=self.seller_investment,
                activity_type='PARTIAL_EXIT',
            ).exists(),
            'PARTIAL_EXIT should NOT be created when the seller fully exits',
        )

    def test_conversion_is_idempotent(self):
        """Patching CONVERTED twice should not double-deduct or double-credit."""
        self.client.patch(self.detail_url, {'status': 'CONVERTED'})
        self.client.patch(self.detail_url, {'status': 'CONVERTED'})  # no-op

        self.seller_investment.refresh_from_db()
        # Deducted exactly once
        self.assertEqual(self.seller_investment.current_value, Decimal('80000.00'))

        count = Investment.objects.filter(user=self.buyer).count()
        self.assertEqual(count, 1, 'Only one buyer investment should exist')


from marketplace.models import MarketplaceOpportunity


class TransferFeeTests(TestCase):
    """
    Verify that the transfer fee on OwnershipTransfer is 0
    and that net_amount equals transfer_amount.
    """

    def setUp(self):
        self.seller = User.objects.create_user(
            username='fee_seller', email='fee_seller@example.com',
            password='Password123!', is_email_verified=True
        )
        self.buyer = User.objects.create_user(
            username='fee_buyer', email='fee_buyer@example.com',
            password='Password123!', is_email_verified=True
        )
        self.investment = Investment.objects.create(
            user=self.seller, name='Fee Test Fund', sector='TECHNOLOGY',
            total_invested=Decimal('100000.00'), current_value=Decimal('100000.00'),
            investment_date=timezone.now().date(),
        )

    def test_transfer_fee_is_zero(self):
        """Transfer fee must be 0 (fee waived)."""
        transfer = OwnershipTransfer.objects.create(
            investment=self.investment,
            from_user=self.seller,
            to_user=self.buyer,
            transfer_amount=Decimal('20000.00'),
            transfer_type='PARTIAL',
            percentage=20,
            status='DRAFT',
            reason='Test fee',
        )
        self.assertEqual(transfer.transfer_fee, Decimal('0.00'))

    def test_net_amount_equals_transfer_amount_when_fee_is_zero(self):
        """net_amount must equal transfer_amount when fee is 0."""
        transfer = OwnershipTransfer.objects.create(
            investment=self.investment,
            from_user=self.seller,
            to_user=self.buyer,
            transfer_amount=Decimal('20000.00'),
            transfer_type='PARTIAL',
            percentage=20,
            status='DRAFT',
            reason='Test net amount',
        )
        self.assertEqual(transfer.net_amount, transfer.transfer_amount)


class TransferDoesNotAffectRaisedAmountTests(TestCase):
    """
    Verify that completing an ownership transfer (via OwnershipTransfer signal
    or SecondaryMarketInterest conversion) does NOT change the associated
    MarketplaceOpportunity.current_raised_amount.

    No new capital enters the opportunity during a transfer — only existing
    ownership moves between investors.
    """

    def setUp(self):
        self.seller = User.objects.create_user(
            username='raised_seller', email='raised_seller@example.com',
            password='Password123!', is_email_verified=True
        )
        self.buyer = User.objects.create_user(
            username='raised_buyer', email='raised_buyer@example.com',
            password='Password123!', is_email_verified=True
        )
        self.opportunity = MarketplaceOpportunity.objects.create(
            title='Opportunity A',
            sector='TECHNOLOGY',
            target_raise_amount=Decimal('1000000.00'),
            current_raised_amount=Decimal('200000.00'),
            min_investment=Decimal('1000.00'),
            status='ACTIVE',
        )
        self.seller_investment = Investment.objects.create(
            user=self.seller,
            opportunity=self.opportunity,
            name=self.opportunity.title,
            sector=self.opportunity.sector,
            total_invested=Decimal('100000.00'),
            current_value=Decimal('100000.00'),
            investment_date=timezone.now().date(),
        )
        # Snapshot the raised amount AFTER the seller's investment is created
        # (creating an investment legitimately increments current_raised_amount)
        self.opportunity.refresh_from_db()
        self.raised_before = self.opportunity.current_raised_amount

    # ------------------------------------------------------------------
    # OwnershipTransfer path
    # ------------------------------------------------------------------

    def test_ownership_transfer_completion_does_not_change_raised_amount(self):
        """Completing an OwnershipTransfer must not alter current_raised_amount."""
        transfer = OwnershipTransfer.objects.create(
            investment=self.seller_investment,
            from_user=self.seller,
            to_user=self.buyer,
            transfer_amount=Decimal('40000.00'),
            transfer_type='PARTIAL',
            percentage=40,
            status='PENDING',
            reason='Liquidity',
        )
        transfer.status = 'COMPLETED'
        transfer.save()

        self.opportunity.refresh_from_db()
        self.assertEqual(
            self.opportunity.current_raised_amount, self.raised_before,
            'current_raised_amount must not change after an ownership transfer'
        )

    # ------------------------------------------------------------------
    # SecondaryMarketInterest path — new buyer
    # ------------------------------------------------------------------

    def test_secondary_interest_conversion_does_not_change_raised_amount(self):
        """Converting a SecondaryMarketInterest must not alter current_raised_amount."""
        transfer = OwnershipTransfer.objects.create(
            investment=self.seller_investment,
            from_user=self.seller,
            transfer_amount=Decimal('30000.00'),
            transfer_type='PARTIAL',
            percentage=30,
            status='PENDING',
            reason='Secondary sale',
        )
        interest = SecondaryMarketInterest.objects.create(
            transfer=transfer,
            buyer=self.buyer,
            amount=Decimal('30000.00'),
        )
        interest.status = 'CONVERTED'
        interest.save()

        self.opportunity.refresh_from_db()
        self.assertEqual(
            self.opportunity.current_raised_amount, self.raised_before,
            'current_raised_amount must not change after a secondary market conversion'
        )

    # ------------------------------------------------------------------
    # SecondaryMarketInterest path — buyer top-up
    # ------------------------------------------------------------------

    def test_secondary_interest_topup_does_not_change_raised_amount(self):
        """
        If the buyer already has an investment and a secondary conversion tops
        it up, current_raised_amount must still be unchanged.
        """
        # Give the buyer an existing investment (this legitimately bumps raised)
        Investment.objects.create(
            user=self.buyer,
            opportunity=self.opportunity,
            name=self.opportunity.title,
            sector=self.opportunity.sector,
            total_invested=Decimal('10000.00'),
            current_value=Decimal('10000.00'),
            investment_date=timezone.now().date(),
        )
        self.opportunity.refresh_from_db()
        raised_after_buyer_joins = self.opportunity.current_raised_amount

        transfer = OwnershipTransfer.objects.create(
            investment=self.seller_investment,
            from_user=self.seller,
            transfer_amount=Decimal('20000.00'),
            transfer_type='PARTIAL',
            percentage=20,
            status='PENDING',
            reason='Top-up test',
        )
        interest = SecondaryMarketInterest.objects.create(
            transfer=transfer,
            buyer=self.buyer,
            amount=Decimal('20000.00'),
        )
        interest.status = 'CONVERTED'
        interest.save()

        self.opportunity.refresh_from_db()
        self.assertEqual(
            self.opportunity.current_raised_amount, raised_after_buyer_joins,
            'current_raised_amount must not change when buyer investment is topped up via transfer'
        )
