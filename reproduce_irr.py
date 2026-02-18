from investments.models import Investment
from marketplace.models import MarketplaceOpportunity
from investments.management.commands.accrue_daily_irr import Command
from decimal import Decimal
from django.utils import timezone
from accounts.models import User
import logging

# Configure logging to see output
logging.basicConfig(level=logging.DEBUG)

def run_test():
    print("Setting up test case...")
    
    # Create a user
    user, _ = User.objects.get_or_create(email="test_irr@example.com", defaults={'username': 'test_irr'})
    
    # Create an opportunity with a realistic target IRR
    opp = MarketplaceOpportunity.objects.create(
        title="Test Opportunity",
        target_irr=20.0,  # 20% IRR
        investment_term_years=5,
        target_raise_amount=Decimal('100000.00'),
    )
    
    # Create an investment with the user's specified starting value
    inv = Investment.objects.create(
        user=user,
        opportunity=opp,
        total_invested=Decimal('10000.00'),
        current_value=Decimal('12000.00'),  # User specified 12000
        investment_date=timezone.now().date(),
        status='ACTIVE'
    )
    
    print(f"\nCreated Investment: {inv.name}")
    print(f"Initial Value: ${inv.current_value}")
    print(f"Target IRR: {inv.target_irr}%")
    
    # Instantiate command and run manual calculation logic to debug
    cmd = Command()
    
    # Test calculation logic
    annual_rate = Decimal(str(inv.target_irr / 100))
    days_in_year = Decimal('365')
    
    # 1. Calculate Daily Rate
    daily_rate = (1 + annual_rate) ** (Decimal('1') / days_in_year) - 1
    print(f"\nCalculation Debug:")
    print(f"Annual Rate: {annual_rate}")
    print(f"Daily Rate (raw): {daily_rate}")
    
    # 2. Apply Growth
    old_value = inv.current_value
    new_value = inv.current_value * (1 + daily_rate)
    growth = new_value - old_value
    
    print(f"Old Value: {old_value}")
    print(f"New Value (calculated): {new_value}")
    print(f"Growth: {growth}")
    
    # Check for overflow/max digits issues
    print(f"New Value Tuple: {new_value.as_tuple()}")
    
    # Try to save using the command's logic
    try:
        # Check validation logic from my previous patch
        if new_value > Decimal('999999999999999999.99'):
            print("(!) WOULD SKIP DUE TO OVERFLOW CHECK")
        
        inv.current_value = new_value
        inv.save(update_fields=['current_value', 'updated_at'])
        print("\n✅ Save Successful!")
        print(f"Saved Value: {inv.current_value}")
        
    except Exception as e:
        print(f"\n❌ Save Failed: {e}")

# Run the test
if __name__ == "__main__":
    import os
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'privcap_hub.settings')
    django.setup()
    run_test()
