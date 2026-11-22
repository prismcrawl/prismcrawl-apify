"""YouTube: maps Actor input to one of PrismCrawl's YouTube endpoints, selected by `mode`.

Field names follow the `Catalog_youtube*_Request` schemas in https://www.prismcrawl.com/openapi.json. Search, video
details, and channel listings paginate with an opaque `next_page_token`; transcripts return a single page.
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
    required_text,
    unused_fields,
)

ACTOR_TITLE = 'PrismCrawl YouTube API'
STANDBY_EXAMPLE = {'mode': 'search', 'query': 'espresso machine review'}

MODES = ('search', 'video', 'channel', 'transcript')
PATHS = {
    'search': '/v1/youtube/search',
    'video': '/v1/youtube/video',
    'channel': '/v1/youtube/channel',
    'transcript': '/v1/youtube/transcript',
}
MODE_FIELDS = {
    'search': ('query', 'sp', 'language'),
    'video': ('id', 'language'),
    'channel': ('id', 'tab', 'sort', 'search_query', 'about', 'language'),
    'transcript': ('id', 'language_code', 'title', 'type'),
}
ALL_MODE_FIELDS = tuple(sorted({name for names in MODE_FIELDS.values() for name in names}))
MAX_PAGES_LIMIT = 20


def build_request(actor_input: dict[str, Any]) -> ActorRequest:
    """Validate Actor input and return the PrismCrawl request."""
    mode = choice(actor_input, 'mode', MODES, 'search')
    fields = MODE_FIELDS[mode]
    body: dict[str, Any] = optional_fields(actor_input, 'country', 'device', 'zero_trace')

    if mode == 'search':
        body['query'] = required_text(actor_input, 'query', max_utf8_bytes=QUERY_MAX_UTF8_BYTES)
        label = f'YouTube search for {body["query"]!r}'
    else:
        body['id'] = required_text(actor_input, 'id')
        label = f'YouTube {mode} for {body["id"]!r}'
    body.update(optional_fields(actor_input, *(name for name in fields if name not in ('query', 'id'))))

    paginated = mode != 'transcript'
    return ActorRequest(
        path=PATHS[mode],
        body=body,
        label=label,
        max_pages=max_pages(actor_input, MAX_PAGES_LIMIT) if paginated else 1,
        pagination=Pagination('token') if paginated else NO_PAGINATION,
        ignored_fields=unused_fields(actor_input, tuple(name for name in ALL_MODE_FIELDS if name not in fields)),
    )
