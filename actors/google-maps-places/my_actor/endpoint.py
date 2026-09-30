"""Google Maps Places: maps Actor input to `POST /v1/google/maps/search`.

Field names and rules follow `GoogleMapsSearchRequest` in https://www.prismcrawl.com/openapi.json: `query` and
`coordinates` (the map center) are required, and each page returns up to 20 places. PrismCrawl documents `start` as a
zero-based offset used "in multiples of 20 for successive 20-place pages".
"""

from __future__ import annotations

from typing import Any

from .runtime import (
    QUERY_MAX_UTF8_BYTES,
    ActorRequest,
    InputError,
    Pagination,
    coordinates,
    max_pages,
    optional_fields,
    optional_int,
    required_text,
)

ACTOR_TITLE = 'PrismCrawl Google Maps Places API'
STANDBY_EXAMPLE = {'query': 'coffee shops', 'latitude': 39.2904, 'longitude': -76.6122}
PATH = '/v1/google/maps/search'

MAX_PAGES_LIMIT = 10
PAGE_SIZE = 20
ZOOM_MIN, ZOOM_MAX = 3, 21


def build_request(actor_input: dict[str, Any]) -> ActorRequest:
    query = required_text(actor_input, 'query', max_utf8_bytes=QUERY_MAX_UTF8_BYTES)
    coords = coordinates(actor_input)
    if coords is None:
        raise InputError('"latitude" and "longitude" (the map center) are required.')
    body: dict[str, Any] = {
        'query': query,
        'coordinates': coords,
        **optional_fields(actor_input, 'gl', 'hl', 'zero_trace'),
    }

    zoom = actor_input.get('zoom')
    if zoom is not None and zoom != '':
        try:
            body['zoom'] = float(zoom)
        except (TypeError, ValueError):
            raise InputError('"zoom" must be a number.') from None
        if not ZOOM_MIN <= body['zoom'] <= ZOOM_MAX:
            raise InputError(f'"zoom" must be between {ZOOM_MIN} and {ZOOM_MAX}.')

    start = optional_int(actor_input, 'start', minimum=0)
    if start is not None:
        body['start'] = start

    return ActorRequest(
        path=PATH,
        body=body,
        label=f'Google Maps search for {query!r} around {coords["latitude"]},{coords["longitude"]}',
        max_pages=max_pages(actor_input, MAX_PAGES_LIMIT),
        pagination=Pagination('offset', param='start', step=PAGE_SIZE),
    )
