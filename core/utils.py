"""
Small helpers shared across apps.
"""


def parse_positive_int(value, default, maximum=None):
    """Parse a query-string integer, falling back to the default on bad input."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < 1:
        return default
    return min(parsed, maximum) if maximum else parsed
