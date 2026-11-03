"""
Utility functions for investment calculations.
Handles IRR, risk metrics, and portfolio analytics.
"""

import bisect
import math
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
from scipy.optimize import brentq, newton
from django.db.models import Sum
from django.utils import timezone
import logging

logger = logging.getLogger('investments')

ACTIVE_STATUSES = ['ACTIVE', 'UNDERPERFORMING']

# Benchmark used for alpha and the quarterly comparison (annual %, compounded)
BENCHMARK_ANNUAL_RETURN = Decimal('10.0')


def _active_investments(user):
    from .models import Investment
    return Investment.objects.filter(user=user, status__in=ACTIVE_STATUSES)


def calculate_investment_irr(investment):
    """
    Calculate Internal Rate of Return for an investment.

    Args:
        investment: Investment instance

    Returns:
        Decimal: Annualized IRR as a percentage
    """
    from .models import CapitalActivity
    try:
        activities = list(investment.capital_activities.order_by('date').values_list('activity_type', 'date', 'amount'))
        if not activities:
            return Decimal('0.00')

        # Negative for money paid in (investments, capital calls),
        # positive for money received (distributions, exits)
        cash_flows = []
        dates = []
        for activity_type, activity_date, amount in activities:
            sign = -1 if activity_type in CapitalActivity.OUTFLOW_TYPES else 1
            cash_flows.append(sign * abs(float(amount)))
            dates.append(activity_date)

        # Current value as the terminal cash flow
        cash_flows.append(float(investment.current_value))
        dates.append(timezone.now().date())

        irr = xirr(dates, cash_flows)
        if irr is not None:
            return Decimal(str(round(irr * 100, 2)))
        return Decimal('0.00')

    except Exception as e:
        logger.error(f"Error calculating IRR for {investment.get_name()}: {str(e)}")
        return Decimal('0.00')


def xirr(dates, cash_flows, guess=0.1):
    """
    Calculate XIRR (Extended Internal Rate of Return) for irregular cash flows.

    Args:
        dates: List of dates
        cash_flows: List of cash flows (negative for outflows, positive for inflows)
        guess: Initial guess for IRR

    Returns:
        float: Annualized IRR as a decimal (e.g., 0.15 for 15%), or None if undefined
    """
    if len(dates) != len(cash_flows) or len(dates) < 2:
        return None
    # An IRR only exists when there are both inflows and outflows
    if not (any(cf < 0 for cf in cash_flows) and any(cf > 0 for cf in cash_flows)):
        return None

    first_date = min(dates)
    years = [(d - first_date).days / 365.0 for d in dates]
    if max(years) == 0:
        return None

    def xnpv(rate):
        return sum(cf / (1 + rate) ** t for t, cf in zip(years, cash_flows))

    try:
        result = newton(xnpv, guess, maxiter=100)
        if np.isfinite(result) and result > -1:
            return float(result)
    except (RuntimeError, OverflowError, ZeroDivisionError, ValueError):
        pass

    # Newton can diverge on unusual cash flows; fall back to a bracketed search
    try:
        return float(brentq(xnpv, -0.9999, 100.0, maxiter=200))
    except (ValueError, RuntimeError, OverflowError, ZeroDivisionError):
        return None


def calculate_portfolio_metrics(user):
    """
    Calculate aggregate portfolio metrics for a user.

    Args:
        user: User instance

    Returns:
        dict: Portfolio metrics
    """
    investments = list(_active_investments(user).select_related('opportunity'))

    if not investments:
        return {
            'total_value': Decimal('0.00'),
            'total_invested': Decimal('0.00'),
            'unrealized_gains': Decimal('0.00'),
            'unrealized_gains_percentage': Decimal('0.00'),
            'average_irr': Decimal('0.00'),
            'num_investments': 0,
        }

    total_value = sum((inv.current_value for inv in investments), Decimal('0.00'))
    total_invested = sum((inv.total_invested for inv in investments), Decimal('0.00'))
    unrealized_gains = total_value - total_invested
    unrealized_gains_percentage = (unrealized_gains / total_invested * 100) if total_invested > 0 else Decimal('0.00')

    # Weighted average of the opportunities' target IRRs (weighted by capital invested)
    irr_values = []
    weights = []
    for investment in investments:
        irr = investment.target_irr
        if irr is not None and irr != 0 and investment.total_invested > 0:
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
        'num_investments': len(investments),
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

    sector_data = list(
        _active_investments(user).values('sector').annotate(total=Sum('current_value')).order_by('-total')
    )
    total_value = sum((item['total'] or Decimal('0.00') for item in sector_data), Decimal('0.00'))
    if total_value == 0:
        return []

    sector_names = dict(Investment.SECTOR_CHOICES)
    return [
        {
            'sector': item['sector'],
            'sector_display': sector_names.get(item['sector'], item['sector']),
            'amount': item['total'],
            'percentage': round(item['total'] / total_value * 100, 2),
        }
        for item in sector_data
    ]


