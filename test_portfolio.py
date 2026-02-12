from decimal import Decimal
from investments.utils import calculate_portfolio_metrics
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.filter(email='test@example.com').first()

# Test portfolio metrics
metrics = calculate_portfolio_metrics(user)

print("Portfolio Metrics Test:")
print(f"  Total Value: ${metrics['total_value']}")
print(f"  Total Invested: ${metrics['total_invested']}")
print(f"  Average IRR: {metrics['average_irr']}%")
print(f"  Num Investments: {metrics['num_investments']}")

# The IRR should be from opportunity target_irr
assert metrics['average_irr'] == Decimal('20.0'), f"Expected 20.0%, got {metrics['average_irr']}%"
print("✓ Portfolio metrics use opportunity target_irr correctly!")
