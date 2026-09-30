"""Tests for each Actor's `endpoint.py`, plus conformance with the vendored PrismCrawl OpenAPI spec."""

from __future__ import annotations

import json
import unittest
from typing import Any

from tests.helpers import ACTOR_SLUGS, API_KEY, ROOT, load_actor

SPEC = json.loads((ROOT / 'spec' / 'openapi.json').read_text())
SCHEMAS = SPEC['components']['schemas']


def request_schema(path: str) -> dict[str, Any]:
    schema = SPEC['paths'][path]['post']['requestBody']['content']['application/json']['schema']
    while '$ref' in schema:
        schema = SCHEMAS[schema['$ref'].split('/')[-1]]
    return schema


def build(slug: str, actor_input: dict[str, Any]) -> Any:
    return load_actor(slug).build_request(actor_input)


def invalid(slug: str) -> Any:
    return load_actor(slug, 'runtime').InputError


# One full input per Actor mode: every field the mode uses is set, so the spec test sees every parameter sent.
FULL_INPUTS: dict[str, list[dict[str, Any]]] = {
    'google-search': [
        {
            'query': 'coffee',
            'maxPages': 3,
            'start': 10,
            'gl': 'us',
            'hl': 'en-US',
            'google_domain': 'google.com',
            'device': 'mobile',
            'latitude': 39.29,
            'longitude': -76.61,
            'radius': 500,
            'udm': '14',
            'tbs': 'qdr:w',
            'safe': 'active',
            'lr': 'lang_en',
            'cr': 'countryUS',
            'nfpr': '1',
            'filter': '0',
            'pws': '0',
            'zero_trace': True,
        },
        {'query': 'coffee', 'location': 'Austin,Texas,United States', 'tbm': 'nws', 'uule': ''},
        {'query': 'coffee', 'uule': 'w+CAIQICIaQXVzdGluLFRleGFzLFVuaXRlZCBTdGF0ZXM'},
    ],
    'google-maps-places': [
        {
            'query': 'coffee',
            'latitude': 30.2672,
            'longitude': -97.7431,
            'zoom': 13.1,
            'start': 20,
            'gl': 'us',
            'hl': 'en-US',
            'maxPages': 2,
            'zero_trace': False,
        },
    ],
    'google-maps-reviews': [
        {
            'mode': 'place',
            'id': 'ChIJaXQRs6lZwokRY6EFpJnhNNE',
            'country': 'us',
            'language': 'en',
            'device': 'mobile',
            'limit': 10,
            'maxPages': 5,
            'zero_trace': True,
        },
        {'mode': 'contributor', 'id': '112967280418127956987', 'country': 'us', 'language': 'en', 'limit': 50},
    ],
    'amazon-search': [
        {
            'query': 'espresso machine',
            'maxPages': 2,
            'page': 3,
            'device': 'mobile',
            'amazon_domain': 'amazon.de',
            'language': 'de_DE',
            'delivery_country': 'DE',
            'postal_code': '10115',
            'currency': 'EUR',
            'category_id': 'kitchen',
            'sort_by': 'price_low_to_high',
            'rh': 'p_36:1000-5000',
            'merchant_id': 'A1B2C3',
            'direct_search': False,
            'zero_trace': True,
        },
    ],
    'bing-search': [
        {
            'query': 'coffee',
            'maxPages': 2,
            'device': 'desktop',
            'safe': 'off',
            'cc': 'gb',
            'setlang': 'en-GB',
            'latitude': 51.5,
            'longitude': -0.12,
            'tbs': 'qdr:w',
            'zero_trace': True,
        },
    ],
    'google-shopping-product': [
        {
            'id': '17755277695162489284',
            'query': 'sony wh-1000xm5',
            'country': 'us',
            'language': 'en',
            'zero_trace': True,
        },
    ],
    'google-play': [
        {
            'mode': 'apps',
            'query': 'weather',
            'limit': 50,
            'country': 'us',
            'language': 'en',
            'device': 'mobile',
            'maxPages': 2,
            'zero_trace': True,
        },
        {'mode': 'games', 'query': 'puzzle', 'gamesCategory': 'GAME_PUZZLE', 'limit': 20},
        {'mode': 'books', 'query': 'history', 'limit': 20},
        {'mode': 'movies', 'query': 'comedy', 'limit': 20},
        {'mode': 'product', 'id': 'com.google.android.apps.maps', 'productCategory': 'apps', 'country': 'us'},
        {'mode': 'reviews', 'id': 'com.google.android.apps.maps', 'sort_by': 'newest', 'limit': 100},
    ],
    'apple-app-store': [
        {
            'mode': 'search',
            'query': 'weather',
            'category': 'iPadSoftware',
            'limit': 50,
            'language': 'en',
            'country': 'us',
            'device': 'tablet',
            'zero_trace': True,
        },
        {'mode': 'product', 'id': '284882215', 'language': 'en', 'country': 'us'},
        {'mode': 'reviews', 'id': '284882215', 'sort_by': 'helpful', 'limit': 50, 'country': 'us'},
    ],
    'yelp': [
        {
            'mode': 'search',
            'query': 'restaurants',
            'location': 'Austin, TX',
            'page': 2,
            'limit': 20,
            'language': 'en',
            'device': 'mobile',
            'zero_trace': True,
        },
        {'mode': 'search', 'query': 'restaurants', 'latitude': 30.27, 'longitude': -97.74},
        {'mode': 'reviews', 'id': 'halcyon-austin-2', 'sort_by': 'newest', 'page': 5, 'limit': 50},
    ],
    'tripadvisor': [
        {
            'mode': 'search',
            'query': 'restaurants',
            'location': 'Austin, TX',
            'limit': 30,
            'language': 'en',
            'device': 'mobile',
            'zero_trace': True,
        },
        {'mode': 'place', 'id': 'https://www.tripadvisor.com/Restaurant_Review-g1-d2-Reviews-X.html'},
        {
            'mode': 'reviews',
            'id': 'https://www.tripadvisor.com/Restaurant_Review-g1-d2-Reviews-X.html',
            'sort_by': 'newest',
            'limit': 100,
        },
    ],
}


