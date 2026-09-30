"""Google Shopping Product: maps Actor input to `POST /v1/google/shopping/product`.

Field names follow `Catalog_google_shopping_product_Request` in https://www.prismcrawl.com/openapi.json. `id` is a
`product_id` from a Google Shopping result and `query` must be the Shopping query that returned it. The endpoint
returns a single product, so there is no pagination.
"""

from __future__ import annotations

from typing import Any

from .runtime import QUERY_MAX_UTF8_BYTES, ActorRequest, optional_fields, required_text

ACTOR_TITLE = 'PrismCrawl Google Shopping Product API'
STANDBY_EXAMPLE = {'id': '<product_id from a Google Shopping result>', 'query': 'espresso machine'}
PATH = '/v1/google/shopping/product'


def build_request(actor_input: dict[str, Any]) -> ActorRequest:
    product_id = required_text(actor_input, 'id')
    query = required_text(actor_input, 'query', max_utf8_bytes=QUERY_MAX_UTF8_BYTES)
    body: dict[str, Any] = {
        'id': product_id,
        'query': query,
        **optional_fields(actor_input, 'country', 'language', 'zero_trace'),
    }
    return ActorRequest(path=PATH, body=body, label=f'Google Shopping product {product_id!r} for {query!r}')
