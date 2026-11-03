from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from .models import Investment, OwnershipTransfer, CapitalActivity, SecondaryMarketInterest, PerformanceSnapshot

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
        self.admin = User.objects.create_user(
            username='staff2', email='staff2@example.com',
            password='Password123!', is_email_verified=True, is_staff=True
        )
        self.client.force_authenticate(user=self.admin)

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
        # Staff execute the purchase via the admin API
        self.detail_url = f'/api/admin/secondary-interests/{self.interest.id}/'

    def test_conversion_deducts_from_seller(self):
        """CONVERTED status should deduct from the seller's investment."""
        response = self.client.patch(self.detail_url, {'status': 'CONVERTED'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.seller_investment.refresh_from_db()
        self.assertEqual(self.seller_investment.current_value, Decimal('80000.00'))
        # Cost basis is reduced in proportion to the value sold: 100000 × 30000/110000
        self.assertEqual(self.seller_investment.total_invested, Decimal('72727.27'))

    def test_buyer_cannot_convert_own_interest(self):
        """Buyers may only cancel; a CONVERTED patch from the buyer is ignored."""
        self.client.force_authenticate(user=self.buyer)
        url = reverse('investments:secondary-market-interest-detail', args=[self.interest.id])
        self.client.patch(url, {'status': 'CONVERTED'})
        self.interest.refresh_from_db()
        self.assertEqual(self.interest.status, 'PENDING')
        self.seller_investment.refresh_from_db()
        self.assertEqual(self.seller_investment.current_value, Decimal('110000.00'))

    def test_buyer_can_cancel_interest(self):
        self.client.force_authenticate(user=self.buyer)
        url = reverse('investments:secondary-market-interest-cancel', args=[self.interest.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.interest.refresh_from_db()
        self.assertEqual(self.interest.status, 'CANCELLED')

    def test_competing_interests_cancelled_on_conversion(self):
        other = User.objects.create_user(
            username='buyer3', email='buyer3@example.com', password='Password123!', is_email_verified=True
        )
        competing = SecondaryMarketInterest.objects.create(
            transfer=self.transfer, buyer=other, amount=Decimal('10000.00')
        )
        self.client.patch(self.detail_url, {'status': 'CONVERTED'}, format='json')
        competing.refresh_from_db()
        self.assertEqual(competing.status, 'CANCELLED')
        response = self.client.patch(f'/api/admin/secondary-interests/{competing.id}/',
                                     {'status': 'CONVERTED'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_conversion_creates_buyer_investment(self):
        """CONVERTED status should create a new Investment for the buyer."""
        self.client.patch(self.detail_url, {'status': 'CONVERTED'}, format='json')

        buyer_inv = Investment.objects.filter(user=self.buyer).first()
        self.assertIsNotNone(buyer_inv, 'Buyer Investment should be created')
        self.assertEqual(buyer_inv.current_value, Decimal('30000.00'))
        self.assertEqual(buyer_inv.total_invested, Decimal('30000.00'))
        self.assertEqual(buyer_inv.status, 'ACTIVE')

    def test_conversion_creates_capital_activities(self):
        """Both a PARTIAL_EXIT (seller) and INITIAL_INVESTMENT (buyer) should be logged."""
        self.client.patch(self.detail_url, {'status': 'CONVERTED'}, format='json')

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
        self.client.patch(self.detail_url, {'status': 'CONVERTED'}, format='json')

        self.transfer.refresh_from_db()
        self.assertEqual(self.transfer.status, 'COMPLETED')
        self.assertTrue(self.transfer.is_processed)
        self.assertEqual(self.transfer.to_user, self.buyer)

    def test_full_transfer_exits_seller(self):
        """If the transferred amount equals seller's entire current_value, mark seller EXITED
        and log a FULL_EXIT (not PARTIAL_EXIT) CapitalActivity."""
        # Set interest to full current_value
        self.interest.amount = Decimal('110000.00')
        self.interest.save(update_fields=['amount'])

        # Also update the transfer amount to match so validation passes
        self.transfer.transfer_amount = Decimal('110000.00')
        self.transfer.save(update_fields=['transfer_amount', 'transfer_fee', 'net_amount'])

        self.client.patch(self.detail_url, {'status': 'CONVERTED'}, format='json')

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
        self.client.patch(self.detail_url, {'status': 'CONVERTED'}, format='json')
        response = self.client.patch(self.detail_url, {'status': 'CONVERTED'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

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


# ---------------------------------------------------------------------------
# Regression tests for access control and money-movement fixes
# ---------------------------------------------------------------------------

def _user(name, **kwargs):
    return User.objects.create_user(
        username=name, email=f'{name}@example.com', password='Password123!',
        is_email_verified=True, **kwargs
    )


def _opportunity(**kwargs):
    defaults = dict(
        title='Fund', description='d', sector='TECHNOLOGY', status='ACTIVE',
        min_investment=Decimal('100.00'), target_raise_amount=Decimal('100000.00'),
        target_irr=Decimal('12.00'), investment_term_years=5,
    )
    defaults.update(kwargs)
    return MarketplaceOpportunity.objects.create(**defaults)


class InvestmentReadOnlyTests(APITestCase):
    def setUp(self):
        self.user = _user('reader')
        self.client.force_authenticate(user=self.user)
        self.investment = Investment.objects.create(
            user=self.user, name='A', total_invested=Decimal('1000'),
            current_value=Decimal('1000'), investment_date=timezone.now().date(),
        )

    def test_user_cannot_create_investment(self):
        response = self.client.post('/api/investments/', {
            'name': 'Fake', 'total_invested': '1', 'current_value': '1000000',
            'investment_date': '2026-01-01',
        })
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_user_cannot_edit_investment_value(self):
        response = self.client.patch(f'/api/investments/{self.investment.id}/', {'current_value': '999999'})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_user_cannot_record_capital_activity(self):
        response = self.client.post('/api/capital-activities/', {
            'investment': self.investment.id, 'activity_type': 'DISTRIBUTION',
            'amount': '10', 'date': '2026-01-01',
        })
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_capital_activities_list(self):
        CapitalActivity.objects.create(investment=self.investment, activity_type='DISTRIBUTION',
                                       amount=Decimal('5'), date=timezone.now().date())
        response = self.client.get('/api/capital-activities/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_bad_days_param_returns_400(self):
        response = self.client.get(f'/api/investments/{self.investment.id}/performance_history/?days=abc')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class OwnershipTransferApiTests(APITestCase):
    def setUp(self):
        self.seller = _user('owner')
        self.recipient = _user('recipient')
        self.client.force_authenticate(user=self.seller)
        self.investment = Investment.objects.create(
            user=self.seller, name='A', total_invested=Decimal('1000'),
            current_value=Decimal('1000'), investment_date=timezone.now().date(),
        )

    def _payload(self, **kwargs):
        data = {'investment': self.investment.id, 'to_user': self.recipient.id, 'transfer_type': 'PARTIAL',
                'percentage': '50', 'transfer_amount': '500', 'reason': 'x'}
        data.update(kwargs)
        return data

    def test_cannot_create_transfer_already_completed(self):
        response = self.client.post('/api/transfers/', self._payload(status='COMPLETED'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Investment.objects.filter(user=self.recipient).exists())
        self.investment.refresh_from_db()
        self.assertEqual(self.investment.current_value, Decimal('1000.00'))

    def test_can_create_transfer_as_pending(self):
        response = self.client.post('/api/transfers/', self._payload(status='PENDING'))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(OwnershipTransfer.objects.get().status, 'PENDING')

    def test_transfer_amount_cannot_exceed_value(self):
        response = self.client.post('/api/transfers/', self._payload(transfer_amount='5000'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_draft_can_be_edited(self):
        self.client.post('/api/transfers/', self._payload())
        transfer = OwnershipTransfer.objects.get()
        response = self.client.patch(f'/api/transfers/{transfer.id}/', {'transfer_amount': '600'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        transfer.refresh_from_db()
        self.assertEqual(transfer.transfer_amount, Decimal('600.00'))

    def test_pending_transfer_cannot_be_edited(self):
        self.client.post('/api/transfers/', self._payload(status='PENDING'))
        transfer = OwnershipTransfer.objects.get()
        response = self.client.patch(f'/api/transfers/{transfer.id}/', {'transfer_amount': '600'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_recipient_cannot_edit_transfer(self):
        self.client.post('/api/transfers/', self._payload())
        transfer = OwnershipTransfer.objects.get()
        self.client.force_authenticate(user=self.recipient)
        response = self.client.patch(f'/api/transfers/{transfer.id}/', {'transfer_amount': '600'})
        self.assertIn(response.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN))

    def test_direct_transfer_not_listed_on_secondary_market(self):
        self.client.post('/api/transfers/', self._payload(status='PENDING'))
        transfer = OwnershipTransfer.objects.get()
        sniper = _user('sniper')
        self.client.force_authenticate(user=sniper)
        self.assertEqual(self.client.get('/api/secondary-market/').data['count'], 0)
        response = self.client.post(f'/api/secondary-market/{transfer.id}/express_interest/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_full_transfer_moves_whole_position(self):
        transfer = OwnershipTransfer.objects.create(
            investment=self.investment, from_user=self.seller, to_user=self.recipient,
            transfer_type='FULL', transfer_amount=Decimal('400'), reason='x', status='APPROVED',
        )
        transfer.status = 'COMPLETED'
        transfer.save()
        self.investment.refresh_from_db()
        self.assertEqual(self.investment.status, 'EXITED')
        recipient_inv = Investment.objects.get(user=self.recipient)
        self.assertEqual(recipient_inv.current_value, Decimal('1000.00'))
        self.assertTrue(CapitalActivity.objects.filter(investment=self.investment, activity_type='FULL_EXIT').exists())


class AdminTransferCompletionTests(APITestCase):
    def setUp(self):
        self.admin = _user('boss', is_staff=True)
        self.seller = _user('seller9')
        self.client.force_authenticate(user=self.admin)
        self.investment = Investment.objects.create(
            user=self.seller, name='A', total_invested=Decimal('1000'),
            current_value=Decimal('1000'), investment_date=timezone.now().date(),
        )

    def test_completing_transfer_without_recipient_fails_cleanly(self):
        transfer = OwnershipTransfer.objects.create(
            investment=self.investment, from_user=self.seller, to_email='someone@example.com',
            transfer_type='PARTIAL', percentage=10, transfer_amount=Decimal('100'),
            reason='x', status='APPROVED',
        )
        response = self.client.post(f'/api/admin/transfers/{transfer.id}/complete/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, 'APPROVED')
        self.assertFalse(transfer.is_processed)


class SecondarySaleFullyFundedOpportunityTests(TestCase):
    def test_secondary_sale_of_fully_funded_opportunity(self):
        """Fully funded opportunities must still allow ownership to change hands."""
        seller, buyer = _user('fseller'), _user('fbuyer')
        opp = _opportunity(target_raise_amount=Decimal('1000.00'))
        inv = Investment.objects.create(user=seller, opportunity=opp, total_invested=Decimal('1000'),
                                        current_value=Decimal('1000'), investment_date=timezone.now().date())
        opp.refresh_from_db()
        self.assertEqual(opp.status, 'CLOSED')
        transfer = OwnershipTransfer.objects.create(
            investment=inv, from_user=seller, transfer_type='PARTIAL', percentage=50,
            transfer_amount=Decimal('500'), reason='x', status='PENDING',
        )
        interest = SecondaryMarketInterest.objects.create(transfer=transfer, buyer=buyer, amount=Decimal('500'))
        interest.status = 'CONVERTED'
        interest.save()
        inv.refresh_from_db()
        self.assertEqual(inv.current_value, Decimal('500.00'))
        self.assertEqual(Investment.objects.get(user=buyer).current_value, Decimal('500.00'))
        opp.refresh_from_db()
        self.assertEqual(opp.current_raised_amount, Decimal('1000.00'))
        self.assertEqual(opp.investors_count, 2)


class DailyAccrualTests(TestCase):
    def setUp(self):
        from io import StringIO
        self.out = StringIO()
        self.user = _user('accruer')
        self.opp = _opportunity()
        self.investment = Investment.objects.create(
            user=self.user, opportunity=self.opp, total_invested=Decimal('1000'),
            current_value=Decimal('1000'), investment_date=timezone.now().date(),
        )
        self.today = timezone.now().date()

    def _accrue(self):
        from django.core.management import call_command
        call_command('accrue_daily_irr', stdout=self.out)
        self.investment.refresh_from_db()

    def _expected(self, days):
        from investments.management.commands.accrue_daily_irr import daily_rate_for
        rate = daily_rate_for(Decimal('12.00'))
        return (Decimal('1000') * (1 + rate) ** days).quantize(Decimal('0.01'))

    def test_new_investment_not_accrued_on_creation_day(self):
        self._accrue()
        self.assertEqual(self.investment.current_value, Decimal('1000.00'))

    def test_missed_days_are_backfilled(self):
        Investment.objects.filter(pk=self.investment.pk).update(
            last_accrued_date=self.today - timezone.timedelta(days=5)
        )
        self._accrue()
        self.assertEqual(self.investment.current_value, self._expected(5))
        self.assertEqual(self.investment.last_accrued_date, self.today)
        self.assertEqual(
            PerformanceSnapshot.objects.filter(
                investment=self.investment, date__gt=self.today - timezone.timedelta(days=5)
            ).count(), 5
        )

    def test_backfill_survives_an_intervening_save(self):
        """An ordinary save (which snapshots today's value) must not swallow missed days."""
        Investment.objects.filter(pk=self.investment.pk).update(
            last_accrued_date=self.today - timezone.timedelta(days=5)
        )
        self.investment.refresh_from_db()
        self.investment.manager = 'edited'
        self.investment.save()
        self._accrue()
        self.assertEqual(self.investment.current_value, self._expected(5))

    def test_accrual_is_idempotent_within_a_day(self):
        Investment.objects.filter(pk=self.investment.pk).update(
            last_accrued_date=self.today - timezone.timedelta(days=1)
        )
        self._accrue()
        self._accrue()
        self.assertEqual(self.investment.current_value, self._expected(1))

    def test_accrual_works_on_fully_funded_opportunity(self):
        MarketplaceOpportunity.objects.filter(pk=self.opp.pk).update(
            current_raised_amount=self.opp.target_raise_amount + 1  # drifted over target
        )
        Investment.objects.filter(pk=self.investment.pk).update(
            last_accrued_date=self.today - timezone.timedelta(days=1)
        )
        self._accrue()
        self.assertEqual(self.investment.current_value, self._expected(1))


class AnalyticsCashFlowTests(TestCase):
    def test_sale_is_not_a_drawdown(self):
        """Selling part of a position is a cash flow, not a loss."""
        from investments.utils import calculate_max_drawdown
        seller, buyer = _user('dd_seller'), _user('dd_buyer')
        inv = Investment.objects.create(user=seller, name='A', total_invested=Decimal('1000'),
                                        current_value=Decimal('1000'), investment_date=timezone.now().date())
        yesterday = timezone.now().date() - timezone.timedelta(days=1)
        PerformanceSnapshot.objects.filter(investment=inv).update(date=yesterday)
        transfer = OwnershipTransfer.objects.create(
            investment=inv, from_user=seller, transfer_type='PARTIAL', percentage=50,
            transfer_amount=Decimal('500'), reason='x', status='PENDING',
        )
        interest = SecondaryMarketInterest.objects.create(transfer=transfer, buyer=buyer, amount=Decimal('500'))
        interest.status = 'CONVERTED'
        interest.save()
        self.assertEqual(calculate_max_drawdown(seller), Decimal('0.00'))

    def test_quarterly_performance_is_deterministic(self):
        from investments.utils import calculate_quarterly_performance
        user = _user('q_user')
        Investment.objects.create(user=user, name='A', total_invested=Decimal('1000'),
                                  current_value=Decimal('1000'), investment_date=timezone.now().date())
        first = calculate_quarterly_performance(user)
        self.assertEqual(first, calculate_quarterly_performance(user))
        self.assertEqual(len(first), 4)
        self.assertEqual(len({q['quarter'] for q in first}), 4)


class RealizedGainAndPrimaryCapitalTests(TestCase):
    def setUp(self):
        self.seller, self.buyer = _user('rg_seller'), _user('rg_buyer')
        self.opp = _opportunity(target_raise_amount=Decimal('10000.00'))
        self.investment = Investment.objects.create(
            user=self.seller, opportunity=self.opp, total_invested=Decimal('1000'),
            current_value=Decimal('1000'), investment_date=timezone.now().date(),
        )
        # Value has grown 50% since purchase
        Investment.objects.filter(pk=self.investment.pk).update(current_value=Decimal('1500'))

    def _sell(self, amount):
        transfer = OwnershipTransfer.objects.create(
            investment=self.investment, from_user=self.seller, transfer_type='PARTIAL', percentage=50,
            transfer_amount=Decimal(amount), reason='x', status='PENDING',
        )
        interest = SecondaryMarketInterest.objects.create(transfer=transfer, buyer=self.buyer, amount=Decimal(amount))
        interest.status = 'CONVERTED'
        interest.save()

    def test_realized_gain_is_proceeds_minus_cost_basis(self):
        from investments.utils import calculate_returns_analysis
        self._sell('750')  # half the position: proceeds 750, cost basis 500
        analysis = calculate_returns_analysis(self.seller)
        self.assertEqual(analysis['cash_received'], Decimal('750.00'))
        self.assertEqual(analysis['realized_gains'], Decimal('250.00'))
        exit_activity = CapitalActivity.objects.get(investment=self.investment, activity_type='PARTIAL_EXIT')
        self.assertEqual(exit_activity.cost_basis, Decimal('500.00'))

    def _assert_raised_equals_primary_capital(self):
        from django.db.models import Sum
        self.opp.refresh_from_db()
        total = Investment.objects.filter(opportunity=self.opp).aggregate(t=Sum('primary_capital'))['t']
        self.assertEqual(self.opp.current_raised_amount, total or Decimal('0.00'))

    def test_primary_capital_moves_with_ownership(self):
        self.investment.refresh_from_db()
        self.assertEqual(self.investment.primary_capital, Decimal('1000.00'))
        self._sell('750')  # half the position
        self.investment.refresh_from_db()
        self.assertEqual(self.investment.primary_capital, Decimal('500.00'))
        self.assertEqual(Investment.objects.get(user=self.buyer).primary_capital, Decimal('500.00'))
        self._assert_raised_equals_primary_capital()

    def test_deleting_bought_in_investment_removes_only_its_share(self):
        self._sell('750')
        Investment.objects.get(user=self.buyer).delete()
        self.opp.refresh_from_db()
        self.assertEqual(self.opp.current_raised_amount, Decimal('500.00'))
        self._assert_raised_equals_primary_capital()

    def test_deleting_primary_investment_removes_its_capital(self):
        self.investment.delete()
        self.opp.refresh_from_db()
        self.assertEqual(self.opp.current_raised_amount, Decimal('0.00'))
        self.assertEqual(self.opp.investors_count, 0)

    def test_admin_capital_adjustment_moves_raised_amount(self):
        self.investment.refresh_from_db()
        self.investment.total_invested = Decimal('1200')
        self.investment.save()
        self.opp.refresh_from_db()
        self.assertEqual(self.opp.current_raised_amount, Decimal('1200.00'))


class DjangoAdminDryRunFormTests(TestCase):
    def test_failed_transfer_completion_is_a_form_error(self):
        from django.contrib import admin
        seller = _user('dj_seller')
        investment = Investment.objects.create(
            user=seller, name='A', total_invested=Decimal('1000'),
            current_value=Decimal('1000'), investment_date=timezone.now().date(),
        )
        transfer = OwnershipTransfer.objects.create(
            investment=investment, from_user=seller, transfer_type='PARTIAL', percentage=10,
            transfer_amount=Decimal('100'), reason='x', status='APPROVED',  # no to_user
        )
        from django.forms import modelform_factory
        model_admin = admin.site._registry[OwnershipTransfer]
        fields = ['investment', 'from_user', 'to_email', 'to_name', 'transfer_type',
                  'percentage', 'transfer_amount', 'reason', 'status']
        form_cls = modelform_factory(OwnershipTransfer, form=model_admin.form, fields=fields)
        data = {field: getattr(transfer, field) for field in
                ('transfer_type', 'percentage', 'transfer_amount', 'reason', 'to_email', 'to_name')}
        data.update(investment=investment.pk, from_user=seller.pk, status='COMPLETED')
        form = form_cls(data=data, instance=transfer)
        self.assertFalse(form.is_valid())
        self.assertIn('no registered recipient', str(form.errors))
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, 'APPROVED')
        investment.refresh_from_db()
        self.assertEqual(investment.current_value, Decimal('1000.00'))


class InvestorsCountTests(TestCase):
    def test_count_follows_status_changes(self):
        user = _user('count_user')
        opp = _opportunity()
        investment = Investment.objects.create(user=user, opportunity=opp, total_invested=Decimal('100'),
                                               current_value=Decimal('100'), investment_date=timezone.now().date())
        opp.refresh_from_db()
        self.assertEqual(opp.investors_count, 1)
        investment.status = 'EXITED'
        investment.save()
        opp.refresh_from_db()
        self.assertEqual(opp.investors_count, 0)
        investment.status = 'ACTIVE'
        investment.save()
        opp.refresh_from_db()
        self.assertEqual(opp.investors_count, 1)


class UserListQueryCountTests(APITestCase):
    """Investor-facing list endpoints must not run a query per row."""

    def setUp(self):
        self.viewer = _user('qc_viewer')
        self.client.force_authenticate(self.viewer)
        self.opp = _opportunity(target_raise_amount=Decimal('10000000'))
        self.n = 0

    def _add_rows(self, count):
        from marketplace.models import InvestorInterest
        for _ in range(count):
            self.n += 1
            seller = _user(f'qc_seller_{self.n}')
            inv = Investment.objects.create(user=seller, opportunity=self.opp, total_invested=Decimal('1000'),
                                            current_value=Decimal('1000'), investment_date=timezone.now().date())
            listing = OwnershipTransfer.objects.create(
                investment=inv, from_user=seller, transfer_type='PARTIAL', percentage=10,
                transfer_amount=Decimal('100'), reason='x', status='PENDING',
            )
            SecondaryMarketInterest.objects.create(transfer=listing, buyer=self.viewer, amount=Decimal('50'))
            own = Investment.objects.create(user=self.viewer, name=f'Own {self.n}', total_invested=Decimal('10'),
                                            current_value=Decimal('10'), investment_date=timezone.now().date())
            CapitalActivity.objects.create(investment=own, activity_type='DISTRIBUTION',
                                           amount=Decimal('1'), date=timezone.now().date())
            OwnershipTransfer.objects.create(
                investment=own, from_user=self.viewer, to_user=seller, transfer_type='PARTIAL',
                percentage=10, transfer_amount=Decimal('1'), reason='x', status='DRAFT',
            )
            InvestorInterest.objects.create(user=self.viewer, opportunity=self.opp,
                                            amount=Decimal('500'), investment_date=timezone.now().date())

    def _queries_for(self, url):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        return len(ctx.captured_queries)

    def test_list_endpoints_scale_flat(self):
        urls = [
            '/api/investments/', '/api/capital-activities/', '/api/transfers/', '/api/transfers/pending/',
            '/api/secondary-market/', '/api/secondary-market-interests/', '/api/marketplace/investor-interest/',
            '/api/marketplace/opportunities/', '/api/accounts/network/directory/', '/api/portfolio/overview/',
            '/api/portfolio/risk_metrics/', '/api/portfolio/performance_analysis/',
        ]
        self._add_rows(2)
        before = {url: self._queries_for(url) for url in urls}
        self._add_rows(4)
        after = {url: self._queries_for(url) for url in urls}
        self.assertEqual(before, after)
