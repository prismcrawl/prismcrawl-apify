"""eBay: maps Actor input to one of PrismCrawl's eBay endpoints, selected by `mode`.

Field names follow the `Catalog_ebay*_Request` schemas in https://www.prismcrawl.com/openapi.json. Search and seller
inventory paginate with a one-based `page`; item details and seller profiles return a single page. Seller inventory
needs `type` (`user` or `store`); without it the seller endpoint returns the profile only.
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

ACTOR_TITLE = 'PrismCrawl eBay API'
STANDBY_EXAMPLE = {'mode': 'search', 'query': 'vintage camera'}

MODES = ('search', 'product', 'seller')
PATHS = {'search': '/v1/ebay/search', 'product': '/v1/ebay/product', 'seller': '/v1/ebay/seller'}
MODE_FIELDS = {
    'search': ('query', 'category_id', 'buying_format', '_udlo', '_udhi', 'show_only', '_stpos', 'LH_ItemCondition'),
    'product': ('id', 'shipping_country'),
    'seller': ('id', 'type', 'limit'),
}
ALL_MODE_FIELDS = tuple(sorted({name for names in MODE_FIELDS.values() for name in names}))
MAX_PAGES_LIMIT = 100


def build_request(actor_input: dict[str, Any]) -> ActorRequest:
    """Validate Actor input and return the PrismCrawl request."""
    mode = choice(actor_input, 'mode', MODES, 'search')
    fields = MODE_FIELDS[mode]
    body: dict[str, Any] = optional_fields(actor_input, 'ebay_domain', 'device', 'zero_trace')

    if mode == 'search':
        if is_set(actor_input.get('query')):
            body['query'] = required_text(actor_input, 'query', max_utf8_bytes=QUERY_MAX_UTF8_BYTES)
        body.update(optional_fields(actor_input, *(name for name in fields if name != 'query')))
        if 'query' not in body and 'category_id' not in body:
            raise InputError('Search needs "query" or "category_id".')
        label = f'eBay search for {body.get("query") or body["category_id"]!r}'
        paginated = True
    else:
        body['id'] = required_text(actor_input, 'id')
        label = f'eBay {mode} {body["id"]!r}'
        if mode == 'product':
            body.update(optional_fields(actor_input, 'shipping_country'))
            paginated = False
        else:
            body.update(optional_fields(actor_input, 'type'))
            limit = optional_int(actor_input, 'limit', minimum=1, maximum=100)
            if limit is not None:
                if 'type' not in body:
                    raise InputError('"limit" applies to seller inventory; set "type" to user or store.')
                body['limit'] = limit
            # Without `type` the endpoint returns the profile only, which is a single page.
            paginated = 'type' in body

    return ActorRequest(
        path=PATHS[mode],
        body=body,
        label=label,
        max_pages=max_pages(actor_input, MAX_PAGES_LIMIT) if paginated else 1,
        pagination=Pagination('page', 'page') if paginated else NO_PAGINATION,
        ignored_fields=unused_fields(actor_input, tuple(name for name in ALL_MODE_FIELDS if name not in fields)),
    )
