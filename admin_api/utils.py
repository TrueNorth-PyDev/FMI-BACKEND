"""
Shared helpers for the admin API views.
"""

from core.utils import parse_positive_int


def paginate(request, queryset, default_page_size=50):
    """
    Slice a queryset using ?page= and ?page_size= (capped at 200).
    Returns (page_items, meta) where meta has count, page and page_size.
    """
    page_size = parse_positive_int(request.query_params.get('page_size'), default_page_size, maximum=200)
    page = parse_positive_int(request.query_params.get('page'), 1)
    start = (page - 1) * page_size
    meta = {'count': queryset.count(), 'page': page, 'page_size': page_size}
    return queryset[start:start + page_size], meta
