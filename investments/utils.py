"""
Utility functions for investment calculations.
Handles IRR, risk metrics, and portfolio analytics.
"""

import numpy as np
from scipy.optimize import newton
from decimal import Decimal
from datetime import datetime, timedelta
from django.db.models import Sum, Avg
from django.utils import timezone
import logging

logger = logging.getLogger('investments')


def calculate_investment_irr(investment):
    """
    Calculate Internal Rate of Return for an investment.
    
    Args:
        investment: Investment instance
        
    Returns:
        Decimal: Annualized IRR as a percentage
    """
    try:
        # Get all capital activities
        activities = investment.capital_activities.order_by('date')
        
        if not activities.exists():
            return Decimal('0.00')
        
        # Build cash flow list
        cash_flows = []
        dates = []
        
        for activity in activities:
            # Negative for outflows (investments, capital calls)
            # Positive for inflows (distributions)
            if activity.activity_type in ['INITIAL_INVESTMENT', 'CAPITAL_CALL']:
                cash_flows.append(float(-abs(activity.amount)))
            else:  # DISTRIBUTION, PARTIAL_EXIT
                cash_flows.append(float(abs(activity.amount)))
            dates.append(activity.date)
        
        # Add current value as final cash flow
        cash_flows.append(float(investment.current_value))
        dates.append(timezone.now().date())
        
        # Calculate IRR using XIRR (date-weighted IRR)
        irr = xirr(dates, cash_flows)
        
        if irr is not None:
            return Decimal(str(round(irr * 100, 2)))
        return Decimal('0.00')
        
    except Exception as e:
        logger.error(f"Error calculating IRR for {investment.name}: {str(e)}")
        return Decimal('0.00')


def xirr(dates, cash_flows, guess=0.1):
    """
    Calculate XIRR (Extended Internal Rate of Return) for irregular cash flows.
    
    Args:
        dates: List of dates
        cash_flows: List of cash flows (negative for outflows, positive for inflows)
        guess: Initial guess for IRR
        
    Returns:
        float: Annualized IRR as a decimal (e.g., 0.15 for 15%)
    """
    if len(dates) != len(cash_flows):
        return None
    
    if len(dates) < 2:
        return None
    
    # Convert dates to days from first date
    first_date = min(dates)
    days = [(d - first_date).days for d in dates]
    
    def xnpv(rate, days, cash_flows):
        """Calculate NPV with irregular periods."""
        return sum([cf / (1 + rate) ** (day / 365.0) for day, cf in zip(days, cash_flows)])
    
    try:
        # Use Newton's method to find the rate where NPV = 0
        result = newton(lambda r: xnpv(r, days, cash_flows), guess, maxiter=100)
        return result
    except:
        return None


def calculate_portfolio_metrics(user):
    """
    Calculate aggregate portfolio metrics for a user.
    
    Args:
        user: User instance
        
    Returns:
        dict: Portfolio metrics
    """
    from .models import Investment
    
    investments = Investment.objects.filter(user=user, status__in=['ACTIVE', 'UNDERPERFORMING'])
    
    if not investments.exists():
        return {
            'total_value': Decimal('0.00'),
            'total_invested': Decimal('0.00'),
            'unrealized_gains': Decimal('0.00'),
            'unrealized_gains_percentage': Decimal('0.00'),
            'average_irr': Decimal('0.00'),
            'num_investments': 0,
        }
    
    # Aggregate calculations
    total_value = investments.aggregate(Sum('current_value'))['current_value__sum'] or Decimal('0.00')
    total_invested = investments.aggregate(Sum('total_invested'))['total_invested__sum'] or Decimal('0.00')
    unrealized_gains = total_value - total_invested
    unrealized_gains_percentage = (unrealized_gains / total_invested * 100) if total_invested > 0 else Decimal('0.00')
    
    # Calculate weighted average IRR
    irr_values = []
    weights = []
    
    for investment in investments:
        irr = investment.calculate_irr()
        if irr is not None and irr != Decimal('0.00'):
            irr_values.append(float(irr))
            weights.append(float(investment.total_invested))
    
    if irr_values:
        average_irr = Decimal(str(round(np.average(irr_values, weights=weights), 2)))
    else:
        average_irr = Decimal('0.00')
    
    return {
        'total_value': total_value,
        'total_invested': total_invested,
        'unrealized_gains': unrealized_gains,
        'unrealized_gains_percentage': unrealized_gains_percentage,
        'average_irr': average_irr,
        'num_investments': investments.count(),
    }


