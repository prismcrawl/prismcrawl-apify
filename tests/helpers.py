"""Shared test fixtures: a fake PrismCrawl server and a loader for each Actor's package.

All PrismCrawl HTTP traffic is mocked; the tests never call the real API.
"""

from __future__ import annotations

import importlib
import importlib.util
import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ACTOR_SLUGS = sorted(path.name for path in (ROOT / 'actors').iterdir() if (path / 'my_actor').is_dir())

API_KEY = 'pc_test_placeholder_key_0123456789'  # Placeholder, not a real key.
REQUEST_ID = '66ca8deb-1dc2-4017-865f-c4fb0e3c7c0d'


def search_body(*, has_next_page: bool = False, query: str = 'best coffee shops in Baltimore') -> dict[str, Any]:
    """A success body shaped like the documented GoogleJsonSearchResponse example."""
    return {
        'success': True,
        'request_id': REQUEST_ID,
        'data': {
            'format': 'json',
            'content': {
                'search_parameters': {'q': query, 'type': 'search', 'engine': 'google', 'gl': 'us', 'hl': 'en-US'},
                'has_next_page': has_next_page,
                'results': [
                    {
                        'id': 's_972c538a8734a8b7',
                        'rank': 1,
                        'type': 'organic',
                        'title': 'The 14 Best Espresso Machines, Tested & Reviewed',
                        'url': 'https://www.seriouseats.com/best-espresso-machines-5185482',
                        'display_url': 'seriouseats.com › best-espresso-machines-5185482',
                        'snippet': 'Our favorite espresso machine is the Breville Bambino Plus.',
                        'domain': 'seriouseats.com',
                        'favicon': 'https://seriouseats.com/favicon.ico',
                        'source_name': 'Serious Eats',
                        'position': {'absolute': 1},
                        'engine': 'google',
                        'domain_info': {'tld': 'com', 'sld': 'seriouseats', 'category': None},
                        'classification': None,
                    }
                ],
                'serp_features': [
                    {
                        'id': 'f_5236e4e73b2337d4',
                        'engine': 'google',
                        'type': 'people_also_ask',
                        'title': 'People also ask',
                        'text': None,
                        'items': [{'title': 'Which brand is most reliable?', 'text': None, 'link': None}],
                        'links': [],
                        'source_result_ids': ['s_972c538a8734a8b7'],
                        'position': {'absolute': 1},
                        'confidence': 0.8,
                        'extracted_at': '2026-07-01T16:45:24Z',
                    }
                ],
            },
        },
    }


def error_body(code: str, message: str, **extra: str) -> dict[str, Any]:
    return {
        'success': False,
        'request_id': REQUEST_ID,
        'data': None,
        'error': {'code': code, 'message': message, **extra},
    }


class FakeResponse:
    def __init__(self, status: int, body: dict[str, Any], headers: dict[str, str]) -> None:
        self.status = status
        self.headers = headers
        self._raw = json.dumps(body).encode()

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None


class FakePrismCrawl:
    """Replaces `urllib.request.urlopen`, replaying queued responses and recording requests."""

    def __init__(self, *responses: tuple[int, dict[str, Any] | None] | BaseException) -> None:
        self.queue = list(responses)
        self.requests: list[urllib.request.Request] = []

    def __call__(self, request: urllib.request.Request, timeout: float) -> FakeResponse:
        self.requests.append(request)
        item = self.queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        status, body = item
        headers = {'X-Request-Id': REQUEST_ID, 'X-Credits-Remaining': '99'}
        if status >= 400:  # noqa: PLR2004
            raw = json.dumps(body).encode() if body is not None else b'<html>Bad gateway</html>'
            raise urllib.error.HTTPError(request.full_url, status, 'error', headers, io.BytesIO(raw))  # type: ignore[arg-type]
        return FakeResponse(status, body or {}, headers)

    def json_bodies(self) -> list[dict[str, Any]]:
        return [json.loads(r.data) for r in self.requests]  # type: ignore[arg-type]


def load_actor(slug: str, module: str = 'endpoint') -> ModuleType:
    """Import `actors/<slug>/my_actor/<module>.py` as part of a uniquely named package.

    Every Actor's package is called `my_actor` on disk, so each is loaded under its own name to keep them apart.
    """
    package = f'actor_{slug.replace("-", "_")}'
    if package not in sys.modules:
        package_dir = ROOT / 'actors' / slug / 'my_actor'
        spec = importlib.util.spec_from_file_location(
            package, package_dir / '__init__.py', submodule_search_locations=[str(package_dir)]
        )
        assert spec and spec.loader
        sys.modules[package] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sys.modules[package])
    return importlib.import_module(f'{package}.{module}')
