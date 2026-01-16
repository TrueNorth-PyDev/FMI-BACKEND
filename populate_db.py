"""
Populate database with realistic test data for API testing.
Run with: python manage.py shell < populate_db.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'privcap_hub.settings')
django.setup()

from django.contrib.auth import get_user_model
from accounts.models import InvestorProfile, InvestorConnection
from investments.models import Investment, CapitalActivity, OwnershipTransfer
from marketplace.models import MarketplaceOpportunity, InvestmentInterest
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone

User = get_user_model()

print("Clearing existing data...")
User.objects.all().delete()

print("Creating users...")
# Create regular investor
investor1 = User.objects.create_user(
    username='investor1',
    email='investor1@privcap.com',
    password='Test123!@#',
    first_name='John',
    last_name='Investor',
    phone_number='+1234567890',
    country='United States',
    investor_type='ACCREDITED',
    risk_tolerance='MODERATE',
    is_email_verified=True
)

investor2 = User.objects.create_user(
    username='investor2',
    email='investor2@privcap.com',
    password='Test123!@#',
    first_name='Jane',
    last_name='Capital',
    phone_number='+0987654321',
    country='United Kingdom',
    investor_type='QUALIFIED',
    risk_tolerance='AGGRESSIVE',
    is_email_verified=True
)

# Create admin user
admin = User.objects.create_superuser(
    username='admin',
    email='admin@privcap.com',
    password='Admin123!@#',
    first_name='Admin',
    last_name='User',
    is_email_verified=True
)

print("Creating investor profiles...")
profile1 = InvestorProfile.objects.get(user=investor1)
profile1.display_name = 'John Investor'
profile1.bio = 'Experienced investor focusing on tech and healthcare'
profile1.investor_category = 'ANGEL'
profile1.is_public = True
profile1.is_accepting_connections = True
profile1.preferred_sectors = ['TECHNOLOGY', 'HEALTHCARE']
profile1.min_investment = Decimal('50000.00')
profile1.save()

profile2 = InvestorProfile.objects.get(user=investor2)
profile2.display_name = 'Jane Capital'
profile2.bio = 'VC investor specializing in fintech and real estate'
profile2.investor_category = 'VC'
profile2.is_public = True
profile2.is_accepting_connections = True
profile2.preferred_sectors = ['FINTECH', 'REAL_ESTATE']
profile2.min_investment = Decimal('100000.00')
profile2.save()

print("Creating investments...")
# Investor 1's portfolio
inv1 = Investment.objects.create(
    user=investor1,
    name='TechVentures Fund III',
    status='ACTIVE',
    sector='TECHNOLOGY',
    total_invested=Decimal('250000.00'),
    current_value=Decimal('320000.00'),
    fund_size=Decimal('50000000.00'),
    unfunded_commitment=Decimal('50000.00'),
    manager='TechVentures Capital',
    investment_date=date(2023, 1, 15),
    expected_horizon_years=7,
    fund_vintage=2023,
    progress_percentage=Decimal('65.00')
)

inv2 = Investment.objects.create(
    user=investor1,
    name='HealthTech Growth Fund',
    status='ACTIVE',
    sector='HEALTHCARE',
    total_invested=Decimal('150000.00'),
    current_value=Decimal('180000.00'),
    manager='MedVentures',
    investment_date=date(2023, 6, 1),
    expected_horizon_years=5,
    fund_vintage=2023,
    progress_percentage=Decimal('45.00')
)

# Investor 2's portfolio
inv3 = Investment.objects.create(
    user=investor2,
    name='PropTech Real Estate Fund',
    status='ACTIVE',
    sector='REAL_ESTATE',
    total_invested=Decimal('500000.00'),
    current_value=Decimal('550000.00'),
    manager='PropTech Ventures',
    investment_date=date(2022, 9, 1),
    expected_horizon_years=10,
    fund_vintage=2022,
    progress_percentage=Decimal('80.00')
)

print("Creating capital activities...")
CapitalActivity.objects.create(
    investment=inv1,
    activity_type='INITIAL_INVESTMENT',
    amount=Decimal('-250000.00'),
    date=date(2023, 1, 15),
    details='Initial capital commitment'
)

CapitalActivity.objects.create(
    investment=inv1,
    activity_type='DISTRIBUTION',
    amount=Decimal('25000.00'),
    date=date(2024, 6, 30),
    details='Q2 2024 distribution'
)

print("Creating ownership transfer...")
transfer = OwnershipTransfer.objects.create(
    investment=inv2,
    from_user=investor1,
    to_user=investor2,
    transfer_type='PARTIAL',
    percentage=Decimal('20.00'),
    transfer_amount=Decimal('36000.00'),
    reason='Portfolio rebalancing',
    status='PENDING'
)

print("Creating marketplace opportunities...")
opp1 = MarketplaceOpportunity.objects.create(
    title='AI-Powered SaaS Startup',
    description='Series A funding for enterprise AI platform',
    detailed_description='Revolutionary AI platform transforming enterprise workflows...',
    sector='TECHNOLOGY',
    status='ACTIVE',
    min_investment=Decimal('25000.00'),
    target_raise_amount=Decimal('5000000.00'),
    current_raised_amount=Decimal('2500000.00'),
    target_irr=Decimal('25.00'),
    investment_term_years=5,
    investment_type='FIXED',
    risk_level='MEDIUM',
    payout_frequency='ANNUALLY',
    rating=Decimal('4.5'),
    investors_count=12,
    verification_type='VERIFIED',
    is_featured=True
)

opp2 = MarketplaceOpportunity.objects.create(
    title='Green Energy Infrastructure Fund',
    description='Renewable energy projects across emerging markets',
    detailed_description='Diversified portfolio of solar and wind projects...',
    sector='ENERGY',
    status='ACTIVE',
    min_investment=Decimal('50000.00'),
    target_raise_amount=Decimal('10000000.00'),
    current_raised_amount=Decimal('7500000.00'),
    target_irr=Decimal('18.00'),
    investment_term_years=8,
    investment_type='VARIABLE',
    risk_level='LOW',
    payout_frequency='QUARTERLY',
    rating=Decimal('4.8'),
    investors_count=25,
    verification_type='VERIFIED',
    is_featured=True
)

print("Creating investment interests...")
InvestmentInterest.objects.create(
    user=investor1,
    opportunity=opp1,
    interest_type='BOOKMARKED'
)

print("Creating investor connection...")
InvestorConnection.objects.create(
    from_investor=investor1,
    to_investor=investor2,
    status='ACCEPTED',
    message='Looking forward to collaborating!'
)

print("\nDatabase populated successfully!")
print("\nTest Credentials:")
print("=" * 50)
print("Investor 1:")
print("  Email: investor1@privcap.com")
print("  Password: Test123!@#")
print("\nInvestor 2:")
print("  Email: investor2@privcap.com")
print("  Password: Test123!@#")
print("\nAdmin:")
print("  Email: admin@privcap.com")
print("  Password: Admin123!@#")
print("=" * 50)
