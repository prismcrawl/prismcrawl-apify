"""Google Play: maps Actor input to one of PrismCrawl's Google Play endpoints, selected by `mode`.

Field names and limits follow the `Catalog_google_play_*_Request` schemas in https://www.prismcrawl.com/openapi.json.
Searches and reviews paginate with an opaque `next_page_token`; product lookups return a single page. The two
`category` parameters mean different things (a Games category for game searches, a store section for product
lookups), so they are separate Actor inputs.
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
    max_pages,
    optional_fields,
    optional_int,
    required_text,
    unused_fields,
)

ACTOR_TITLE = 'PrismCrawl Google Play API'
STANDBY_EXAMPLE = {'mode': 'apps', 'query': 'photo editor', 'country': 'us'}

SEARCH_MODES = ('apps', 'games', 'books', 'movies')
MODES = (*SEARCH_MODES, 'product', 'reviews')
PATHS = {
    'apps': '/v1/google/play/apps/search',
    'games': '/v1/google/play/games/search',
    'books': '/v1/google/play/books/search',
    'movies': '/v1/google/play/movies/search',
    'product': '/v1/google/play/product',
    'reviews': '/v1/google/play/reviews',
}
# Mode-specific inputs; anything listed for other modes only is ignored.
MODE_FIELDS = {
    'apps': ('query', 'limit'),
    'games': ('query', 'gamesCategory', 'limit'),
    'books': ('query', 'limit'),
    'movies': ('query', 'limit'),
    'product': ('id', 'productCategory'),
    'reviews': ('id', 'limit', 'sort_by'),
}
ALL_MODE_FIELDS = tuple(sorted({name for names in MODE_FIELDS.values() for name in names}))
LIMIT_MAX = 100
MAX_PAGES_LIMIT = 100


def build_request(actor_input: dict[str, Any]) -> ActorRequest:
    mode = choice(actor_input, 'mode', MODES, 'apps')
    body: dict[str, Any] = optional_fields(actor_input, 'country', 'language', 'device', 'zero_trace')
    fields = MODE_FIELDS[mode]

    if mode in SEARCH_MODES:
        if mode == 'games':
            query = optional_fields(actor_input, 'query').get('query')
            category = optional_fields(actor_input, 'gamesCategory').get('gamesCategory')
            if not query and not category:
                raise InputError('Game searches need a "query", a "gamesCategory", or both.')
            if query:
                body['query'] = required_text(actor_input, 'query', max_utf8_bytes=QUERY_MAX_UTF8_BYTES)
            if category:
                body['category'] = category
            label = f'Google Play games search for {query or category!r}'
        else:
            body['query'] = required_text(actor_input, 'query', max_utf8_bytes=QUERY_MAX_UTF8_BYTES)
            label = f'Google Play {mode} search for {body["query"]!r}'
    else:
        body['id'] = required_text(actor_input, 'id')
        label = f'Google Play {mode} for {body["id"]!r}'
        if mode == 'product':
            category = optional_fields(actor_input, 'productCategory').get('productCategory')
            if category:
                body['category'] = category
        else:
            body.update(optional_fields(actor_input, 'sort_by'))

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
