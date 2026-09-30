"""Google Maps Reviews: maps Actor input to `POST /v1/google/maps/reviews` or `/v1/google/contributor/reviews`.

Field names and limits follow `Catalog_google_maps_reviews_Request` and `Catalog_google_contributor_reviews_Request`
in https://www.prismcrawl.com/openapi.json. Both endpoints paginate with an opaque `next_page_token`; each supports a
single sort order (relevance for a place, newest for a contributor), so `sort_by` is left to the endpoint default.
"""

from __future__ import annotations

from typing import Any

from .runtime import (
    ActorRequest,
    Pagination,
    choice,
    max_pages,
    optional_fields,
    optional_int,
    required_text,
)

ACTOR_TITLE = 'PrismCrawl Google Maps Reviews API'
STANDBY_EXAMPLE = {'mode': 'place', 'id': 'ChIJN1t_tDeuEmsRUsoyG83frY4', 'limit': 10}

MODES = ('place', 'contributor')
PATHS = {'place': '/v1/google/maps/reviews', 'contributor': '/v1/google/contributor/reviews'}
LIMITS = {'place': 10, 'contributor': 50}
MAX_PAGES_LIMIT = 100


def build_request(actor_input: dict[str, Any]) -> ActorRequest:
    mode = choice(actor_input, 'mode', MODES, 'place')
    review_id = required_text(actor_input, 'id')
    body: dict[str, Any] = {
        'id': review_id,
        **optional_fields(actor_input, 'country', 'language', 'device', 'zero_trace'),
    }
    limit = optional_int(actor_input, 'limit', minimum=1, maximum=LIMITS[mode])
    if limit is not None:
        body['limit'] = limit

    subject = 'place' if mode == 'place' else 'contributor'
    return ActorRequest(
        path=PATHS[mode],
        body=body,
        label=f'Google Maps reviews for {subject} {review_id!r}',
        max_pages=max_pages(actor_input, MAX_PAGES_LIMIT),
        pagination=Pagination('token'),
    )
