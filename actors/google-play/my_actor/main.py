"""Apify Actor entry point: call one PrismCrawl endpoint and store the responses.

Normal runs read the Actor input, call PrismCrawl, and push one dataset item per page. Standby runs serve the same
request over HTTP (see `standby.py`). Everything endpoint-specific lives in `endpoint.py`; no scraping or parsing
happens in this Actor: PrismCrawl does all of it.

This file is shared by every PrismCrawl Actor in this repository. Edit `shared/main.py`, then run
`python scripts/build_actors.py`.
"""

from __future__ import annotations

import asyncio
from typing import Any

from apify import Actor, Event

from .endpoint import build_request
from .prismcrawl import PrismCrawlClient, PrismCrawlError, PrismCrawlResponse, redact
from .runtime import InputError, result_counts, search_pages
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
    # Give the SDK a moment to persist state, then stop immediately so no further (billed) requests start.
    await asyncio.sleep(1)
    await Actor.exit()


async def run_batch() -> None:
    """Run the request described by the Actor input and store the responses in the default dataset."""
    actor_input: dict[str, Any] = await Actor.get_input() or {}
    api_key = actor_input.get('prismcrawlApiKey')
    if not isinstance(api_key, str) or not api_key.strip():
        await Actor.fail(status_message='Missing PrismCrawl API key. Add your key in the "PrismCrawl API key" input.')
        return

    try:
        request = build_request(actor_input)
    except InputError as error:
        await Actor.fail(status_message=f'Invalid input: {redact(str(error), api_key)}')
        return

    if request.ignored_fields:
        Actor.log.warning(f'Ignoring input fields that do not apply here: {", ".join(request.ignored_fields)}.')

    client = PrismCrawlClient(api_key, on_retry=_log_retry)
    Actor.log.info(f'PrismCrawl {request.label} (up to {request.max_pages} page(s)).')

    page_count = 0
    last_request_id = None
    try:
        # The HTTP client is blocking; iterate pages on a worker thread so the event loop stays responsive.
        pages = search_pages(client, request)
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
        f'Saved {page_count} PrismCrawl page(s): {request.label}. Last request ID: {last_request_id}.'
    )


def dataset_item(response: PrismCrawlResponse, page: int) -> dict[str, Any]:
    """Return the PrismCrawl response unchanged, plus the page number and remaining-credits header."""
    return {'page': page, 'credits_remaining': response.credits_remaining, **response.body}


def _log_page(response: PrismCrawlResponse, page: int) -> None:
    results, features, has_next_page = result_counts(response.body)
    Actor.log.info(
        f'Page {page}: {results} results, {features} SERP features, has_next_page={has_next_page}, '
        f'request_id={response.request_id}, credits_remaining={response.credits_remaining}'
    )


def _log_retry(error: PrismCrawlError, attempt: int, delay: float) -> None:
    Actor.log.warning(f'Retrying in {delay:.0f}s (attempt {attempt}) after transient error: {error.describe()}')
