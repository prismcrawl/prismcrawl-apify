"""Bing Search: maps Actor input to `POST /v1/microsoft/search`.

Field names and rules follow `MicrosoftSearchRequest` in https://www.prismcrawl.com/openapi.json. Later pages are
requested with the opaque `next_page_token` from the previous response (PrismCrawl rejects `first` values greater
than 1 without a matching token), so `first` is not exposed.
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
    required_text,
)

ACTOR_TITLE = 'PrismCrawl Bing Search API'
STANDBY_EXAMPLE = {'query': 'best coffee shops in Baltimore', 'cc': 'us'}
PATH = '/v1/microsoft/search'

MAX_PAGES_LIMIT = 10
PASSTHROUGH_FIELDS = ('device', 'safe', 'cc', 'setlang', 'tbs', 'zero_trace')


def build_request(actor_input: dict[str, Any]) -> ActorRequest:
    query = required_text(actor_input, 'query', max_utf8_bytes=QUERY_MAX_UTF8_BYTES)
    body: dict[str, Any] = {'query': query, **optional_fields(actor_input, *PASSTHROUGH_FIELDS)}
    coords = coordinates(actor_input)
    if coords:
        body['coordinates'] = coords
    # Documented: Bing has day-level precision, so hour ranges (qdr:h) are rejected.
    if str(body.get('tbs', '')).startswith('qdr:h'):
        raise InputError('Bing does not support hour time ranges ("qdr:h"); use days or longer, such as "qdr:d".')

    return ActorRequest(
        path=PATH,
        body=body,
        label=f'Bing search for {query!r}',
        max_pages=max_pages(actor_input, MAX_PAGES_LIMIT),
        pagination=Pagination('token', drop_on_token=('first',)),
    )
