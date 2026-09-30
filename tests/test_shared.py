"""Tests for the shared runtime (HTTP transport, run loop, Standby server, pagination).

The shared code is exercised through the Google Search Actor's copy; `test_generated.py` checks that every Actor's copy
is identical. Run all tests with:

    python -m unittest discover -s tests -t .
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import threading
import unittest
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from http.server import ThreadingHTTPServer
from typing import Any
from unittest import mock

from tests.helpers import API_KEY, REQUEST_ID, FakePrismCrawl, error_body, load_actor, search_body

main = load_actor('google-search', 'main')
prismcrawl = load_actor('google-search', 'prismcrawl')
runtime = load_actor('google-search', 'runtime')
standby = load_actor('google-search', 'standby')
PrismCrawlClient = prismcrawl.PrismCrawlClient
PrismCrawlError = prismcrawl.PrismCrawlError


def make_client(**kwargs: Any) -> tuple[PrismCrawlClient, list[float]]:
    sleeps: list[float] = []
    return PrismCrawlClient(API_KEY, sleep=sleeps.append, **kwargs), sleeps


class PrismCrawlClientTests(unittest.TestCase):
    def post(self, fake: FakePrismCrawl, **kwargs: Any) -> tuple[Any, list[float]]:
        client, sleeps = make_client(**kwargs)
        with mock.patch.object(urllib.request, 'urlopen', fake):
            return client.post('/v1/google/search', {'query': 'coffee'}), sleeps

    def assert_error(self, fake: FakePrismCrawl, status: int, code: str) -> tuple[PrismCrawlError, list[float]]:
        client, sleeps = make_client()
        with mock.patch.object(urllib.request, 'urlopen', fake), self.assertRaises(PrismCrawlError) as ctx:
            client.post('/v1/google/search', {'query': 'coffee'})
        self.assertEqual(ctx.exception.status, status)
        self.assertEqual(ctx.exception.code, code)
        return ctx.exception, sleeps

    def test_successful_search_sends_documented_request(self) -> None:
        fake = FakePrismCrawl((200, search_body()))
        response, sleeps = self.post(fake)
        request = fake.requests[0]
        self.assertEqual(request.full_url, 'https://api.prismcrawl.com/v1/google/search')
        self.assertEqual(request.get_method(), 'POST')
        self.assertEqual(request.get_header('Content-type'), 'application/json')
        self.assertEqual(request.get_header('X-api-key'), API_KEY)
        self.assertEqual(fake.json_bodies(), [{'query': 'coffee'}])
        self.assertEqual(response.status, 200)
        self.assertEqual(sleeps, [])

    def test_successful_response_parsing(self) -> None:
        response, _ = self.post(FakePrismCrawl((200, search_body(has_next_page=True))))
        self.assertEqual(response.body, search_body(has_next_page=True))
        self.assertEqual(response.credits_remaining, 99)
        content = response.body['data']['content']
        self.assertEqual(content['results'][0]['rank'], 1)
        self.assertEqual(content['serp_features'][0]['type'], 'people_also_ask')
        self.assertTrue(content['has_next_page'])

    def test_request_id_preserved_on_success_and_error(self) -> None:
        response, _ = self.post(FakePrismCrawl((200, search_body())))
        self.assertEqual(response.request_id, REQUEST_ID)
        error, _ = self.assert_error(
            FakePrismCrawl((400, error_body('invalid_request', 'bad'))), 400, 'invalid_request'
        )
        self.assertEqual(error.request_id, REQUEST_ID)
        self.assertIn(REQUEST_ID, error.describe())

    def test_request_id_falls_back_to_header_when_body_is_not_json(self) -> None:
        fake = FakePrismCrawl(*[(502, None)] * 4)
        error, _ = self.assert_error(fake, 502, 'http_502')
        self.assertEqual(error.request_id, REQUEST_ID)

    def test_missing_api_key_rejected_before_any_request(self) -> None:
        for key in ('', '   ', None):
            with self.subTest(key=key), self.assertRaises(ValueError):
                PrismCrawlClient(key)  # type: ignore[arg-type]

    def test_invalid_api_key_not_retried(self) -> None:
        fake = FakePrismCrawl((401, error_body('invalid_api_key', 'invalid api key')))
        error, sleeps = self.assert_error(fake, 401, 'invalid_api_key')
        self.assertEqual((len(fake.requests), sleeps), (1, []))
        self.assertIn('API key is missing, invalid', error.describe())

    def test_invalid_request_not_retried(self) -> None:
        fake = FakePrismCrawl((400, error_body('invalid_request', 'query is required')))
        error, sleeps = self.assert_error(fake, 400, 'invalid_request')
        self.assertEqual((len(fake.requests), sleeps), (1, []))
        self.assertIn('query is required', error.describe())

    def test_insufficient_credits_not_retried_and_distinguished(self) -> None:
        fake = FakePrismCrawl((402, error_body('credits_exhausted', 'no credits remaining')))
        error, sleeps = self.assert_error(fake, 402, 'credits_exhausted')
        self.assertEqual((len(fake.requests), sleeps), (1, []))
        self.assertIn('no credits remaining', error.describe())
        self.assertNotIn('API key is missing', error.describe())

    def test_rate_limit_retried_then_succeeds(self) -> None:
        reset_at = (datetime.now(UTC) + timedelta(seconds=8)).strftime('%Y-%m-%dT%H:%M:%SZ')
        fake = FakePrismCrawl(
            (429, error_body('quota_exceeded', 'rate limit exceeded', rule='10s', reset_at=reset_at)),
            (200, search_body()),
        )
        response, sleeps = self.post(fake)
        self.assertEqual(response.request_id, REQUEST_ID)
        self.assertEqual(len(fake.requests), 2)
        self.assertEqual(len(sleeps), 1)
        self.assertGreater(sleeps[0], 5)  # waits for reset_at rather than the 2 s base backoff
        self.assertLessEqual(sleeps[0], prismcrawl.RATE_LIMIT_MAX_WAIT_SECS)

    def test_rate_limit_gives_up_after_max_retries(self) -> None:
        fake = FakePrismCrawl(*[(429, error_body('quota_exceeded', 'rate limit exceeded', rule='10s'))] * 4)
        error, sleeps = self.assert_error(fake, 429, 'quota_exceeded')
        self.assertEqual(len(fake.requests), 1 + prismcrawl.DEFAULT_MAX_RETRIES)
        self.assertEqual(sleeps, [2.0, 4.0, 8.0])
        self.assertIn('Rate-limit rule: 10s', error.describe())

    def test_server_error_retried_then_succeeds(self) -> None:
        fake = FakePrismCrawl((500, error_body('overloaded', 'service temporarily overloaded')), (200, search_body()))
        response, sleeps = self.post(fake)
        self.assertEqual((response.status, len(fake.requests), sleeps), (200, 2, [2.0]))

    def test_server_error_exhausts_retries(self) -> None:
        body = error_body('internal_failure', 'request failed. no quota has been deducted')
        fake = FakePrismCrawl(*[(500, body)] * 4)
        error, _ = self.assert_error(fake, 500, 'internal_failure')
        self.assertEqual(len(fake.requests), 4)
        self.assertIn('No credit was charged', error.describe())

    def test_timeout_is_not_retried(self) -> None:
        fake = FakePrismCrawl(urllib.error.URLError(TimeoutError('timed out')), (200, search_body()))
        client, sleeps = make_client()
        with mock.patch.object(urllib.request, 'urlopen', fake), self.assertRaises(PrismCrawlError) as ctx:
            client.post('/v1/google/search', {'query': 'coffee'})
        self.assertEqual((ctx.exception.code, len(fake.requests), sleeps), ('timeout', 1, []))
        self.assertIn('request history', ctx.exception.describe())

    def test_connection_refused_is_retried(self) -> None:
        fake = FakePrismCrawl(urllib.error.URLError(socket.gaierror('dns failure')), (200, search_body()))
        response, sleeps = self.post(fake)
        self.assertEqual((response.status, sleeps), (200, [2.0]))

    def test_api_key_redacted_from_error_messages(self) -> None:
        fake = FakePrismCrawl((401, error_body('invalid_api_key', f'invalid api key {API_KEY}')))
        error, _ = self.assert_error(fake, 401, 'invalid_api_key')
        self.assertNotIn(API_KEY, error.describe())
        self.assertNotIn(API_KEY, repr(error))
        self.assertIn(prismcrawl.REDACTED, error.describe())


def catalog_body(*, has_next_page: bool, token: str | None = None, token_in_data: bool = False) -> dict[str, Any]:
    content: dict[str, Any] = {'search_parameters': {}, 'results': [{'id': 'r1'}], 'has_next_page': has_next_page}
    data: dict[str, Any] = {'format': 'json', 'content': content}
    if token:
        (data if token_in_data else content)['next_page_token'] = token
    return {'success': True, 'request_id': REQUEST_ID, 'data': data}


class PaginationTests(unittest.TestCase):
    def pages(self, request: Any, *responses: dict[str, Any]) -> list[dict[str, Any]]:
        fake = FakePrismCrawl(*[(200, body) for body in responses])
        client, _ = make_client()
        with mock.patch.object(urllib.request, 'urlopen', fake):
            list(runtime.search_pages(client, request))
        return fake.json_bodies()

    def request(self, pagination: Any, body: dict[str, Any], max_pages: int = 5) -> Any:
        return runtime.ActorRequest('/v1/x', body, 'test', max_pages=max_pages, pagination=pagination)

    def test_offset_follows_has_next_page(self) -> None:
        request = self.request(runtime.Pagination('offset', param='start', step=10), {'query': 'q', 'start': 20})
        bodies = self.pages(request, search_body(has_next_page=True), search_body(has_next_page=False))
        self.assertEqual([b.get('start') for b in bodies], [20, 30])

    def test_offset_respects_max_pages(self) -> None:
        request = self.request(runtime.Pagination('offset', param='start', step=20), {'query': 'q'}, max_pages=2)
        bodies = self.pages(request, *[search_body(has_next_page=True)] * 2)
        self.assertEqual([b.get('start') for b in bodies], [None, 20])

    def test_page_increments_from_one(self) -> None:
        request = self.request(runtime.Pagination('page', param='page'), {'query': 'q'}, max_pages=3)
        bodies = self.pages(request, *[catalog_body(has_next_page=True)] * 3)
        self.assertEqual([b.get('page') for b in bodies], [None, 2, 3])

    def test_token_from_content_replaces_dropped_fields(self) -> None:
        request = self.request(runtime.Pagination('token', drop_on_token=('first',)), {'query': 'q', 'first': 1})
        bodies = self.pages(
            request, catalog_body(has_next_page=True, token='tok-1'), catalog_body(has_next_page=False, token='tok-2')
        )
        self.assertEqual(bodies, [{'query': 'q', 'first': 1}, {'query': 'q', 'next_page_token': 'tok-1'}])

    def test_token_in_data_is_used_for_bing(self) -> None:
        request = self.request(runtime.Pagination('token'), {'query': 'q'})
        bodies = self.pages(
            request,
            catalog_body(has_next_page=True, token='bing', token_in_data=True),
            catalog_body(has_next_page=False),
        )
        self.assertEqual(bodies[1]['next_page_token'], 'bing')

    def test_token_missing_stops_even_if_has_next_page(self) -> None:
        request = self.request(runtime.Pagination('token'), {'query': 'q'})
        self.assertEqual(len(self.pages(request, catalog_body(has_next_page=True))), 1)

    def test_no_pagination_makes_one_request(self) -> None:
        request = self.request(runtime.NO_PAGINATION, {'id': 'x'})
        self.assertEqual(len(self.pages(request, catalog_body(has_next_page=True, token='t'))), 1)


class FakeActor:
    """Stands in for `apify.Actor` in `run_batch`."""

    def __init__(self, actor_input: dict[str, Any] | None) -> None:
        self.actor_input = actor_input
        self.items: list[dict[str, Any]] = []
        self.failed_with: str | None = None
        self.status_message: str | None = None
        self.log = logging.getLogger('fake-actor')

    async def get_input(self) -> dict[str, Any] | None:
        return self.actor_input

    async def push_data(self, item: dict[str, Any]) -> None:
        self.items.append(item)

    async def fail(self, *, status_message: str) -> None:
        self.failed_with = status_message

    async def set_status_message(self, message: str) -> None:
        self.status_message = message


class RunBatchTests(unittest.TestCase):
    def run_batch(self, actor_input: dict[str, Any] | None, fake: FakePrismCrawl) -> tuple[FakeActor, list[str]]:
        actor = FakeActor(actor_input)
        with (
            mock.patch.object(main, 'Actor', actor),
            mock.patch.object(urllib.request, 'urlopen', fake),
            mock.patch.object(prismcrawl.time, 'sleep'),
            self.assertLogs('fake-actor', level='DEBUG') as logs,
        ):
            actor.log.debug('start')
            asyncio.run(main.run_batch())
        return actor, logs.output

    def test_successful_search_pushes_full_response(self) -> None:
        fake = FakePrismCrawl((200, search_body()))
        actor, _ = self.run_batch({'prismcrawlApiKey': API_KEY, 'query': 'best coffee shops in Baltimore'}, fake)
        self.assertIsNone(actor.failed_with)
        self.assertEqual(actor.items, [{'page': 1, 'credits_remaining': 99, **search_body()}])
        self.assertEqual(actor.items[0]['request_id'], REQUEST_ID)
        self.assertIn(REQUEST_ID, actor.status_message or '')

    def test_missing_api_key_fails_without_request(self) -> None:
        fake = FakePrismCrawl()
        actor, _ = self.run_batch({'query': 'coffee'}, fake)
        self.assertIn('Missing PrismCrawl API key', actor.failed_with or '')
        self.assertEqual((fake.requests, actor.items), ([], []))

    def test_invalid_input_fails_without_request(self) -> None:
        fake = FakePrismCrawl()
        actor, _ = self.run_batch({'prismcrawlApiKey': API_KEY, 'query': 'q', 'tbm': 'nws', 'udm': '12'}, fake)
        self.assertIn('Invalid input', actor.failed_with or '')
        self.assertEqual(fake.requests, [])

    def test_error_fails_run_with_request_id(self) -> None:
        fake = FakePrismCrawl((402, error_body('credits_exhausted', 'no credits remaining')))
        actor, _ = self.run_batch({'prismcrawlApiKey': API_KEY, 'query': 'coffee'}, fake)
        self.assertIn('credits_exhausted', actor.failed_with or '')
        self.assertIn(REQUEST_ID, actor.failed_with or '')
        self.assertEqual(actor.items, [])

    def test_error_after_first_page_keeps_saved_pages(self) -> None:
        fake = FakePrismCrawl((200, search_body(has_next_page=True)), (402, error_body('credits_exhausted', 'none')))
        actor, _ = self.run_batch({'prismcrawlApiKey': API_KEY, 'query': 'coffee', 'maxPages': 3}, fake)
        self.assertEqual(len(actor.items), 1)
        self.assertIn('1 earlier page(s) were saved', actor.failed_with or '')

    def test_api_key_never_logged_or_stored(self) -> None:
        fake = FakePrismCrawl(
            (500, error_body('internal_failure', f'echo {API_KEY}')),
            (401, error_body('invalid_api_key', f'bad key {API_KEY}')),
        )
        actor, logs = self.run_batch({'prismcrawlApiKey': API_KEY, 'query': 'coffee'}, fake)
        self.assertEqual(fake.requests[0].get_header('X-api-key'), API_KEY)  # the key is only sent to PrismCrawl
        self.assertTrue(any('Retrying' in line for line in logs))
        for text in [*logs, actor.failed_with or '', json.dumps(actor.items)]:
            self.assertNotIn(API_KEY, text)


class StandbyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), standby.StandbyHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base_url = f'http://127.0.0.1:{self.server.server_port}/'
        self.real_urlopen = urllib.request.urlopen

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def call(
        self, method: str, body: dict[str, Any] | None = None, headers: dict[str, str] | None = None
    ) -> tuple[int, bytes]:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base_url, data=data, method=method, headers=headers or {})  # noqa: S310
        try:
            with self.real_urlopen(request, timeout=10) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()

    def test_readiness_probe(self) -> None:
        self.assertEqual(self.call('GET', headers={standby.READINESS_PROBE_HEADER: '1'}), (200, b'ok'))

    def test_post_requires_api_key_header(self) -> None:
        status, raw = self.call('POST', {'query': 'coffee'})
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(raw)['error']['code'], 'missing_api_key')

    def test_post_returns_prismcrawl_response_and_errors_unchanged(self) -> None:
        fake = FakePrismCrawl((200, search_body()), (402, error_body('credits_exhausted', 'no credits remaining')))
        with mock.patch.object(urllib.request, 'urlopen', fake):
            ok = self.call('POST', {'query': 'coffee', 'gl': 'us'}, {standby.API_KEY_HEADER: API_KEY})
            no_credits = self.call('POST', {'query': 'coffee'}, {standby.API_KEY_HEADER: API_KEY})
        self.assertEqual((ok[0], json.loads(ok[1])), (200, search_body()))
        self.assertEqual(
            (no_credits[0], json.loads(no_credits[1])), (402, error_body('credits_exhausted', 'no credits remaining'))
        )
        self.assertEqual(fake.json_bodies()[0], {'query': 'coffee', 'gl': 'us'})

    def test_post_rejects_key_in_body(self) -> None:
        status, raw = self.call('POST', {'query': 'q', 'prismcrawlApiKey': API_KEY}, {standby.API_KEY_HEADER: API_KEY})
        self.assertEqual(status, 400)
        self.assertNotIn(API_KEY.encode(), raw)


if __name__ == '__main__':
    unittest.main()


class StandbyRequestTests(unittest.TestCase):
    def test_token_is_applied_on_token_endpoints(self) -> None:
        bing = load_actor('bing-search', 'standby')
        request = bing.standby_request({'query': 'q', 'next_page_token': 'tok'})
        self.assertEqual((request.body, request.max_pages), ({'query': 'q', 'next_page_token': 'tok'}, 1))

    def test_token_is_rejected_on_other_endpoints(self) -> None:
        with self.assertRaises(runtime.InputError):
            standby.standby_request({'query': 'q', 'next_page_token': 'tok'})
        yelp = load_actor('yelp', 'standby')
        with self.assertRaises(load_actor('yelp', 'runtime').InputError):
            yelp.standby_request({'query': 'q', 'location': 'Austin', 'next_page_token': 'tok'})
