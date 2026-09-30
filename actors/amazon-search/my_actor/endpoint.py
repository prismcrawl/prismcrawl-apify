"""Amazon Search: maps Actor input to `POST /v1/amazon/search`.

Field names and rules follow `AmazonSearchRequest` in https://www.prismcrawl.com/openapi.json. Pagination uses the
one-based `page` field (1 to 1,000). Marketplace-specific rules that the input form cannot express (supported
locales and postal codes per marketplace) are validated by PrismCrawl, which rejects invalid requests without charge.
"""

from __future__ import annotations

from typing import Any

from .runtime import (
    QUERY_MAX_UTF8_BYTES,
    ActorRequest,
    InputError,
    Pagination,
    max_pages,
    optional_fields,
    optional_int,
    required_text,
)

ACTOR_TITLE = 'PrismCrawl Amazon Search API'
STANDBY_EXAMPLE = {'query': 'espresso machine', 'amazon_domain': 'amazon.com'}
PATH = '/v1/amazon/search'

MAX_PAGES_LIMIT = 20
PAGE_MAX = 1000
PASSTHROUGH_FIELDS = (
    'device',
    'amazon_domain',
    'language',
    'delivery_country',
    'postal_code',
    'currency',
    'category_id',
    'sort_by',
    'rh',
    'merchant_id',
    'direct_search',
    'zero_trace',
)


def build_request(actor_input: dict[str, Any]) -> ActorRequest:
    query = required_text(actor_input, 'query', max_utf8_bytes=QUERY_MAX_UTF8_BYTES)
    body: dict[str, Any] = {'query': query, **optional_fields(actor_input, *PASSTHROUGH_FIELDS)}

    # Documented in the schema: amazon.com with US delivery (either may be omitted) only supports USD.
    us_storefront = (
        body.get('amazon_domain', 'amazon.com') == 'amazon.com' and body.get('delivery_country', 'US') == 'US'
    )
    if us_storefront and body.get('currency', 'USD') != 'USD':
        raise InputError('amazon.com with US delivery only supports the USD currency.')

    page = optional_int(actor_input, 'page', minimum=1, maximum=PAGE_MAX)
    if page is not None:
        body['page'] = page

    return ActorRequest(
        path=PATH,
        body=body,
        label=f'Amazon search for {query!r} on {body.get("amazon_domain", "amazon.com")}',
        max_pages=max_pages(actor_input, MAX_PAGES_LIMIT),
        pagination=Pagination('page', param='page'),
    )
