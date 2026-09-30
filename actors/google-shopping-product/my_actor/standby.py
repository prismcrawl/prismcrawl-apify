"""Actor Standby mode: serve single-page PrismCrawl requests over HTTP.

`POST /` accepts the same JSON fields as the Actor input (except `prismcrawlApiKey` and `maxPages`) and responds with
the PrismCrawl response body and status code unchanged. For token-paginated endpoints, pass the previous response's
`next_page_token` in the body to get the next page. The PrismCrawl API key is read from the `x-prismcrawl-api-key`
request header so it never has to appear in a URL or request body.

This file is shared by every PrismCrawl Actor in this repository. Edit `shared/standby.py`, then run
`python scripts/build_actors.py`.
"""

from __future__ import annotations

import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from apify import Actor

from .endpoint import ACTOR_TITLE, STANDBY_EXAMPLE, build_request
from .prismcrawl import PrismCrawlClient, PrismCrawlError, redact
from .runtime import TOKEN_PARAM, ActorRequest, InputError

API_KEY_HEADER = 'x-prismcrawl-api-key'
READINESS_PROBE_HEADER = 'x-apify-container-server-readiness-probe'
MAX_BODY_BYTES = 64 * 1024

USAGE = (
    f'{ACTOR_TITLE} Actor (Standby).\n'
    f'POST / with a JSON body such as {json.dumps(STANDBY_EXAMPLE)} and your '
    f'PrismCrawl API key in the "{API_KEY_HEADER}" header.\n'
    'Docs: https://www.prismcrawl.com/docs\n'
)


class StandbyHandler(BaseHTTPRequestHandler):
    """Handle readiness probes and search requests."""

    server_version = 'PrismCrawlActor'

    def do_GET(self) -> None:
        # Apify Standby readiness probe:
        # https://docs.apify.com/platform/actors/development/programming-interface/standby#readiness-probe
        if READINESS_PROBE_HEADER in self.headers:
            self._send_text(200, 'ok')
            return
        self._send_text(200, USAGE)

    def do_POST(self) -> None:
        api_key = (self.headers.get(API_KEY_HEADER) or '').strip()
        if not api_key:
            self._send_actor_error(
                401, 'missing_api_key', f'Send your PrismCrawl API key in the "{API_KEY_HEADER}" header.'
            )
            return

        try:
            actor_input = self._read_json()
            if 'prismcrawlApiKey' in actor_input:
                raise InputError(f'Send the API key in the "{API_KEY_HEADER}" header, not in the request body.')
            if actor_input.get('maxPages') not in (None, 1):
                raise InputError('Standby requests return a single page; request later pages one at a time.')
            request = standby_request(actor_input)
        except InputError as error:
            self._send_actor_error(400, 'invalid_input', redact(str(error), api_key))
            return

        client = PrismCrawlClient(api_key)
        try:
            response = client.post(request.path, request.body)
        except PrismCrawlError as error:
            Actor.log.warning(client.redact(error.describe()))
            if error.body is not None and error.status is not None:
                self._send_json(error.status, error.body)
            else:
                self._send_actor_error(502, error.code, client.redact(error.describe()))
            return

        Actor.log.info(f'Standby request completed, request_id={response.request_id}')
        self._send_json(response.status, response.body)

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            raise InputError('Invalid Content-Length header.') from None
        if length > MAX_BODY_BYTES:
            raise InputError(f'The request body must not exceed {MAX_BODY_BYTES} bytes.')
        try:
            payload = json.loads(self.rfile.read(length) or b'{}')
        except ValueError:
            raise InputError('The request body must be valid JSON.') from None
        if not isinstance(payload, dict):
            raise InputError('The request body must be a JSON object.')
        return payload

    def _send_actor_error(self, status: int, code: str, message: str) -> None:
        # Mirrors PrismCrawl's error envelope; request_id is null because PrismCrawl was not called (or not reached).
        self._send_json(
            status, {'success': False, 'request_id': None, 'data': None, 'error': {'code': code, 'message': message}}
        )

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        self._send(status, json.dumps(payload).encode(), 'application/json')

    def _send_text(self, status: int, text: str) -> None:
        self._send(status, text.encode(), 'text/plain; charset=utf-8')

    def _send(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        # The default logs the full request line, which can include an Apify `?token=` query parameter.
        Actor.log.debug(f'{self.command} {self.path.split("?", 1)[0]} -> {args[1] if len(args) > 1 else ""}')


def standby_request(actor_input: dict[str, Any]) -> ActorRequest:
    """Build a single-page request, applying a caller-supplied `next_page_token` on token-paginated endpoints."""
    token = actor_input.get(TOKEN_PARAM)
    request = build_request({key: value for key, value in actor_input.items() if key != TOKEN_PARAM})
    if token is not None:
        if request.pagination.kind != 'token':
            raise InputError(f'"{TOKEN_PARAM}" is not supported here.')
        if not isinstance(token, str) or not token:
            raise InputError(f'"{TOKEN_PARAM}" must be a non-empty string.')
        drop = request.pagination.drop_on_token
        request.body = {key: value for key, value in request.body.items() if key not in drop}
        request.body[TOKEN_PARAM] = token
    request.max_pages = 1
    return request


async def serve_standby(port: int) -> None:
    """Serve Standby requests until the Actor is stopped."""
    server = ThreadingHTTPServer(('', port), StandbyHandler)
    Actor.log.info(f'Standby server listening on port {port}.')
    try:
        await asyncio.to_thread(server.serve_forever)
    finally:
        server.shutdown()
        server.server_close()
