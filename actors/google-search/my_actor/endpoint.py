"""Google Search: maps Actor input to `POST /v1/google/search`.

Field names, types and cross-field rules follow `GoogleSearchRequest` in https://www.prismcrawl.com/openapi.json.
Per-field enums and patterns are enforced by `.actor/input_schema.json` and by PrismCrawl itself (an invalid request is
an uncharged HTTP 400); this module only checks what the input form cannot express, so a run fails before any request
is sent.
"""

from __future__ import annotations

from typing import Any

from .runtime import (
    QUERY_MAX_UTF8_BYTES,
    ActorRequest,
    InputError,
    Pagination,
    coordinates,
    is_set,
    max_pages,
    optional_fields,
    optional_int,
    required_text,
    to_int,
)

ACTOR_TITLE = 'PrismCrawl Google Search API'
STANDBY_EXAMPLE = {'query': 'best coffee shops in Baltimore', 'gl': 'us'}
PATH = '/v1/google/search'

TBS_MAX_LENGTH = 512
RADIUS_MAX_DESKTOP = 199
RADIUS_MAX_MOBILE = 1000
MAX_PAGES_LIMIT = 10
# PrismCrawl's own pagination example advances `start` by 10 per page:
# https://www.prismcrawl.com/google-search-api-javascript
PAGE_SIZE = 10

# Actor input fields forwarded to PrismCrawl under the same name.
PASSTHROUGH_FIELDS = (
    'gl',
    'hl',
    'google_domain',
    'device',
    'location',
    'uule',
    'tbs',
    'tbm',
    'safe',
    'lr',
    'cr',
    'zero_trace',
)
# Tri-state 0/1 controls exposed as string selects in the input form (Apify selects only take strings).
BINARY_FIELDS = ('pws', 'nfpr', 'filter')


def build_request(actor_input: dict[str, Any]) -> ActorRequest:
    """Validate Actor input and return the PrismCrawl request."""
    query = required_text(actor_input, 'query', max_utf8_bytes=QUERY_MAX_UTF8_BYTES)
    body: dict[str, Any] = {'query': query, **optional_fields(actor_input, *PASSTHROUGH_FIELDS)}

    udm = optional_int(actor_input, 'udm')
    if udm is not None:
        body['udm'] = udm
    for name in BINARY_FIELDS:
        value = optional_int(actor_input, name, minimum=0, maximum=1)
        if value is not None:
            body[name] = value

    coords = coordinates(actor_input)
    if coords:
        body['coordinates'] = coords
    targeting = [name for name in ('location', 'coordinates', 'uule') if name in body]
    if len(targeting) > 1:
        raise InputError('Use only one of "location", "latitude"/"longitude", or "uule".')

    if is_set(actor_input.get('radius')):
        if 'coordinates' not in body:
            raise InputError('"radius" requires "latitude" and "longitude".')
        mobile = body.get('device') in ('mobile', 'tablet')
        limit = RADIUS_MAX_MOBILE if mobile else RADIUS_MAX_DESKTOP
        try:
            body['radius'] = to_int('radius', actor_input['radius'], minimum=1, maximum=limit)
        except InputError:
            raise InputError(
                f'"radius" must be between 1 and {limit} meters for this device '
                f'(up to {RADIUS_MAX_DESKTOP} for desktop or no device, {RADIUS_MAX_MOBILE} for mobile or tablet).'
            ) from None

    if 'tbm' in body and 'udm' in body:
        raise InputError('Use either "tbm" or "udm", not both.')
    if len(body.get('tbs', '')) > TBS_MAX_LENGTH:
        raise InputError(f'"tbs" must not exceed {TBS_MAX_LENGTH} characters.')

    start = optional_int(actor_input, 'start', minimum=0)
    if start is not None:
        body['start'] = start

    return ActorRequest(
        path=PATH,
        body=body,
        label=f'Google search for {query!r}',
        max_pages=max_pages(actor_input, MAX_PAGES_LIMIT),
        pagination=Pagination('offset', param='start', step=PAGE_SIZE),
    )
