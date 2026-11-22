"""Walmart: maps Actor input to one of PrismCrawl's Walmart endpoints, selected by `mode`.

Field names follow the `Catalog_walmart*_Request` schemas in https://www.prismcrawl.com/openapi.json. Search and reviews
paginate with a one-based `page`; product details and sellers return a single page. Search and reviews both send
`sort`, with different choices, so the input form offers them as separate fields.
"""

from __future__ import annotations

from typing import Any

from .runtime import (
    NO_PAGINATION,
    QUERY_MAX_UTF8_BYTES,
    ActorRequest,
    InputError,
    Pagination,
    choice,
    is_set,
    max_pages,
    optional_fields,
    optional_int,
    required_text,
    unused_fields,
)

ACTOR_TITLE = 'PrismCrawl Walmart API'
STANDBY_EXAMPLE = {'mode': 'search', 'query': 'coffee maker'}

MODES = ('search', 'product', 'sellers', 'reviews')
PATHS = {
    'search': '/v1/walmart/search',
    'product': '/v1/walmart/product',
    'sellers': '/v1/walmart/product/sellers',
    'reviews': '/v1/walmart/reviews',
}
MODE_FIELDS = {
    'search': ('query', 'cat_id', 'sort', 'min_price', 'max_price', 'walmart_domain', 'store_id'),
    'product': ('id', 'store_id'),
    'sellers': ('id', 'store_id'),
    'reviews': ('id', 'rating', 'reviewSort'),
}
ALL_MODE_FIELDS = tuple(sorted({name for names in MODE_FIELDS.values() for name in names}))
MAX_PAGES_LIMIT = 100


def build_request(actor_input: dict[str, Any]) -> ActorRequest:
    """Validate Actor input and return the PrismCrawl request."""
    mode = choice(actor_input, 'mode', MODES, 'search')
    fields = MODE_FIELDS[mode]
    body: dict[str, Any] = optional_fields(actor_input, 'device', 'zero_trace')

    if mode == 'search':
        if is_set(actor_input.get('query')):
            body['query'] = required_text(actor_input, 'query', max_utf8_bytes=QUERY_MAX_UTF8_BYTES)
        body.update(
            optional_fields(actor_input, 'cat_id', 'sort', 'min_price', 'max_price', 'walmart_domain', 'store_id')
        )
        if 'query' not in body and 'cat_id' not in body:
            raise InputError('Search needs "query" or "cat_id".')
        label = f'Walmart search for {body.get("query") or body["cat_id"]!r}'
    else:
        body['id'] = required_text(actor_input, 'id')
        label = f'Walmart {mode} for item {body["id"]!r}'
        if mode in ('product', 'sellers'):
            body.update(optional_fields(actor_input, 'store_id'))
            if mode == 'sellers' and 'store_id' not in body:
                raise InputError('Sellers need "store_id".')
        else:
            rating = optional_int(actor_input, 'rating', minimum=1, maximum=5)
            if rating is not None:
                body['rating'] = rating
            if is_set(actor_input.get('reviewSort')):
                body['sort'] = actor_input['reviewSort']

    paginated = mode in ('search', 'reviews')
    return ActorRequest(
        path=PATHS[mode],
        body=body,
        label=label,
        max_pages=max_pages(actor_input, MAX_PAGES_LIMIT) if paginated else 1,
        pagination=Pagination('page', 'page') if paginated else NO_PAGINATION,
        ignored_fields=unused_fields(actor_input, tuple(name for name in ALL_MODE_FIELDS if name not in fields)),
    )
