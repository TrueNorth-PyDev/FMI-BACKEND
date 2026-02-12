"""
Comprehensive test script for Investment-Opportunity integration.
Tests models, serializers, portfolio metrics, and daily accrual.
"""

from decimal import Decimal
from django.contrib.auth import get_user_model
from marketplace.models import MarketplaceOpportunity
from investments.models import Investment, PerformanceSnapshot
from investments.utils import calculate_portfolio_metrics
from django.core.management import call_command
from django.utils import timezone
import sys

User = get_user_model()

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")

def print_success(text):
    print(f"✓ {text}")

def print_error(text):
    print(f"✗ {text}")
    sys.exit(1)

print_header("COMPREHENSIVE TESTING SUITE")

# Test 1: Create test user
print_header("Test 1: Create Test User")
try:
    user, created = User.objects.get_or_create(
        email='test@example.com',
        defaults={'username': 'testuser'}
    )
    print_success(f"User: {user.email}")
except Exception as e:
    print_error(f"Failed to create user: {e}")

# Test 2: Create marketplace opportunity
print_header("Test 2: Create Marketplace Opportunity")
try:
    opportunity = MarketplaceOpportunity.objects.create(
        title="TechVenture Fund III",
        description="High-growth technology fund",
        sector="TECHNOLOGY",
        status="ACTIVE",
        target_raise_amount=Decimal('5000000.00'),
        current_raised_amount=Decimal('0.00'),
        min_investment=Decimal('50000.00'),
        target_irr=Decimal('18.5'),  # 18.5% annual IRR
        investment_term_years=5,
        risk_level="MEDIUM"
    )
    print_success(f"Created opportunity: {opportunity.title}")
    print(f"  - Target IRR: {opportunity.target_irr}%")
    print(f"  - Sector: {opportunity.sector}")
except Exception as e:
    print_error(f"Failed to create opportunity: {e}")

# Test 3: Create investment linked to opportunity
print_header("Test 3: Create Investment with Opportunity Link")
try:
    investment = Investment.objects.create(
        user=user,
        opportunity=opportunity,
        status='ACTIVE',
        total_invested=Decimal('100000.00'),
        current_value=Decimal('100000.00'),
        investment_date=timezone.now().date()
    )
    print_success(f"Created investment: {investment.id}")
    print(f"  - Opportunity: {investment.opportunity.title}")
    print(f"  - Name (from opportunity): {investment.get_name()}")
    print(f"  - Sector (from opportunity): {investment.get_sector()}")
    print(f"  - Target IRR (from opportunity): {investment.target_irr}%")
except Exception as e:
    print_error(f"Failed to create investment: {e}")

# Test 4: Test model methods
print_header("Test 4: Test Model Methods")
try:
    assert investment.get_name() == "TechVenture Fund III", "Name should come from opportunity"
    print_success("get_name() works correctly")
    
    assert investment.get_sector() == "TECHNOLOGY", "Sector should come from opportunity"
    print_success("get_sector() works correctly")
    
    assert investment.target_irr == Decimal('18.5'), "Target IRR should come from opportunity"
    print_success("target_irr property works correctly")
    
    assert investment.unrealized_gain == Decimal('0.00'), "Initial unrealized gain should be 0"
    print_success("unrealized_gain calculation works")
    
    assert investment.moic == Decimal('1.00'), "Initial MOIC should be 1.0"
    print_success("moic calculation works")
except AssertionError as e:
    print_error(f"Model method test failed: {e}")

# Test 5: Test legacy investment (without opportunity)
print_header("Test 5: Test Legacy Investment (No Opportunity)")
try:
    legacy_investment = Investment.objects.create(
        user=user,
        name="Legacy Fund",
        sector="HEALTHCARE",
        status='ACTIVE',
        total_invested=Decimal('50000.00'),
        current_value=Decimal('55000.00'),
        investment_date=timezone.now().date()
    )
    print_success(f"Created legacy investment: {legacy_investment.id}")
    
    assert legacy_investment.get_name() == "Legacy Fund", "Legacy investment should use name field"
    print_success("Legacy get_name() works correctly")
    
    assert legacy_investment.get_sector() == "HEALTHCARE", "Legacy investment should use sector field"
    print_success("Legacy get_sector() works correctly")
    
    assert legacy_investment.target_irr is None, "Legacy investment has no target IRR"
    print_success("Legacy target_irr is None (correct)")
except Exception as e:
    print_error(f"Failed legacy investment test: {e}")

# Test 6: Test portfolio metrics
print_header("Test 6: Test Portfolio Metrics (Uses target_irr)")
try:
    metrics = calculate_portfolio_metrics(user)
    
    print(f"  Total Value: ${metrics['total_value']:,.2f}")
    print(f"  Total Invested: ${metrics['total_invested']:,.2f}")
    print(f"  Unrealized Gains: ${metrics['unrealized_gains']:,.2f}")
    print(f"  Average IRR: {metrics['average_irr']}%")
    print(f"  Num Investments: {metrics['num_investments']}")
    
    # Average IRR should be 18.5% (only one investment with target_irr)
    assert metrics['average_irr'] == Decimal('18.5'), f"Expected 18.5%, got {metrics['average_irr']}%"
    print_success("Average IRR calculation uses target_irr correctly")