def calculate_sector_allocation(user):
    """
    Calculate portfolio allocation by sector.
    
    Args:
        user: User instance
        
    Returns:
        list: Sector allocation data
    """
    from .models import Investment
    from django.db.models import Sum
    
    investments = Investment.objects.filter(user=user, status__in=['ACTIVE', 'UNDERPERFORMING'])
    
    total_value = investments.aggregate(Sum('current_value'))['current_value__sum'] or Decimal('0.00')
    
    if total_value == 0:
        return []
    
    # Group by sector
    sector_data = investments.values('sector').annotate(
        total=Sum('current_value')
    ).order_by('-total')
    
    allocation = []
    for item in sector_data:
        percentage = (item['total'] / total_value * 100) if total_value > 0 else Decimal('0.00')
        allocation.append({
            'sector': item['sector'],
            'sector_display': dict(Investment.SECTOR_CHOICES).get(item['sector'], item['sector']),
            'amount': item['total'],
            'percentage': round(percentage, 2)
        })
    
    return allocation


def calculate_portfolio_beta(user, market_returns=None):
    """
    Calculate portfolio beta (volatility relative to market).
    
    Args:
        user: User instance
        market_returns: List of market returns (optional, defaults to S&P 500 proxy)
        
    Returns:
        Decimal: Portfolio beta
    """
    # Simplified beta calculation
    # In production, you'd compare portfolio returns to actual market data
    
    from .models import Investment
    
    investments = Investment.objects.filter(user=user, status__in=['ACTIVE', 'UNDERPERFORMING'])
    
    if not investments.exists():
        return Decimal('0.00')
    
    # Calculate portfolio volatility
    returns = []
    for investment in investments:
        gain_pct = float(investment.unrealized_gain_percentage)
        returns.append(gain_pct)
    
    if not returns:
        return Decimal('0.00')
    
    portfolio_std = np.std(returns)
    
    # Assume market std dev of ~15% annually (S&P 500 historical)
    market_std = 15.0
    
    # Simplified beta = portfolio_std / market_std
    beta = portfolio_std / market_std if market_std > 0 else 0.85
    
    return Decimal(str(round(beta, 2)))


def calculate_sharpe_ratio(user, risk_free_rate=0.04):
    """
    Calculate Sharpe Ratio (risk-adjusted return).
    
    Args:
        user: User instance
        risk_free_rate: Risk-free rate (default 4% annually)
        
    Returns:
        Decimal: Sharpe ratio
    """
    metrics = calculate_portfolio_metrics(user)
    
    if metrics['total_invested'] == 0:
        return Decimal('0.00')
    
    # Portfolio return
    portfolio_return = float(metrics['unrealized_gains_percentage']) / 100
    
    # Calculate portfolio standard deviation
    from .models import Investment
    investments = Investment.objects.filter(user=user, status__in=['ACTIVE', 'UNDERPERFORMING'])
    
    returns = [float(inv.unrealized_gain_percentage) / 100 for inv in investments]
    
    if not returns:
        return Decimal('0.00')
    
    portfolio_std = np.std(returns)
    
    if portfolio_std == 0:
        return Decimal('0.00')
    
    # Sharpe Ratio = (Portfolio Return - Risk Free Rate) / Portfolio Std Dev
    sharpe = (portfolio_return - risk_free_rate) / portfolio_std
    
    return Decimal(str(round(sharpe, 2)))


def calculate_max_drawdown(user):
    """
    Calculate maximum drawdown (largest peak-to-trough decline).
    
    Args:
        user: User instance
        
    Returns:
        Decimal: Maximum drawdown as a percentage
    """
    from .models import Investment, PerformanceSnapshot
    
    # Get all performance snapshots across all investments
    snapshots = PerformanceSnapshot.objects.filter(
        investment__user=user
    ).order_by('date')
    
    if not snapshots.exists():
        return Decimal('0.00')
    
    # Aggregate portfolio value by date
    from collections import defaultdict
    portfolio_values = defaultdict(Decimal)
    
    for snapshot in snapshots:
        portfolio_values[snapshot.date] += snapshot.value
    
    # Convert to sorted list
    dates = sorted(portfolio_values.keys())
    values = [float(portfolio_values[d]) for d in dates]
    
    if not values:
        return Decimal('0.00')
    
    # Calculate drawdown
    peak = values[0]
    max_dd = 0
    
    for value in values:
        if value > peak:
            peak = value
        dd = (peak - value) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)
    
    return Decimal(str(round(max_dd * 100, 2)))