def _investment_return_ratios(user):
    """Unrealized return of each active investment, as a fraction (0.12 = 12%)."""
    return [
        float((value - invested) / invested)
        for value, invested in _active_investments(user).values_list('current_value', 'total_invested')
        if invested and invested > 0
    ]


def calculate_portfolio_beta(user, market_returns=None):
    """
    Calculate a simplified portfolio beta (dispersion relative to the market).

    Args:
        user: User instance
        market_returns: unused; reserved for comparing against real market data

    Returns:
        Decimal: Portfolio beta
    """
    returns = _investment_return_ratios(user)
    if not returns:
        return Decimal('0.00')

    # Simplified beta = dispersion of holding returns / market std dev (~15% for the S&P 500)
    market_std = 15.0
    beta = np.std([r * 100 for r in returns]) / market_std
    return Decimal(str(round(float(beta), 2)))


def calculate_sharpe_ratio(user, risk_free_rate=0.04):
    """
    Calculate Sharpe Ratio (risk-adjusted return).

    Args:
        user: User instance
        risk_free_rate: Risk-free rate (default 4% annually)

    Returns:
        Decimal: Sharpe ratio
    """
    rows = list(_active_investments(user).values_list('current_value', 'total_invested'))
    total_invested = sum((invested for _, invested in rows), Decimal('0.00'))
    if total_invested == 0:
        return Decimal('0.00')

    total_value = sum((value for value, _ in rows), Decimal('0.00'))
    portfolio_return = float((total_value - total_invested) / total_invested)

    returns = [float((v - i) / i) for v, i in rows if i and i > 0]
    portfolio_std = np.std(returns) if returns else 0
    if portfolio_std == 0:
        return Decimal('0.00')

    sharpe = (portfolio_return - risk_free_rate) / portfolio_std
    return Decimal(str(round(float(sharpe), 2)))


def _portfolio_daily_returns(user):
    """
    Cash-flow-adjusted (time-weighted) daily returns for the user's portfolio.

    For each pair of consecutive snapshot dates, only investments with a snapshot
    on both dates contribute, and buys, top-ups, sales and exits recorded as
    capital activities are netted out. A purchase therefore doesn't look like a
    gain, and a sale or exit doesn't look like a loss.

    Returns a list of (date, daily_return) sorted by date.
    """
    from .models import PerformanceSnapshot, CapitalActivity

    values = defaultdict(dict)  # investment_id -> {date: value}
    all_dates = set()
    for inv_id, snap_date, value in PerformanceSnapshot.objects.filter(
        investment__user=user
    ).values_list('investment_id', 'date', 'value'):
        values[inv_id][snap_date] = float(value)
        all_dates.add(snap_date)
    if len(all_dates) < 2:
        return []

    # Net capital moved into (+) or out of (-) each position, per date.
    # Activity amounts are negative for capital paid in, positive for proceeds.
    flows = defaultdict(float)
    for inv_id, activity_date, amount in CapitalActivity.objects.filter(
        investment__user=user,
        activity_type__in=['INITIAL_INVESTMENT', 'CAPITAL_CALL', 'PARTIAL_EXIT', 'FULL_EXIT'],
    ).values_list('investment_id', 'date', 'amount'):
        flows[(inv_id, activity_date)] -= float(amount)

    dates = sorted(all_dates)
    returns = []
    for prev_date, cur_date in zip(dates, dates[1:]):
        gain = 0.0
        base = 0.0
        for inv_id, series in values.items():
            if prev_date in series and cur_date in series:
                period_flow = sum(
                    flows.get((inv_id, prev_date + timedelta(days=offset)), 0.0)
                    for offset in range(1, (cur_date - prev_date).days + 1)
                )
                gain += series[cur_date] - series[prev_date] - period_flow
                base += series[prev_date]
        if base > 0:
            returns.append((cur_date, gain / base))
    return returns


