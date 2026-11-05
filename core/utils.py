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


def query_list(params, name, upper=True):
    """
    Read a multi-value query parameter given as repeated keys (?a=X&a=Y),
    comma-separated (?a=X,Y) or a mix of both. Blank entries are dropped and
    enum codes are upper-cased. Returns [] when the parameter is absent.
    """
    values = []
    for raw in params.getlist(name):
        for value in raw.split(','):
            value = value.strip()
            if value:
                values.append(value.upper() if upper else value)
    return values


def resolve_ordering(raw, options, default):
    """
    Map an ?ordering= value to a list of order_by() fields.

    `options` maps public names to field lists; a leading '-' on the request
    reverses the first field. Unknown values fall back to `default`.
    """
    key = (raw or '').strip()
    descending = key.startswith('-')
    fields = options.get(key.lstrip('-'))
    if fields is None:
        return list(options[default])
    fields = list(fields)
    if descending:
        first = fields[0]
        fields[0] = first[1:] if first.startswith('-') else f'-{first}'
    return fields