def calculate_value_at_risk(user, confidence=0.95, days=30):
    """
    Calculate Value at Risk (potential loss over time period).
    
    Args:
        user: User instance
        confidence: Confidence level (default 95%)
        days: Time period in days (default 30)
        
    Returns:
        Decimal: VaR amount
    """
    from .models import Investment
    
    investments = Investment.objects.filter(user=user, status__in=['ACTIVE', 'UNDERPERFORMING'])
    
    if not investments.exists():
        return Decimal('0.00')
    
    # Calculate portfolio returns
    returns = [float(inv.unrealized_gain_percentage) / 100 for inv in investments]
    
    if not returns:
        return Decimal('0.00')
    
    # Calculate VaR using historical simulation
    returns_array = np.array(returns)
    var_percentile = (1 - confidence) * 100
    var_return = np.percentile(returns_array, var_percentile)
    
    # Get total portfolio value
    total_value = investments.aggregate(Sum('current_value'))['current_value__sum'] or Decimal('0.00')
    
    # VaR amount
    var_amount = abs(float(total_value) * var_return)
    
    return Decimal(str(round(var_amount, 2)))


def calculate_returns_analysis(user):
    """
    Calculate detailed returns analysis including realized and unrealized gains.
    
    Args:
        user: User instance
        
    Returns:
        dict: Returns analysis data
    """
    from .models import Investment, CapitalActivity
    
    investments = Investment.objects.filter(user=user)
    
    # Calculate realized gains from distributions
    distributions = CapitalActivity.objects.filter(
        investment__user=user,
        activity_type__in=['DISTRIBUTION', 'PARTIAL_EXIT']
    )
    
    realized_gains = distributions.aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    
    # Calculate unrealized gains
    active_investments = investments.filter(status__in=['ACTIVE', 'UNDERPERFORMING'])
    total_current_value = active_investments.aggregate(Sum('current_value'))['current_value__sum'] or Decimal('0.00')
    total_invested = active_investments.aggregate(Sum('total_invested'))['total_invested__sum'] or Decimal('0.00')
    unrealized_gains = total_current_value - total_invested
    
    # Total return
    total_return = realized_gains + unrealized_gains
    
    return {
        'realized_gains': realized_gains,
        'unrealized_gains': unrealized_gains,
        'total_return': total_return,
        'total_invested': total_invested,
        'total_current_value': total_current_value,
    }


def calculate_return_attribution(user):
    """
    Calculate return attribution by sector.
    
    Args:
        user: User instance
        
    Returns:
        list: Return attribution by sector
    """
    from .models import Investment
    from django.db.models import Sum
    
    investments = Investment.objects.filter(user=user, status__in=['ACTIVE', 'UNDERPERFORMING'])
    
    if not investments.exists():
        return []
    
    # Group by sector and calculate gains
    attribution = []
    
    for sector_code, sector_name in Investment.SECTOR_CHOICES:
        sector_investments = investments.filter(sector=sector_code)
        
        if not sector_investments.exists():
            continue
        
        # Calculate sector metrics
        sector_invested = sector_investments.aggregate(Sum('total_invested'))['total_invested__sum'] or Decimal('0.00')
        sector_value = sector_investments.aggregate(Sum('current_value'))['current_value__sum'] or Decimal('0.00')
        sector_gain = sector_value - sector_invested
        sector_gain_pct = (sector_gain / sector_invested * 100) if sector_invested > 0 else Decimal('0.00')
        
        attribution.append({
            'sector': sector_code,
            'sector_display': sector_name,
            'invested': sector_invested,
            'current_value': sector_value,
            'gain': sector_gain,
            'gain_percentage': round(sector_gain_pct, 2),
        })
    
    # Sort by gain percentage descending
    attribution.sort(key=lambda x: float(x['gain_percentage']), reverse=True)
    
    return attribution


def get_distribution_history(user):
    """
    Get distribution history for user's investments.
    
    Args:
        user: User instance
        
    Returns:
        list: Distribution history
    """
    from .models import CapitalActivity
    
    distributions = CapitalActivity.objects.filter(
        investment__user=user,
        activity_type__in=['DISTRIBUTION', 'PARTIAL_EXIT']
    ).select_related('investment').order_by('-date')
    
    history = []
    for dist in distributions:
        history.append({
            'id': dist.id,
            'investment_id': dist.investment.id,
            'investment_name': dist.investment.name,
            'amount': dist.amount,
            'date': dist.date,
            'details': dist.details,
            'activity_type': dist.activity_type,
            'activity_type_display': dist.get_activity_type_display(),
        })
    
    return history


