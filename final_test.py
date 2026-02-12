"""Final comprehensive test suite"""
from decimal import Decimal
from django.contrib.auth import get_user_model
from marketplace.models import MarketplaceOpportunity
from investments.models import Investment, PerformanceSnapshot
from investments.utils import calculate_portfolio_metrics
from django.core.management import call_command
from django.utils import timezone

User = get_user_model()

print("="*60)
print("  FINAL COMPREHENSIVE TEST SUITE")
print("="*60)

# Get test user
user = User.objects.filter(email='test@example.com').first()

# Create clean opportunity
opp = MarketplaceOpportunity.objects.create(
    title="Test Venture Fund",
    description="Test opportunity for IRR accrual",
    sector="TECHNOLOGY",
    status="ACTIVE",
    target_raise_amount=Decimal('5000000'),
    min_investment=Decimal('50000'),
    target_irr=Decimal('18.5'),
    investment_term_years=5,
    risk_level="MEDIUM"
)
print(f"\n✓ Created opportunity: {opp.title} (IRR: {opp.target_irr}%)")

# Create investment
inv = Investment.objects.create(
    user=user,
    opportunity=opp,
    status='ACTIVE',
    total_invested=Decimal('100000'),
    current_value=Decimal('100000'),
    investment_date=timezone.now().date()
)
print(f"✓ Created investment ID: {inv.id}")

# Test 1: Model methods
print("\nTest 1: Model Methods")
assert inv.get_name() == "Test Venture Fund"
print(f"  ✓ get_name(): {inv.get_name()}")
assert inv.get_sector() == "TECHNOLOGY"
print(f"  ✓ get_sector(): {inv.get_sector()}")
assert inv.target_irr == Decimal('18.5')
print(f"  ✓ target_irr: {inv.target_irr}%")

# Test 2: Portfolio metrics
print("\nTest 2: Portfolio Metrics (Uses target_irr)")
metrics = calculate_portfolio_metrics(user)
print(f"  Total Value: ${metrics['total_value']}")
print(f"  Total Invested: ${metrics['total_invested']}")
print(f"  Average IRR: {metrics['average_irr']}%")
assert metrics['average_irr'] == Decimal('18.5')
print("  ✓ Portfolio metrics use opportunity target_irr!")

# Test 3: Daily accrual (dry-run)
print("\nTest 3: Daily Accrual (Dry-Run)")
call_command('accrue_daily_irr', dry_run=True, verbosity=0)
print("  ✓ Dry-run completed")

# Test 4: Daily accrual (live)
print("\nTest 4: Daily Accrual (Live)")
old_value = inv.current_value
old_invested = inv.total_invested
print(f"  Before - Value: ${old_value}, Invested: ${old_invested}")

call_command('accrue_daily_irr', verbosity=0)
inv.refresh_from_db()

new_value = inv.current_value
new_invested = inv.total_invested
growth = new_value - old_value
print(f"  After - Value: ${new_value}, Invested: ${new_invested}")
print(f"  Growth: ${growth}")

assert new_invested == old_invested
print("  ✓ total_invested unchanged")
assert new_value > old_value
print(f"  ✓ current_value grew by ${growth}")

# Test 5: Calculation accuracy
annual_rate = Decimal('0.185')
daily_rate = (1 + annual_rate) ** (Decimal('1') / Decimal('365')) - 1
expected = old_value * (1 + daily_rate)
diff = abs(new_value - expected)
assert diff < Decimal('0.01')
print(f"  ✓ Calculation accurate (diff: ${diff})")

# Test 6: Performance snapshot
print("\nTest 5: Performance Snapshot")
snapshot = PerformanceSnapshot.objects.filter(
    investment=inv,
    date=timezone.now().date()
).first()
assert snapshot is not None
assert snapshot.value == inv.current_value
print(f"  ✓ Snapshot created with value: ${snapshot.value}")

# Test 7: Compound interest (5 days)
print("\nTest 6: Compound Interest (5 days)")
inv.current_value = Decimal('100000')
inv.save()
initial = Decimal('100000')

for day in range(1, 6):
    call_command('accrue_daily_irr', verbosity=0)
    inv.refresh_from_db()

expected_5days = initial * ((1 + daily_rate) ** 5)
diff_5days = abs(inv.current_value - expected_5days)
assert diff_5days < Decimal('0.01')
print(f"  Day 5 value: ${inv.current_value}")
print(f"  Expected: ${expected_5days}")
print(f"  ✓ Compound interest working (diff: ${diff_5days})")

print("\n" + "="*60)
print("  ALL TESTS PASSED ✓")
print("="*60)
print("\nVerified:")
print("  ✓ Investment-Opportunity relationship works")
print("  ✓ Model methods (get_name, get_sector, target_irr)")
print("  ✓ Portfolio metrics use target_irr from opportunity")
print("  ✓ Daily IRR accrual updates current_value correctly")
print("  ✓ total_invested stays fixed")
print("  ✓ Performance snapshots created")
print("  ✓ Compound interest calculation accurate")
print("\n🎉 ALL SYSTEMS OPERATIONAL!")