def _index_levels(daily_returns, start_date=None):
    """Chain-link daily returns into an index starting at 1.0. Returns (dates, levels)."""
    dates = [start_date] if start_date else []
    levels = [1.0] if start_date else []
    level = 1.0
    for ret_date, ret in daily_returns:
        level *= 1 + ret
        dates.append(ret_date)
        levels.append(level)
    return dates, levels


def calculate_max_drawdown(user):
    """
    Calculate maximum drawdown (largest peak-to-trough decline) of the
    cash-flow-adjusted portfolio index.

    Args:
        user: User instance

    Returns:
        Decimal: Maximum drawdown as a percentage
    """
    _, levels = _index_levels(_portfolio_daily_returns(user))
    if not levels:
        return Decimal('0.00')

    peak = 1.0
    max_dd = 0.0
    for level in levels:
        peak = max(peak, level)
        max_dd = max(max_dd, (peak - level) / peak)

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
    rows = list(_active_investments(user).values_list('current_value', 'total_invested'))
    returns = [float((v - i) / i) for v, i in rows if i and i > 0]
    if not returns:
        return Decimal('0.00')

    # Historical-simulation style percentile across holdings
    var_return = np.percentile(np.array(returns), (1 - confidence) * 100)
    total_value = sum((value for value, _ in rows), Decimal('0.00'))
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
    from .models import CapitalActivity
    from django.db.models import F, Q
    from django.db.models.functions import Coalesce

    exits = Q(activity_type__in=['PARTIAL_EXIT', 'FULL_EXIT'])
    cash = CapitalActivity.objects.filter(
        investment__user=user,
        activity_type__in=['DISTRIBUTION', 'PARTIAL_EXIT', 'FULL_EXIT'],
    ).aggregate(
        received=Sum('amount'),
        distributions=Sum('amount', filter=Q(activity_type='DISTRIBUTION')),
        # Gain on exits = proceeds - cost basis sold. Exits recorded before cost
        # basis was tracked count as break-even.
        exit_gains=Sum(F('amount') - Coalesce('cost_basis', F('amount')), filter=exits),
    )
    cash_received = cash['received'] or Decimal('0.00')
    # Distributions don't reduce cost basis or value here, so they are income
    realized_gains = (cash['distributions'] or Decimal('0.00')) + (cash['exit_gains'] or Decimal('0.00'))

    totals = _active_investments(user).aggregate(
        current_value=Sum('current_value'),
        invested=Sum('total_invested'),
    )
    total_current_value = totals['current_value'] or Decimal('0.00')
    total_invested = totals['invested'] or Decimal('0.00')
    unrealized_gains = total_current_value - total_invested

    return {
        'cash_received': cash_received,
        'realized_gains': realized_gains,
        'unrealized_gains': unrealized_gains,
        'total_return': realized_gains + unrealized_gains,
        'total_invested': total_invested,
        'total_current_value': total_current_value,
    }


def _quarter_start(d):
    return date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)


def calculate_quarterly_performance(user):
    """
    Calculate quarterly portfolio performance with benchmark comparison.

    Covers the current calendar quarter (to date) and the three before it,
    using the cash-flow-adjusted portfolio index.

    Args:
        user: User instance

    Returns:
        list: Quarterly performance data with portfolio and benchmark returns
    """
    from dateutil.relativedelta import relativedelta

    if not _active_investments(user).exists():
        return []

    daily_returns = _portfolio_daily_returns(user)
    dates, levels = _index_levels(daily_returns)

    def level_on(d):
        """Index level at the end of day d (1.0 before any history)."""
        pos = bisect.bisect_right(dates, d)
        return levels[pos - 1] if pos else 1.0

    today = timezone.now().date()
    benchmark_annual = float(BENCHMARK_ANNUAL_RETURN) / 100
    quarters = []
    current_start = _quarter_start(today)
    for i in range(3, -1, -1):
        q_start = current_start - relativedelta(months=3 * i)
        q_end = min(q_start + relativedelta(months=3) - timedelta(days=1), today)
        start_level = level_on(q_start - timedelta(days=1))
        end_level = level_on(q_end)
        portfolio_return = (end_level / start_level - 1) * 100 if start_level else 0.0

        period_days = (q_end - q_start).days + 1
        benchmark_return = ((1 + benchmark_annual) ** (period_days / 365) - 1) * 100

        quarters.append({
            'quarter': f"Q{(q_start.month - 1) // 3 + 1} {q_start.year}",
            'portfolio_return': round(portfolio_return, 2),
            'benchmark_return': round(benchmark_return, 2),
        })

    return quarters