def calculate_quarterly_performance(user):
    """
    Calculate quarterly portfolio performance with benchmark comparison.
    
    Args:
        user: User instance
        
    Returns:
        list: Quarterly performance data with portfolio and benchmark returns
    """
    from dateutil.relativedelta import relativedelta
    
    investments = user.investments.filter(status__in=['ACTIVE', 'UNDERPERFORMING'])
    
    if not investments.exists():
        return []
    
    # Get last 4 quarters
    quarters = []
    current_date = timezone.now().date()
    
    for i in range(4):
        quarter_end = current_date - relativedelta(months=i*3)
        quarter_start = quarter_end - relativedelta(months=3)
        
        # Calculate portfolio value at start and end of quarter
        start_value = Decimal('0.00')
        end_value = Decimal('0.00')
        
        for investment in investments:
            # Get snapshots for this quarter
            start_snapshot = investment.performance_snapshots.filter(
                date__lte=quarter_start
            ).order_by('-date').first()
            
            end_snapshot = investment.performance_snapshots.filter(
                date__lte=quarter_end
            ).order_by('-date').first()
            
            if start_snapshot:
                start_value += start_snapshot.value
            if end_snapshot:
                end_value += end_snapshot.value
        
        # Calculate return
        if start_value > 0:
            portfolio_return = ((end_value - start_value) / start_value) * 100
        else:
            portfolio_return = Decimal('0.00')
        
        # Benchmark return (simulated - in production, fetch from market data)
        benchmark_return = portfolio_return - Decimal(str(np.random.uniform(-5, 5)))
        
        quarter_name = f"Q{((quarter_end.month - 1) // 3) + 1} {quarter_end.year}"
        
        quarters.append({
            'quarter': quarter_name,
            'portfolio_return': float(portfolio_return),
            'benchmark_return': float(benchmark_return)
        })
    
    return list(reversed(quarters))


def calculate_alpha(user, benchmark_return=Decimal('10.0')):
    """
    Calculate portfolio alpha (excess return vs benchmark).
    
    Args:
        user: User instance
        benchmark_return: Benchmark return percentage
        
    Returns:
        Decimal: Alpha value
    """
    metrics = calculate_portfolio_metrics(user)
    portfolio_return = metrics.get('unrealized_gains_percentage', Decimal('0.00'))
    
    alpha = portfolio_return - benchmark_return
    return alpha


def calculate_asset_allocation(user):
    """
    Calculate current asset allocation by asset class.
    
    Args:
        user: User instance
        
    Returns:
        list: Asset allocation data with current and target percentages
    """
    investments = user.investments.filter(status__in=['ACTIVE', 'UNDERPERFORMING'])
    
    if not investments.exists():
        return []
    
    total_value = investments.aggregate(total=Sum('current_value'))['total'] or Decimal('0.00')
    
    if total_value == 0:
        return []
    
    # Define asset classes and targets
    asset_classes = {
        'Private Equity': {'target': 60, 'sectors': ['TECHNOLOGY', 'HEALTHCARE', 'CONSUMER']},
        'Venture Capital': {'target': 30, 'sectors': ['FINTECH', 'TECHNOLOGY']},
        'Real Estate': {'target': 10, 'sectors': ['REAL_ESTATE']},
    }
    
    allocation = []
    
    for asset_class, config in asset_classes.items():
        class_value = investments.filter(
            sector__in=config['sectors']
        ).aggregate(total=Sum('current_value'))['total'] or Decimal('0.00')
        
        current_percentage = (class_value / total_value * 100) if total_value > 0 else Decimal('0.00')
        
        allocation.append({
            'asset_class': asset_class,
            'current_value': float(class_value),
            'current_percentage': float(current_percentage),
            'target_percentage': config['target'],
            'difference': float(current_percentage - config['target'])
        })
    
    return allocation