class SpecConformanceTests(unittest.TestCase):
    """Nothing the Actors send or offer is invented: it must exist in PrismCrawl's OpenAPI spec."""

    def test_every_actor_has_full_inputs(self) -> None:
        self.assertEqual(sorted(FULL_INPUTS), ACTOR_SLUGS)

    def test_request_bodies_only_use_documented_parameters(self) -> None:
        for slug, inputs in FULL_INPUTS.items():
            for actor_input in inputs:
                with self.subTest(slug=slug, mode=actor_input.get('mode')):
                    request = build(slug, {'prismcrawlApiKey': API_KEY, **actor_input})
                    self.assertIn(request.path, SPEC['paths'])
                    properties = request_schema(request.path)['properties']
                    self.assertEqual(set(request.body) - set(properties), set())
                    self.assertNotIn('prismcrawlApiKey', request.body)
                    self.assertEqual(request.ignored_fields, [])
                    if request.pagination.kind == 'token':
                        self.assertIn('next_page_token', properties)
                    if request.pagination.kind in ('offset', 'page'):
                        self.assertIn(request.pagination.param, properties)

    def test_input_enums_and_defaults_match_spec(self) -> None:
        renamed = {'productCategory': 'category', 'gamesCategory': 'category'}
        for slug in ACTOR_SLUGS:
            schema = json.loads((ROOT / 'actors' / slug / '.actor' / 'input_schema.json').read_text())
            paths = {build(slug, {**i, 'prismcrawlApiKey': API_KEY}).path for i in FULL_INPUTS[slug]}
            for name, field in schema['properties'].items():
                spec_props = [request_schema(p)['properties'].get(renamed.get(name, name)) for p in paths]
                spec_props = [p for p in spec_props if p]
                if not spec_props:
                    continue
                with self.subTest(slug=slug, field=name):
                    if 'enum' in field:
                        documented = {str(v) for p in spec_props for v in p.get('enum', []) if v is not None}
                        self.assertTrue(documented, 'input offers choices the spec does not enumerate')
                        self.assertLessEqual(set(field['enum']), documented)
                    for p in spec_props:
                        if 'default' in field and p.get('default') is not None:
                            self.assertEqual(field['default'], p['default'])
                        if 'pattern' in field and 'pattern' in p:
                            self.assertEqual(field['pattern'], p['pattern'])


