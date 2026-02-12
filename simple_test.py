from decimal import Decimal
from django.contrib.auth import get_user_model
from marketplace.models import MarketplaceOpportunity
from investments.models import Investment

User = get_user_model()

# Get or create test user
user = User.objects.filter(email='test@example.com').first()
if not user:
    user = User.objects.create_user(email='test@example.com', username='testuser', password='test123')

# Create opportunity
opp = MarketplaceOpportunity.objects.create(
    title="Test Fund",
    description="Test",
    sector="TECHNOLOGY",
    status="ACTIVE",
    target_raise_amount=Decimal('1000000'),
    min_investment=Decimal('10000'),
    target_irr=Decimal('20.0'),
    investment_term_years=5,
    risk_level="MEDIUM"
)

# Create investment
inv = Investment.objects.create(
    user=user,
    opportunity=opp,
    status='ACTIVE',
    total_invested=Decimal('50000'),
    current_value=Decimal('50000'),
    investment_date='2026-02-12'
)

print(f"Created investment ID: {inv.id}")
print(f"Name: {inv.get_name()}")
print(f"Sector: {inv.get_sector()}")
print(f"Target IRR: {inv.target_irr}%")
print("SUCCESS: Investment-Opportunity link works!")
