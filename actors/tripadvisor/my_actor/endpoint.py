"""Tripadvisor: maps Actor input to one of PrismCrawl's Tripadvisor endpoints, selected by `mode`.

Field names and limits follow the `Catalog_tripadvisor*_Request` schemas in https://www.prismcrawl.com/openapi.json.
Search and reviews paginate with an opaque `next_page_token`; place lookups return a single page. Place and review
lookups take the canonical Tripadvisor URL returned by search as `id`.
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

ACTOR_TITLE = 'PrismCrawl Tripadvisor API'
STANDBY_EXAMPLE = {'mode': 'search', 'query': 'crab cakes', 'location': 'Baltimore, MD'}

MODES = ('search', 'place', 'reviews')
PATHS = {'search': '/v1/tripadvisor/search', 'place': '/v1/tripadvisor/place', 'reviews': '/v1/tripadvisor/reviews'}
MODE_FIELDS = {
    'search': ('query', 'location', 'limit'),
    'place': ('id',),
    'reviews': ('id', 'limit', 'sort_by'),
}
ALL_MODE_FIELDS = tuple(sorted({name for names in MODE_FIELDS.values() for name in names}))
LIMIT_MAX = {'search': 30, 'place': 0, 'reviews': 100}
MAX_PAGES_LIMIT = 100


def build_request(actor_input: dict[str, Any]) -> ActorRequest:
    mode = choice(actor_input, 'mode', MODES, 'search')
    fields = MODE_FIELDS[mode]
    body: dict[str, Any] = optional_fields(actor_input, 'language', 'device', 'zero_trace')

    if mode == 'search':
        body['query'] = required_text(actor_input, 'query', max_utf8_bytes=QUERY_MAX_UTF8_BYTES)
        body.update(optional_fields(actor_input, 'location'))
        label = f'Tripadvisor search for {body["query"]!r}'
    else:
        body['id'] = required_text(actor_input, 'id')
        label = f'Tripadvisor {mode} for {body["id"]!r}'
        if mode == 'reviews':
            body.update(optional_fields(actor_input, 'sort_by'))
    if 'limit' in fields:
        limit = optional_int(actor_input, 'limit', minimum=1, maximum=LIMIT_MAX[mode])
        if limit is not None:
            body['limit'] = limit

    paginated = mode != 'place'
    return ActorRequest(
        path=PATHS[mode],
        body=body,
        label=label,
        max_pages=max_pages(actor_input, MAX_PAGES_LIMIT) if paginated else 1,
        pagination=Pagination('token') if paginated else NO_PAGINATION,
        ignored_fields=unused_fields(actor_input, tuple(name for name in ALL_MODE_FIELDS if name not in fields)),
    )
