"""Google Search endpoint: maps Actor input to `POST /v1/google/search` and paginates.

Field names, types and cross-field rules follow `GoogleSearchRequest` in https://www.prismcrawl.com/openapi.json.
Per-field enums and patterns are enforced by `.actor/input_schema.json` and by PrismCrawl itself (an invalid request is
an uncharged HTTP 400); this module only checks what the input form cannot express, so a run fails before any request
is sent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .prismcrawl import PrismCrawlClient, PrismCrawlResponse

ENDPOINT_PATH = '/v1/google/search'

QUERY_MAX_UTF8_BYTES = 8192
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
    'radius',
    'tbs',
    'tbm',
    'udm',
    'safe',
    'lr',
    'cr',
    'zero_trace',
)
# Tri-state 0/1 controls exposed as string selects in the input form (Apify selects only take strings).
BINARY_FIELDS = ('pws', 'nfpr', 'filter')
# Select values that are integers in the PrismCrawl schema.
INTEGER_SELECT_FIELDS = ('udm',)


class InputError(ValueError):
    """Invalid Actor input, detected before calling PrismCrawl."""


def _is_set(value: Any) -> bool:
    return value is not None and value != ''


def build_request(actor_input: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Validate Actor input and return the PrismCrawl request body plus the number of pages to fetch."""
    query = actor_input.get('query')
    if not isinstance(query, str) or not query.strip():
        raise InputError('"query" is required.')
    query = query.strip()
    if len(query.encode()) > QUERY_MAX_UTF8_BYTES:
        raise InputError(f'"query" must not exceed {QUERY_MAX_UTF8_BYTES} UTF-8 bytes.')

    body: dict[str, Any] = {'query': query}
    for name in PASSTHROUGH_FIELDS:
        value = actor_input.get(name)
        if isinstance(value, str):
            value = value.strip()
        if _is_set(value):
            body[name] = value

    for name in INTEGER_SELECT_FIELDS:
        if name in body:
            body[name] = _to_int(name, body[name])
    for name in BINARY_FIELDS:
        value = actor_input.get(name)
        if _is_set(value):
            body[name] = _to_int(name, value)
            if body[name] not in (0, 1):
                raise InputError(f'"{name}" must be 0 or 1.')

    latitude: Any = actor_input.get('latitude')
    longitude: Any = actor_input.get('longitude')
    if _is_set(latitude) or _is_set(longitude):
        if not (_is_set(latitude) and _is_set(longitude)):
            raise InputError('Set both "latitude" and "longitude", or neither.')
        try:
            body['coordinates'] = {'latitude': float(latitude), 'longitude': float(longitude)}
        except (TypeError, ValueError):
            raise InputError('"latitude" and "longitude" must be numbers.') from None

    _validate_combinations(body)

    start = actor_input.get('start')
    if _is_set(start):
        start = _to_int('start', start)
        if start < 0:
            raise InputError('"start" must be 0 or greater.')
        body['start'] = start

    max_pages = _to_int('maxPages', actor_input.get('maxPages') or 1)
    if not 1 <= max_pages <= MAX_PAGES_LIMIT:
        raise InputError(f'"maxPages" must be between 1 and {MAX_PAGES_LIMIT}.')

    return body, max_pages


def _validate_combinations(body: dict[str, Any]) -> None:
    targeting = [name for name in ('location', 'coordinates', 'uule') if name in body]
    if len(targeting) > 1:
        raise InputError('Use only one of "location", "latitude"/"longitude", or "uule".')
    if 'radius' in body:
        if 'coordinates' not in body:
            raise InputError('"radius" requires "latitude" and "longitude".')
        radius = _to_int('radius', body['radius'])
        limit = RADIUS_MAX_MOBILE if body.get('device') in ('mobile', 'tablet') else RADIUS_MAX_DESKTOP
        if not 1 <= radius <= limit:
            raise InputError(
                f'"radius" must be between 1 and {limit} meters for this device '
                f'(up to {RADIUS_MAX_DESKTOP} for desktop or no device, {RADIUS_MAX_MOBILE} for mobile or tablet).'
            )
        body['radius'] = radius
    if 'tbm' in body and 'udm' in body:
        raise InputError('Use either "tbm" or "udm", not both.')
    if len(body.get('tbs', '')) > TBS_MAX_LENGTH:
        raise InputError(f'"tbs" must not exceed {TBS_MAX_LENGTH} characters.')


def _to_int(name: str, value: Any) -> int:
    if isinstance(value, bool):
        raise InputError(f'"{name}" must be an integer.')
    try:
        return int(value)
    except (TypeError, ValueError):
        raise InputError(f'"{name}" must be an integer.') from None


def search_pages(client: PrismCrawlClient, body: dict[str, Any], max_pages: int) -> Iterator[PrismCrawlResponse]:
    """Yield up to `max_pages` responses, following `has_next_page` and advancing `start`.

    Each yielded page is a separate, billed PrismCrawl search. Errors propagate as `PrismCrawlError`.
    """
    first_start = body.get('start', 0)
    for page_index in range(max_pages):
        page_body = dict(body)
        if page_index:
            page_body['start'] = first_start + page_index * PAGE_SIZE
        response = client.post(ENDPOINT_PATH, page_body)
        yield response
        content = (response.body.get('data') or {}).get('content')
        if not isinstance(content, dict) or not content.get('has_next_page'):
            return
