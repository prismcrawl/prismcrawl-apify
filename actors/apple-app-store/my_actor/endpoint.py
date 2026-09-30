"""Apple App Store: maps Actor input to one of PrismCrawl's App Store endpoints, selected by `mode`.

Field names and limits follow the `Catalog_apple_app_store*_Request` schemas in https://www.prismcrawl.com/openapi.json.
Searches paginate within Apple's returned inventory (up to 200 apps) and reviews paginate with an opaque
`next_page_token`; product lookups return a single page. The reviews endpoint does not take `language`.
"""

from __future__ import annotations

from typing import Any

from .runtime import (
    NO_PAGINATION,
    QUERY_MAX_UTF8_BYTES,
    ActorRequest,
    Pagination,
    choice,
    max_pages,
    optional_fields,
    optional_int,
    required_text,
    unused_fields,
)

ACTOR_TITLE = 'PrismCrawl Apple App Store API'
STANDBY_EXAMPLE = {'mode': 'search', 'query': 'photo editor', 'country': 'us'}

MODES = ('search', 'product', 'reviews')
PATHS = {
    'search': '/v1/apple/app-store/search',
    'product': '/v1/apple/app-store/product',
    'reviews': '/v1/apple/app-store/reviews',
}
MODE_FIELDS = {
    'search': ('query', 'category', 'limit', 'language'),
    'product': ('id', 'language'),
    'reviews': ('id', 'limit', 'sort_by'),
}
ALL_MODE_FIELDS = tuple(sorted({name for names in MODE_FIELDS.values() for name in names}))
LIMIT_MAX = 100
MAX_PAGES_LIMIT = 10


def build_request(actor_input: dict[str, Any]) -> ActorRequest:
    mode = choice(actor_input, 'mode', MODES, 'search')
    fields = MODE_FIELDS[mode]
    body: dict[str, Any] = optional_fields(actor_input, 'country', 'device', 'zero_trace')

    if mode == 'search':
        body['query'] = required_text(actor_input, 'query', max_utf8_bytes=QUERY_MAX_UTF8_BYTES)
        body.update(optional_fields(actor_input, 'category'))
        label = f'App Store search for {body["query"]!r}'
    else:
        body['id'] = required_text(actor_input, 'id')
        label = f'App Store {mode} for app {body["id"]!r}'
        if mode == 'reviews':
            body.update(optional_fields(actor_input, 'sort_by'))
    if 'language' in fields:
        body.update(optional_fields(actor_input, 'language'))
    if 'limit' in fields:
        limit = optional_int(actor_input, 'limit', minimum=1, maximum=LIMIT_MAX)
        if limit is not None:
            body['limit'] = limit

    paginated = mode != 'product'
    return ActorRequest(
        path=PATHS[mode],
        body=body,
        label=label,
        max_pages=max_pages(actor_input, MAX_PAGES_LIMIT) if paginated else 1,
        pagination=Pagination('token') if paginated else NO_PAGINATION,
        ignored_fields=unused_fields(actor_input, tuple(name for name in ALL_MODE_FIELDS if name not in fields)),
    )