except Exception as e:
    print_error(f"Portfolio metrics test failed: {e}")

# Test 7: Test daily IRR accrual (dry-run)
print_header("Test 7: Test Daily IRR Accrual (Dry-Run)")
try:
    print("Running: python manage.py accrue_daily_irr --dry-run")
    call_command('accrue_daily_irr', dry_run=True)
    print_success("Dry-run completed without errors")
except Exception as e:
    print_error(f"Dry-run failed: {e}")

# Test 8: Test daily IRR accrual (live)
print_header("Test 8: Test Daily IRR Accrual (Live)")
try:
    old_value = investment.current_value
    old_invested = investment.total_invested
    
    print(f"  Before - Current Value: ${old_value:,.2f}")
    print(f"  Before - Total Invested: ${old_invested:,.2f}")
    
    call_command('accrue_daily_irr')
    
    # Refresh from database
    investment.refresh_from_db()
    
    new_value = investment.current_value
    new_invested = investment.total_invested
    growth = new_value - old_value
    
    print(f"  After - Current Value: ${new_value:,.2f}")
    print(f"  After - Total Invested: ${new_invested:,.2f}")
    print(f"  Growth: ${growth:,.2f}")
    
    # Verify calculations
    assert new_invested == old_invested, "Total invested should not change"
    print_success("total_invested unchanged (correct)")
    
    assert new_value > old_value, "Current value should increase"
    print_success(f"current_value increased by ${growth:,.2f}")
    
    # Calculate expected growth
    annual_rate = Decimal('0.185')  # 18.5%
    daily_rate = (1 + annual_rate) ** (Decimal('1') / Decimal('365')) - 1
    expected_value = old_value * (1 + daily_rate)
    
    # Allow small rounding difference
    diff = abs(new_value - expected_value)
    assert diff < Decimal('0.01'), f"Value mismatch. Expected: ${expected_value}, Got: ${new_value}"
    print_success(f"Growth calculation accurate (diff: ${diff})")
    
except Exception as e:
    print_error(f"Live accrual test failed: {e}")

# Test 9: Verify performance snapshot created
print_header("Test 9: Verify Performance Snapshot")
try:
    today = timezone.now().date()
    snapshot = PerformanceSnapshot.objects.filter(
        investment=investment,
        date=today
    ).first()
    
    assert snapshot is not None, "Performance snapshot should be created"
    print_success(f"Snapshot created for {today}")
    print(f"  Value: ${snapshot.value:,.2f}")
    
    assert snapshot.value == investment.current_value, "Snapshot value should match current value"
    print_success("Snapshot value matches investment value")
except AssertionError as e:
    print_error(f"Snapshot test failed: {e}")

# Test 10: Test multiple accruals (compound interest)
print_header("Test 10: Test Compound Interest (Multiple Accruals)")
try:
    # Store initial value
    initial_value = Decimal('100000.00')
    
    # Reset investment
    investment.current_value = initial_value
    investment.save()
    
    print(f"  Initial Value: ${initial_value:,.2f}")
    
    # Run accrual 5 times
    for i in range(1, 6):
        call_command('accrue_daily_irr', verbosity=0)
        investment.refresh_from_db()
        print(f"  Day {i}: ${investment.current_value:,.2f}")
    
    # Calculate expected value after 5 days
    annual_rate = Decimal('0.185')
    daily_rate = (1 + annual_rate) ** (Decimal('1') / Decimal('365')) - 1
    expected = initial_value * ((1 + daily_rate) ** 5)
    
    diff = abs(investment.current_value - expected)
    assert diff < Decimal('0.01'), f"Compound interest error. Expected: ${expected}, Got: ${investment.current_value}"
    print_success(f"Compound interest working correctly (5 days)")
    print(f"  Expected: ${expected:,.2f}")
    print(f"  Actual: ${investment.current_value:,.2f}")
    print(f"  Difference: ${diff:,.2f}")
    
except Exception as e:
    print_error(f"Compound interest test failed: {e}")

# Final Summary
print_header("TEST SUMMARY")
print_success("All tests passed!")
print("\nVerified:")
print("  ✓ Investment-Opportunity relationship")
print("  ✓ get_name() and get_sector() methods")
print("  ✓ target_irr property from opportunity")
print("  ✓ Portfolio metrics use target_irr")
print("  ✓ Daily IRR accrual updates current_value")
print("  ✓ total_invested remains fixed")
print("  ✓ Performance snapshots created")
print("  ✓ Compound interest calculation accurate")
print("  ✓ Legacy investments (no opportunity) work")

print("\n" + "="*60)
print("  ALL SYSTEMS OPERATIONAL ✓")
print("="*60)