class GoogleSearchTests(unittest.TestCase):
    def test_maps_input_to_documented_fields(self) -> None:
        request = build('google-search', {'prismcrawlApiKey': API_KEY, **FULL_INPUTS['google-search'][0]})
        self.assertEqual(request.max_pages, 3)
        self.assertEqual(request.path, '/v1/google/search')
        self.assertEqual(
            request.body,
            {
                'query': 'coffee',
                'gl': 'us',
                'hl': 'en-US',
                'google_domain': 'google.com',
                'device': 'mobile',
                'tbs': 'qdr:w',
                'safe': 'active',
                'lr': 'lang_en',
                'cr': 'countryUS',
                'zero_trace': True,
                'udm': 14,
                'pws': 0,
                'nfpr': 1,
                'filter': 0,
                'coordinates': {'latitude': 39.29, 'longitude': -76.61},
                'radius': 500,
                'start': 10,
            },
        )
        self.assertEqual(
            (request.pagination.kind, request.pagination.param, request.pagination.step), ('offset', 'start', 10)
        )

    def test_minimal_input_omits_optional_fields(self) -> None:
        request = build('google-search', {'query': ' coffee '})
        self.assertEqual((request.body, request.max_pages), ({'query': 'coffee'}, 1))

    def test_invalid_combinations_rejected(self) -> None:
        cases = {
            'missing query': {},
            'blank query': {'query': '  '},
            'query too long': {'query': 'é' * 4097},
            'location + coordinates': {'query': 'q', 'location': 'Austin', 'latitude': 1, 'longitude': 2},
            'location + uule': {'query': 'q', 'location': 'Austin', 'uule': 'w+CAIQICI'},
            'latitude only': {'query': 'q', 'latitude': 1},
            'radius without coordinates': {'query': 'q', 'radius': 10},
            'desktop radius too large': {'query': 'q', 'latitude': 1, 'longitude': 2, 'radius': 500},
            'tbm + udm': {'query': 'q', 'tbm': 'nws', 'udm': '12'},
            'tbs too long': {'query': 'q', 'tbs': 'x' * 513},
            'negative start': {'query': 'q', 'start': -1},
            'too many pages': {'query': 'q', 'maxPages': 11},
            'bad binary': {'query': 'q', 'pws': '2'},
        }
        for name, actor_input in cases.items():
            with self.subTest(name), self.assertRaises(invalid('google-search')):
                build('google-search', actor_input)


