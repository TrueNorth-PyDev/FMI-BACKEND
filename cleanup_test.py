from decimal import Decimal
from investments.models import Investment
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.filter(email='test@example.com').first()

# List all investments for the test user
print("All investments for test user:")
investments = Investment.objects.filter(user=user, status__in=['ACTIVE', 'UNDERPERFORMING'])
for inv in investments:
    print(f"\nInvestment ID: {inv.id}")
    print(f"  Name: {inv.get_name()}")
    print(f"  Opportunity: {inv.opportunity}")
    print(f"  Target IRR: {inv.target_irr}")
    print(f"  Total Invested: ${inv.total_invested}")
    print(f"  Status: {inv.status}")

# Clean up old test data and recreate
print("\n\nCleaning up old investments...")
Investment.objects.filter(user=user).delete()
print("✓ Cleaned")