def calculate_rebalancing_recommendations(user):
    """
    Calculate rebalancing recommendations based on target allocation.
    
    Args:
        user: User instance
        
    Returns:
        list: Rebalancing recommendations
    """
    allocation = calculate_asset_allocation(user)
    recommendations = []
    
    for item in allocation:
        difference = item['difference']
        
        if abs(difference) < 2:
            status = 'On Target'
            action = 'Current allocation aligns with target'
        elif difference > 0:
            status = 'Overweight'
            action = f"Consider reducing allocation by {abs(difference):.1f}% to reach target"
        else:
            status = 'Underweight'
            action = f"Consider increasing allocation by {abs(difference):.1f}% to reach target"
        
        recommendations.append({
            'asset_class': item['asset_class'],
            'status': status,
            'action': action,
            'current_percentage': item['current_percentage'],
            'target_percentage': item['target_percentage']
        })
    
    return recommendations


def calculate_concentration_risk(user):
    """
    Calculate portfolio concentration risk.
    
    Args:
        user: User instance
        
    Returns:
        dict: Concentration risk metrics
    """
    investments = user.investments.filter(status__in=['ACTIVE', 'UNDERPERFORMING']).order_by('-current_value')
    
    if not investments.exists():
        return {
            'top_3_concentration': 0,
            'top_5_concentration': 0,
            'risk_level': 'Low'
        }
    
    total_value = investments.aggregate(total=Sum('current_value'))['total'] or Decimal('0.00')
    
    if total_value == 0:
        return {
            'top_3_concentration': 0,
            'top_5_concentration': 0,
            'risk_level': 'Low'
        }
    
    top_3_value = sum([inv.current_value for inv in investments[:3]])
    top_5_value = sum([inv.current_value for inv in investments[:5]])
    
    top_3_pct = (top_3_value / total_value * 100) if total_value > 0 else Decimal('0.00')
    top_5_pct = (top_5_value / total_value * 100) if total_value > 0 else Decimal('0.00')
    
    # Determine risk level
    if top_3_pct > 75:
        risk_level = 'High'
    elif top_3_pct > 50:
        risk_level = 'Medium'
    else:
        risk_level = 'Low'
    
    return {
        'top_3_concentration': float(top_3_pct),
        'top_5_concentration': float(top_5_pct),
        'risk_level': risk_level
    }


def calculate_stress_test_scenarios(user):
    """
    Calculate portfolio performance under stress scenarios.
    
    Args:
        user: User instance
        
    Returns:
        list: Stress test scenarios with expected impact
    """
    metrics = calculate_portfolio_metrics(user)
    total_value = metrics.get('total_value', Decimal('0.00'))
    
    # Define stress scenarios
    scenarios = [
        {
            'name': 'Market Correction (-20%)',
            'impact_percentage': -12.8,
            'recovery_months': 18
        },
        {
            'name': 'Economic Recession',
            'impact_percentage': -18.4,
            'recovery_months': 24
        },
        {
            'name': 'Interest Rate Shock',
            'impact_percentage': -9.2,
            'recovery_months': 12
        },
        {
            'name': 'Credit Crisis',
            'impact_percentage': -22.1,
            'recovery_months': 30
        }
    ]
    
    results = []
    for scenario in scenarios:
        expected_loss = total_value * Decimal(str(scenario['impact_percentage'] / 100))
        
        results.append({
            'scenario': scenario['name'],
            'impact_percentage': scenario['impact_percentage'],
            'expected_loss': float(expected_loss),
            'recovery_months': scenario['recovery_months']
        })
    
    return results


def calculate_portfolio_volatility(user):
    """
    Calculate portfolio volatility based on historical performance.
    
    Args:
        user: User instance
        
    Returns:
        dict: Volatility metrics
    """
    investments = user.investments.filter(status__in=['ACTIVE', 'UNDERPERFORMING'])
    
    if not investments.exists():
        return {
            'volatility': 0.0,
            'risk_level': 'Low'
        }
    
    # Get performance snapshots for the last year
    returns = []
    for investment in investments:
        snapshots = investment.performance_snapshots.order_by('date')
        
        if snapshots.count() >= 2:
            for i in range(1, len(snapshots)):
                prev_value = snapshots[i-1].value
                curr_value = snapshots[i].value
                
                if prev_value > 0:
                    ret = ((curr_value - prev_value) / prev_value) * 100
                    returns.append(float(ret))
    
    if not returns:
        volatility = 0.0
    else:
        volatility = float(np.std(returns))
    
    # Determine risk level
    if volatility > 20:
        risk_level = 'High'
    elif volatility > 10:
        risk_level = 'Moderate'
    else:
        risk_level = 'Low'
    
    return {
        'volatility': round(volatility, 1),
        'risk_level': risk_level
    }


