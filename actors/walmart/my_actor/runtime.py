"""Endpoint-agnostic pieces shared by every PrismCrawl Actor.

Each Actor's `endpoint.py` turns its Actor input into an `ActorRequest`: which PrismCrawl path to call, the JSON body,
and how to fetch further pages. This module runs that request and provides small input helpers, so endpoint modules
only contain what is specific to their PrismCrawl endpoint.

Pagination follows the documented PrismCrawl response envelope (https://www.prismcrawl.com/openapi.json): every JSON
response has `data.content.has_next_page`; token-paginated endpoints return `next_page_token` in `data.content` (or in
`data` for Bing).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .prismcrawl import PrismCrawlClient, PrismCrawlResponse

QUERY_MAX_UTF8_BYTES = 8192
TOKEN_PARAM = 'next_page_token'


class InputError(ValueError):
    """Invalid Actor input, detected before calling PrismCrawl."""


@dataclass(frozen=True)
class Pagination:
    """How to request the page after a response whose `has_next_page` is true.

    - `none`: the endpoint returns a single page.
    - `offset`: add `step` to the integer body field `param` (starting from 0).
    - `page`: add 1 to the one-based integer body field `param` (starting from 1).
    - `token`: send the response's `next_page_token`, removing the body fields in `drop_on_token`.
    """

    kind: Literal['none', 'offset', 'page', 'token']
    param: str = ''
    step: int = 1
    drop_on_token: tuple[str, ...] = ()


NO_PAGINATION = Pagination('none')


@dataclass
class ActorRequest:
    """One PrismCrawl call, plus how many pages to follow."""

    path: str
    body: dict[str, Any]
    label: str
    max_pages: int = 1
    pagination: Pagination = field(default=NO_PAGINATION)
    # Input fields that were set but do not apply (for example to the selected mode); logged, then ignored.
    ignored_fields: list[str] = field(default_factory=list)


def search_pages(client: PrismCrawlClient, request: ActorRequest) -> Iterator[PrismCrawlResponse]:
    """Yield up to `request.max_pages` responses. Each one is a separate, billed PrismCrawl request."""
    body = dict(request.body)
    for page_index in range(request.max_pages):
        response = client.post(request.path, body)
        yield response
        if page_index + 1 >= request.max_pages:
            return
        next_body = next_page_body(body, response.body, request.pagination)
        if next_body is None:
            return
        body = next_body


def next_page_body(body: dict[str, Any], response: dict[str, Any], pagination: Pagination) -> dict[str, Any] | None:
    """Return the request body for the next page, or None when there is no next page."""
    data = response.get('data')
    data = data if isinstance(data, dict) else {}
    content = data.get('content')
    content = content if isinstance(content, dict) else {}
    if pagination.kind == 'none' or not content.get('has_next_page'):
        return None
    if pagination.kind == 'offset':
        return {**body, pagination.param: int(body.get(pagination.param) or 0) + pagination.step}
    if pagination.kind == 'page':
        return {**body, pagination.param: int(body.get(pagination.param) or 1) + 1}
    token = content.get(TOKEN_PARAM) or data.get(TOKEN_PARAM)
    if not isinstance(token, str) or not token:
        return None
    next_body = {key: value for key, value in body.items() if key not in pagination.drop_on_token}
    next_body[TOKEN_PARAM] = token
    return next_body


def result_counts(response: dict[str, Any]) -> tuple[int, int, Any]:
    """Return (results, serp_features, has_next_page) for logging."""
    data = response.get('data')
    content = data.get('content') if isinstance(data, dict) else None
    if not isinstance(content, dict):
        return 0, 0, None
    return len(content.get('results') or []), len(content.get('serp_features') or []), content.get('has_next_page')


# Input helpers --------------------------------------------------------------------------------------------------------


def is_set(value: Any) -> bool:
    return value is not None and value not in ('', [])


def clean(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def optional_fields(actor_input: dict[str, Any], *names: str) -> dict[str, Any]:
    """Copy the named input fields that are set, unchanged, under the same name."""
    return {name: clean(actor_input[name]) for name in names if is_set(clean(actor_input.get(name)))}


def required_text(actor_input: dict[str, Any], name: str, *, max_utf8_bytes: int | None = None) -> str:
    value = clean(actor_input.get(name))
    if not isinstance(value, str) or not value:
        raise InputError(f'"{name}" is required.')
    if max_utf8_bytes is not None and len(value.encode()) > max_utf8_bytes:
        raise InputError(f'"{name}" must not exceed {max_utf8_bytes} UTF-8 bytes.')
    return value


def to_int(name: str, value: Any, *, minimum: int | None = None, maximum: int | None = None) -> int:
    if isinstance(value, bool):
        raise InputError(f'"{name}" must be an integer.')
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise InputError(f'"{name}" must be an integer.') from None
    if (minimum is not None and number < minimum) or (maximum is not None and number > maximum):
        bounds = f'between {minimum} and {maximum}' if maximum is not None else f'{minimum} or greater'
        raise InputError(f'"{name}" must be {bounds}.')
    return number


def optional_int(
    actor_input: dict[str, Any], name: str, *, minimum: int | None = None, maximum: int | None = None
) -> int | None:
    value = actor_input.get(name)
    return to_int(name, value, minimum=minimum, maximum=maximum) if is_set(value) else None


def coordinates(actor_input: dict[str, Any]) -> dict[str, float] | None:
    """Build a PrismCrawl `coordinates` object from `latitude`/`longitude` inputs (both or neither)."""
    latitude, longitude = actor_input.get('latitude'), actor_input.get('longitude')
    if not is_set(latitude) and not is_set(longitude):
        return None
    if not (is_set(latitude) and is_set(longitude)):
        raise InputError('Set both "latitude" and "longitude", or neither.')
    try:
        lat, lng = float(latitude), float(longitude)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise InputError('"latitude" and "longitude" must be numbers.') from None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):  # noqa: PLR2004
        raise InputError('"latitude" must be between -90 and 90 and "longitude" between -180 and 180.')
    return {'latitude': lat, 'longitude': lng}


def max_pages(actor_input: dict[str, Any], limit: int) -> int:
    value = actor_input.get('maxPages')
    return to_int('maxPages', value, minimum=1, maximum=limit) if is_set(value) else 1


def choice(actor_input: dict[str, Any], name: str, options: tuple[str, ...], default: str) -> str:
    value = clean(actor_input.get(name)) or default
    if value not in options:
        raise InputError(f'"{name}" must be one of: {", ".join(options)}.')
    return str(value)


def unused_fields(actor_input: dict[str, Any], names: tuple[str, ...]) -> list[str]:
    """Return which of `names` are set, so the caller can report them as ignored."""
    return [name for name in names if is_set(clean(actor_input.get(name)))]
