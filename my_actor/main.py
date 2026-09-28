"""Apify Actor entry point: run a Google search through the PrismCrawl API.

Normal runs read the Actor input, call PrismCrawl, and push one dataset item per results page. Standby runs serve the
same search over HTTP (see `standby.py`). No searching or parsing happens here: PrismCrawl does all of it.
"""

from __future__ import annotations

import asyncio
from typing import Any

from apify import Actor, Event

from .google_search import InputError, build_request, search_pages
from .prismcrawl import PrismCrawlClient, PrismCrawlError, PrismCrawlResponse, redact
from .standby import serve_standby


async def main() -> None:
    """Define a main entry point for the Apify Actor."""
    async with Actor:
        Actor.on(Event.ABORTING, _on_aborting)
        if Actor.configuration.meta_origin == 'STANDBY':
            await serve_standby(Actor.configuration.web_server_port)
            return
        await run_batch()


async def _on_aborting() -> None:
    # Give the SDK a moment to persist state, then stop immediately so no further (billed) searches start.
    await asyncio.sleep(1)
    await Actor.exit()


async def run_batch() -> None:
    """Run the search described by the Actor input and store the results in the default dataset."""
    actor_input: dict[str, Any] = await Actor.get_input() or {}
    api_key = actor_input.get('prismcrawlApiKey')
    if not isinstance(api_key, str) or not api_key.strip():
        await Actor.fail(status_message='Missing PrismCrawl API key. Add your key in the "PrismCrawl API key" input.')
        return

    try:
        body, max_pages = build_request(actor_input)
    except InputError as error:
        await Actor.fail(status_message=f'Invalid input: {redact(str(error), api_key)}')
        return

    client = PrismCrawlClient(api_key, on_retry=_log_retry)
    Actor.log.info(f'Searching Google via PrismCrawl for {body["query"]!r} (up to {max_pages} page(s)).')

    page_count = 0
    last_request_id = None
    try:
        # The HTTP client is blocking; iterate pages on a worker thread so the event loop stays responsive.
        pages = search_pages(client, body, max_pages)
        while (response := await asyncio.to_thread(next, pages, None)) is not None:
            page_count += 1
            last_request_id = response.request_id
            await Actor.push_data(dataset_item(response, page_count))
            _log_page(response, page_count)
    except PrismCrawlError as error:
        message = client.redact(error.describe())
        Actor.log.error(message)
        if page_count:
            message = f'{message} {page_count} earlier page(s) were saved to the dataset.'
        await Actor.fail(status_message=message)
        return

    await Actor.set_status_message(
        f'Saved {page_count} PrismCrawl results page(s) for {body["query"]!r}. Last request ID: {last_request_id}.'
    )


def dataset_item(response: PrismCrawlResponse, page: int) -> dict[str, Any]:
    """Return the PrismCrawl response unchanged, plus the page number and remaining-credits header."""
    return {'page': page, 'credits_remaining': response.credits_remaining, **response.body}


def _log_page(response: PrismCrawlResponse, page: int) -> None:
    content = (response.body.get('data') or {}).get('content') or {}
    Actor.log.info(
        f'Page {page}: {len(content.get("results") or [])} results, '
        f'{len(content.get("serp_features") or [])} SERP features, '
        f'has_next_page={content.get("has_next_page")}, request_id={response.request_id}, '
        f'credits_remaining={response.credits_remaining}'
    )


def _log_retry(error: PrismCrawlError, attempt: int, delay: float) -> None:
    Actor.log.warning(f'Retrying in {delay:.0f}s (attempt {attempt}) after transient error: {error.describe()}')