class OtherActorTests(unittest.TestCase):
    def assert_invalid(self, slug: str, cases: dict[str, dict[str, Any]]) -> None:
        for name, actor_input in cases.items():
            with self.subTest(slug=slug, case=name), self.assertRaises(invalid(slug)):
                build(slug, actor_input)

    def test_google_maps_places(self) -> None:
        request = build('google-maps-places', FULL_INPUTS['google-maps-places'][0])
        self.assertEqual(request.body['coordinates'], {'latitude': 30.2672, 'longitude': -97.7431})
        self.assertEqual((request.pagination.kind, request.pagination.step), ('offset', 20))
        self.assert_invalid(
            'google-maps-places',
            {
                'no coordinates': {'query': 'coffee'},
                'zoom too high': {'query': 'coffee', 'latitude': 1, 'longitude': 1, 'zoom': 22},
                'bad latitude': {'query': 'coffee', 'latitude': 91, 'longitude': 1},
            },
        )

    def test_google_maps_reviews_modes_and_limits(self) -> None:
        place = build('google-maps-reviews', FULL_INPUTS['google-maps-reviews'][0])
        contributor = build('google-maps-reviews', FULL_INPUTS['google-maps-reviews'][1])
        self.assertEqual((place.path, contributor.path), ('/v1/google/maps/reviews', '/v1/google/contributor/reviews'))
        self.assertEqual(place.pagination.kind, 'token')
        self.assert_invalid(
            'google-maps-reviews',
            {
                'no id': {'mode': 'place'},
                'place limit over 10': {'mode': 'place', 'id': 'x', 'limit': 11},
                'bad mode': {'mode': 'everything', 'id': 'x'},
            },
        )

    def test_amazon_currency_rule(self) -> None:
        self.assertEqual(build('amazon-search', {'query': 'q', 'currency': 'USD'}).body['currency'], 'USD')
        self.assertEqual(
            build(
                'amazon-search',
                {'query': 'q', 'amazon_domain': 'amazon.com', 'delivery_country': 'CA', 'currency': 'CAD'},
            ).body['currency'],
            'CAD',
        )
        self.assert_invalid(
            'amazon-search',
            {
                'US storefront with EUR': {'query': 'q', 'currency': 'EUR'},
                'page over 1000': {'query': 'q', 'page': 1001},
                'too many pages': {'query': 'q', 'maxPages': 21},
            },
        )
        self.assertEqual(build('amazon-search', {'query': 'q'}).pagination.param, 'page')

    def test_bing_token_pagination_and_tbs(self) -> None:
        request = build('bing-search', FULL_INPUTS['bing-search'][0])
        self.assertEqual((request.pagination.kind, request.pagination.drop_on_token), ('token', ('first',)))
        self.assertNotIn('first', request.body)
        self.assert_invalid('bing-search', {'hour range': {'query': 'q', 'tbs': 'qdr:h'}})

    def test_google_shopping_product_is_single_page(self) -> None:
        request = build('google-shopping-product', FULL_INPUTS['google-shopping-product'][0])
        self.assertEqual((request.max_pages, request.pagination.kind), (1, 'none'))
        self.assert_invalid('google-shopping-product', {'no query': {'id': 'x'}, 'no id': {'query': 'q'}})

    def test_google_play_modes(self) -> None:
        paths = [build('google-play', i).path for i in FULL_INPUTS['google-play']]
        self.assertEqual(len(set(paths)), 6)
        product = build('google-play', {**FULL_INPUTS['google-play'][4], 'maxPages': 5})
        self.assertEqual((product.body['category'], product.max_pages, product.pagination.kind), ('apps', 1, 'none'))
        games = build('google-play', {'mode': 'games', 'gamesCategory': 'GAME_ACTION'})
        self.assertEqual(games.body, {'category': 'GAME_ACTION'})
        ignored = build('google-play', {'mode': 'apps', 'query': 'q', 'id': 'com.x', 'sort_by': 'newest'})
        self.assertEqual(ignored.ignored_fields, ['id', 'sort_by'])
        self.assertNotIn('id', ignored.body)
        self.assert_invalid(
            'google-play',
            {
                'games without query or category': {'mode': 'games'},
                'reviews without id': {'mode': 'reviews'},
                'search without query': {'mode': 'apps'},
            },
        )

    def test_apple_app_store_reviews_do_not_send_language(self) -> None:
        reviews = build('apple-app-store', {'mode': 'reviews', 'id': '1', 'language': 'en'})
        self.assertNotIn('language', reviews.body)
        self.assertEqual(reviews.ignored_fields, ['language'])
        self.assert_invalid('apple-app-store', {'search without query': {'mode': 'search'}})

    def test_yelp_location_rules(self) -> None:
        request = build('yelp', FULL_INPUTS['yelp'][1])
        self.assertEqual(request.body['coordinates'], {'latitude': 30.27, 'longitude': -97.74})
        self.assertEqual(request.pagination.param, 'page')
        self.assert_invalid(
            'yelp',
            {
                'no location': {'mode': 'search', 'query': 'q'},
                'location and coordinates': {
                    'mode': 'search',
                    'query': 'q',
                    'location': 'Austin',
                    'latitude': 1,
                    'longitude': 2,
                },
                'past 200-business window': {'mode': 'search', 'query': 'q', 'location': 'Austin', 'page': 11},
                'reviews without id': {'mode': 'reviews'},
            },
        )

    def test_tripadvisor_limits(self) -> None:
        self.assertEqual(build('tripadvisor', FULL_INPUTS['tripadvisor'][1]).pagination.kind, 'none')
        self.assert_invalid(
            'tripadvisor',
            {
                'search limit over 30': {'mode': 'search', 'query': 'q', 'limit': 31},
                'place without id': {'mode': 'place'},
            },
        )


if __name__ == '__main__':
    unittest.main()
