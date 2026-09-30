"""Yelp: maps Actor input to `POST /v1/yelp/search` (business lookup) or `/v1/yelp/reviews`, selected by `mode`.

Field names and rules follow `Catalog_yelp_Request` and `Catalog_yelp_reviews_Request` in
https://www.prismcrawl.com/openapi.json. Both paginate with a one-based `page`. Business lookup requires exactly one of
`location` or `coordinates` and covers only the first 200 businesses: `(page - 1) × limit` must be less than 200.
"""

from __future__ import annotations

from typing import Any

from .runtime import (
    QUERY_MAX_UTF8_BYTES,
    ActorRequest,
    InputError,
    Pagination,
    choice,
    coordinates,
    max_pages,
    optional_fields,
    optional_int,
    required_text,
    unused_fields,
)

ACTOR_TITLE = 'PrismCrawl Yelp API'
STANDBY_EXAMPLE = {'mode': 'search', 'query': 'coffee', 'location': 'Baltimore, MD'}

MODES = ('search', 'reviews')
PATHS = {'search': '/v1/yelp/search', 'reviews': '/v1/yelp/reviews'}
MODE_FIELDS = {
    'search': ('query', 'location', 'latitude', 'longitude'),
    'reviews': ('id', 'sort_by'),
}
ALL_MODE_FIELDS = tuple(sorted({name for names in MODE_FIELDS.values() for name in names}))
LIMIT_MAX = 100
DEFAULT_SEARCH_LIMIT = 20
LOOKUP_WINDOW = 200
PAGE_MAX = {'search': 200, 'reviews': 1000}
MAX_PAGES_LIMIT = 100


def build_request(actor_input: dict[str, Any]) -> ActorRequest:
    mode = choice(actor_input, 'mode', MODES, 'search')
    body: dict[str, Any] = optional_fields(actor_input, 'language', 'device', 'zero_trace')
    limit = optional_int(actor_input, 'limit', minimum=1, maximum=LIMIT_MAX)
    if limit is not None:
        body['limit'] = limit
    page = optional_int(actor_input, 'page', minimum=1, maximum=PAGE_MAX[mode])
    if page is not None:
        body['page'] = page

    if mode == 'search':
        body['query'] = required_text(actor_input, 'query', max_utf8_bytes=QUERY_MAX_UTF8_BYTES)
        location = optional_fields(actor_input, 'location').get('location')
        coords = coordinates(actor_input)
        if bool(location) == bool(coords):
            raise InputError('Yelp business lookup needs exactly one of "location" or "latitude"/"longitude".')
        if location:
            body['location'] = location
        else:
            body['coordinates'] = coords
        if ((page or 1) - 1) * (limit or DEFAULT_SEARCH_LIMIT) >= LOOKUP_WINDOW:
            raise InputError(
                'Yelp business lookup covers the first 200 businesses: (page - 1) × limit must be under 200.'
            )
        label = f'Yelp business lookup for {body["query"]!r} near {location or coords}'
    else:
        body['id'] = required_text(actor_input, 'id')
        body.update(optional_fields(actor_input, 'sort_by'))
        label = f'Yelp reviews for {body["id"]!r}'

    fields = MODE_FIELDS[mode]
    return ActorRequest(
        path=PATHS[mode],
        body=body,
        label=label,
        max_pages=max_pages(actor_input, MAX_PAGES_LIMIT),
        pagination=Pagination('page', param='page'),
        ignored_fields=unused_fields(actor_input, tuple(name for name in ALL_MODE_FIELDS if name not in fields)),
    )