def calculate_alpha(user, benchmark_return=BENCHMARK_ANNUAL_RETURN):
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
    return portfolio_return - benchmark_return


# Each sector belongs to exactly one asset class
ASSET_CLASSES = {
    'Private Equity': {'target': 60, 'sectors': ['HEALTHCARE', 'CONSUMER', 'INDUSTRIAL', 'ENERGY', 'AGRICULTURE']},
    'Venture Capital': {'target': 30, 'sectors': ['TECHNOLOGY', 'FINTECH']},
    'Real Estate': {'target': 10, 'sectors': ['REAL_ESTATE']},
}


def calculate_asset_allocation(user):
    """
    Calculate current asset allocation by asset class.

    Args:
        user: User instance

    Returns:
        list: Asset allocation data with current and target percentages
    """
    by_sector = {
        row['sector']: row['total'] or Decimal('0.00')
        for row in _active_investments(user).values('sector').annotate(total=Sum('current_value'))
    }
    total_value = sum(by_sector.values(), Decimal('0.00'))
    if total_value == 0:
        return []

    allocation = []
    for asset_class, config in ASSET_CLASSES.items():
        class_value = sum((by_sector.get(sector, Decimal('0.00')) for sector in config['sectors']), Decimal('0.00'))
        current_percentage = class_value / total_value * 100
        allocation.append({
            'asset_class': asset_class,
            'current_value': float(class_value),
            'current_percentage': float(current_percentage),
            'target_percentage': config['target'],
            'difference': float(current_percentage - config['target'])
        })

    return allocation


def calculate_rebalancing_recommendations(user, allocation=None):
    """
    Calculate rebalancing recommendations based on target allocation.

    Args:
        user: User instance
        allocation: precomputed calculate_asset_allocation() result (optional)

    Returns:
        list: Rebalancing recommendations
    """
    if allocation is None:
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
    values = list(
        _active_investments(user).order_by('-current_value').values_list('current_value', flat=True)
    )
    total_value = sum(values, Decimal('0.00'))

    if total_value == 0:
        return {
            'top_3_concentration': 0,
            'top_5_concentration': 0,
            'risk_level': 'Low'
        }

    top_3_pct = sum(values[:3], Decimal('0.00')) / total_value * 100
    top_5_pct = sum(values[:5], Decimal('0.00')) / total_value * 100

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


STRESS_SCENARIOS = [
    {'name': 'Market Correction (-20%)', 'impact_percentage': -12.8, 'recovery_months': 18},
    {'name': 'Economic Recession', 'impact_percentage': -18.4, 'recovery_months': 24},
    {'name': 'Interest Rate Shock', 'impact_percentage': -9.2, 'recovery_months': 12},
    {'name': 'Credit Crisis', 'impact_percentage': -22.1, 'recovery_months': 30},
]


def calculate_stress_test_scenarios(user):
    """
    Calculate portfolio performance under stress scenarios.

    Args:
        user: User instance

    Returns:
        list: Stress test scenarios with expected impact
    """
    total_value = _active_investments(user).aggregate(total=Sum('current_value'))['total'] or Decimal('0.00')

    return [
        {
            'scenario': scenario['name'],
            'impact_percentage': scenario['impact_percentage'],
            'expected_loss': float(total_value * Decimal(str(scenario['impact_percentage'] / 100))),
            'recovery_months': scenario['recovery_months']
        }
        for scenario in STRESS_SCENARIOS
    ]


def calculate_portfolio_volatility(user):
    """
    Calculate annualized portfolio volatility from the cash-flow-adjusted
    daily returns.

    Args:
        user: User instance

    Returns:
        dict: Volatility metrics (volatility in annualized %)
    """
    returns = [ret for _, ret in _portfolio_daily_returns(user)]
    volatility = float(np.std(returns)) * math.sqrt(365) * 100 if len(returns) >= 2 else 0.0

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
