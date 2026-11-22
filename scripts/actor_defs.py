"""Definitions for every PrismCrawl Actor in this repository.

`build_actors.py` renders these into each Actor's `.actor/` files and README. Parameter names, enums, defaults, limits
and example requests come from the vendored PrismCrawl OpenAPI spec (`spec/openapi.json`); descriptions paraphrase it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SPEC = json.loads((ROOT / 'spec' / 'openapi.json').read_text())
NAMES = json.loads((ROOT / 'spec' / 'display_names.json').read_text())
SCHEMAS = SPEC['components']['schemas']
EXAMPLE_REQUEST_ID = '66ca8deb-1dc2-4017-865f-c4fb0e3c7c0d'  # The request ID used throughout PrismCrawl's docs.


def spec_prop(schema: str, prop: str) -> dict[str, Any]:
    return SCHEMAS[schema]['properties'][prop]


def spec_enum(schema: str, prop: str) -> list[Any]:
    return [value for value in spec_prop(schema, prop)['enum'] if value is not None]


def request_example(path: str, name: str | None = None) -> dict[str, Any]:
    examples = SPEC['paths'][path]['post']['requestBody']['content']['application/json']['examples']
    return examples[name or next(iter(examples))]['value']


def response_example(path: str, name: str = 'json') -> dict[str, Any] | None:
    content = SPEC['paths'][path]['post']['responses']['200']['content']['application/json']
    example = content.get('examples', {}).get(name)
    return example['value'] if example else None


# Input field builders -------------------------------------------------------------------------------------------------


def text(title: str, description: str, **extra: Any) -> dict[str, Any]:
    return {'title': title, 'type': 'string', 'editor': 'textfield', 'description': description, **extra}


def integer(title: str, description: str, **extra: Any) -> dict[str, Any]:
    return {'title': title, 'type': 'integer', 'editor': 'number', 'description': description, **extra}


def number(title: str, description: str, **extra: Any) -> dict[str, Any]:
    return {'title': title, 'type': 'number', 'editor': 'number', 'description': description, **extra}


def select(title: str, description: str, values: list[Any], titles: list[str], **extra: Any) -> dict[str, Any]:
    assert len(values) == len(titles), title
    return {
        'title': title,
        'type': 'string',
        'editor': 'select',
        'enum': [str(v) for v in values],
        'enumTitles': titles,
        'description': description,
        **extra,
    }


def section(caption: str, description: str | None = None) -> dict[str, Any]:
    return {'sectionCaption': caption, **({'sectionDescription': description} if description else {})}


def region_title(code: str) -> str:
    return f'{NAMES["regions"][code.upper()]} ({code})'


def language_title(code: str) -> str:
    return f'{NAMES["languages"][code.replace("_", "-")]} ({code})'


API_KEY = {
    'title': 'PrismCrawl API key',
    'type': 'string',
    'editor': 'textfield',
    'isSecret': True,
    'description': 'Your PrismCrawl API key, sent to PrismCrawl as the <code>x-api-key</code> header. Create or '
    'rotate it in the <a href="https://www.prismcrawl.com/" target="_blank">PrismCrawl dashboard</a>; new accounts get '
    '100 free credits. The key is stored encrypted by Apify and is never logged or written to the dataset.',
}


def max_pages(limit: int, per_page: str) -> dict[str, Any]:
    return integer(
        'Maximum pages',
        f'How many pages to fetch ({per_page}). The Actor stops early when PrismCrawl reports there is no next page. '
        '<strong>Each page is a separate PrismCrawl request and uses one credit.</strong>',
        minimum=1,
        maximum=limit,
        default=1,
    )


ZERO_TRACE = {
    **section('Privacy'),
    'title': 'Zero trace',
    'type': 'boolean',
    'default': False,
    'description': 'When enabled, PrismCrawl does not store the source or parsed response for these requests; only '
    "audit and billing metadata is kept. Results still appear in this Actor's dataset.",
}
DEVICE = select(
    'Device',
    'Device presentation used for the source request. Leave empty for the default.',
    ['desktop', 'mobile', 'tablet'],
    ['Desktop', 'Mobile', 'Tablet'],
)
COUNTRY = text(
    'Country',
    'Two-letter country or storefront code, such as <code>us</code> or <code>gb</code>.',
    pattern='^[A-Za-z]{2}$',
)
LANGUAGE = text('Language', 'Language code supported by the provider, such as <code>en</code>.')
LATITUDE = number(
    'Latitude', 'Latitude, for example <code>39.2904</code>. Set together with longitude.', minimum=-90, maximum=90
)
LONGITUDE = number(
    'Longitude', 'Longitude, for example <code>-76.6122</code>. Set together with latitude.', minimum=-180, maximum=180
)


def gl_field(schema: str, description: str) -> dict[str, Any]:
    values = spec_enum(schema, 'gl')
    return select(
        'Country (gl)',
        description,
        values,
        [region_title(v) for v in values],
        default=spec_prop(schema, 'gl')['default'],
    )


def hl_field(schema: str, title: str, description: str) -> dict[str, Any]:
    values = spec_enum(schema, 'hl')
    return select(
        title, description, values, [language_title(v) for v in values], default=spec_prop(schema, 'hl')['default']
    )


# Dataset views ------------------------------------------------------------------------------------------------------


def table_view(
    title: str, description: str, columns: list[tuple[str, str, str]], unwind: str = 'results'
) -> dict[str, Any]:
    """A view with one row per item of `data.content.<unwind>`; columns are (field, label, format)."""
    columns = [('page', 'Page', 'number'), *columns, ('request_id', 'PrismCrawl request ID', 'text')]
    return {
        'title': title,
        'description': description,
        # Apify applies `fields` before `unwind`, so `data` must be kept or there is nothing to unwind.
        'transformation': {
            'unwind': ['data', 'content', unwind],
            'fields': [*(name for name, _, _ in columns), 'data'],
        },
        'display': {
            'component': 'table',
            'properties': {name: {'label': label, 'format': fmt} for name, label, fmt in columns},
        },
    }


SERP_FEATURES_VIEW = table_view(
    'SERP features',
    'One row per SERP feature, such as featured snippets, People also ask, knowledge panels, news, and AI summaries.',
    [
        ('type', 'Type', 'text'),
        ('title', 'Title', 'text'),
        ('text', 'Text', 'text'),
        ('items', 'Items', 'array'),
        ('links', 'Links', 'array'),
        ('source_result_ids', 'Related result IDs', 'array'),
        ('confidence', 'Confidence', 'number'),
    ],
    unwind='serp_features',
)
WEB_RESULTS_VIEW = table_view(
    'Search results',
    'One row per ranked result (organic results, ads, and other result types).',
    [
        ('rank', 'Rank', 'number'),
        ('type', 'Type', 'text'),
        ('title', 'Title', 'text'),
        ('url', 'URL', 'link'),
        ('display_url', 'Display URL', 'text'),
        ('snippet', 'Snippet', 'text'),
        ('domain', 'Domain', 'text'),
        ('source_name', 'Source', 'text'),
        ('favicon', 'Favicon', 'image'),
    ],
)
REVIEWS_VIEW = table_view(
    'Reviews',
    'One row per review.',
    [
        ('position', 'Position', 'number'),
        ('rating', 'Rating', 'number'),
        ('text', 'Review', 'text'),
        ('author', 'Author', 'text'),
        ('date', 'Date', 'text'),
        ('published_at', 'Published', 'text'),
        ('language', 'Language', 'text'),
        ('helpful_votes', 'Helpful votes', 'number'),
        ('url', 'URL', 'link'),
    ],
)
APPS_VIEW = table_view(
    'Apps and products',
    'One row per app, game, book, movie, or product.',
    [
        ('position', 'Position', 'number'),
        ('thumbnail', 'Icon', 'image'),
        ('title', 'Title', 'text'),
        ('id', 'ID', 'text'),
        ('developer', 'Developer', 'text'),
        ('category', 'Category', 'text'),
        ('rating', 'Rating', 'number'),
        ('rating_count', 'Ratings', 'number'),
        ('price_text', 'Price', 'text'),
        ('installs', 'Installs', 'text'),
        ('url', 'URL', 'link'),
    ],
)


# README helpers -----------------------------------------------------------------------------------------------------


def envelope(content: dict[str, Any], *, data_extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        'success': True,
        'request_id': EXAMPLE_REQUEST_ID,
        'data': {'format': 'json', **(data_extra or {}), 'content': content},
    }


def catalog_example(engine: str, kind: str, results: list[dict[str, Any]], *, token: bool = True) -> dict[str, Any]:
    """An illustrative response with the documented catalog envelope; result fields come from the result schema."""
    content: dict[str, Any] = {
        'search_parameters': {'engine': engine, 'type': kind},
        'results': results,
        'has_next_page': token,
        'serp_features': [],
    }
    if token:
        content['next_page_token'] = '<opaque token>'
    return envelope(content)


REVIEW_FIELDS_ROW = (
    '`data.content.results[]`',
    'Reviews: `rating`, `text`, `author`, `date` / `published_at`, `language`, `helpful_votes`, `photos`, and '
    '`developer_response` when present.',
)


@dataclass
class ActorDef:
    slug: str
    name: str
    title: str
    description: str
    paths: list[str]
    fields: dict[str, dict[str, Any]]
    required: list[str]
    views: dict[str, dict[str, Any]]
    # README content
    intro: str
    why: list[str]
    target: str  # what the user fetches, e.g. "Google Maps places"
    input_rows: list[tuple[str, str, str]]
    example_input: dict[str, Any]
    example_output: dict[str, Any]
    example_is_illustrative: bool
    data_fields: list[tuple[str, str]]
    tips: list[str]
    faq: list[tuple[str, str]] = field(default_factory=list)
    input_notes: str = ''
    pagination_note: str = ''
    standby_note: str = ''
    related: list[str] = field(default_factory=list)
    # Apify Store listing name and description; the README keeps `title`.
    store_title: str = ''
    store_description: str = ''


def mode_select(values: list[str], titles: list[str], default: str, description: str) -> dict[str, Any]:
    return {**select('What to fetch', description, values, titles), 'default': default}


# Google Search ----------------------------------------------------------------------------------------------------

_G = 'GoogleSearchRequest'
TBM_NAMES = {'nws': 'News', 'vid': 'Videos', 'isch': 'Images', 'shop': 'Shopping', 'lcl': 'Local', 'bks': 'Books'}
UDM_NAMES = {
    1: 'Local',
    2: 'Images',
    6: 'Forums',
    7: 'Videos',
    12: 'News',
    14: 'Web',
    28: 'Shopping',
    36: 'Books',
    50: 'AI Mode',
}
GOOGLE_SEARCH = ActorDef(
    slug='google-search',
    store_title='Google Search Results Scraper | PrismCrawl API',
    store_description=(
        'Get live Google search results as clean JSON: organic rankings, featured snippets, People also ask, '
        'AI summaries, local and shopping results, and pagination. Search from any country, city, or '
        'language. Uses your PrismCrawl API key, with 100 free credits and no card needed.'
    ),
    name='prismcrawl-google-search-api',
    title='PrismCrawl Google Search API',
    description='Run live Google searches through the PrismCrawl API and receive normalized search results, SERP '
    'features, and pagination metadata.',
    paths=['/v1/google/search'],
    fields={
        'prismcrawlApiKey': API_KEY,
        'query': text(
            'Search query',
            'What to search for on Google, exactly as you would type it into the search box. Search operators such '
            'as <code>site:</code> work as usual. Limited to 8,192 UTF-8 bytes.',
            prefill='best coffee shops in Baltimore',
        ),
        'maxPages': max_pages(10, 'one Google results page each'),
        'start': integer(
            'Start offset',
            'Zero-based result offset for the first page (for example <code>10</code> starts at the second page). '
            'Leave empty to start at the first result. Later pages advance the offset by 10.',
            minimum=0,
        ),
        'gl': {
            **section(
                'Location and language',
                'Control which market Google searches from. For city-level targeting use a named location or '
                'coordinates (only one of the two).',
            ),
            **gl_field(
                _G,
                'Two-letter Google result-country code. Results from this country are boosted rather than strictly '
                'filtered. To restrict results to documents from a country, use <strong>Restrict to countries '
                '(cr)</strong>.',
            ),
        },
        'hl': hl_field(
            _G,
            'Interface language (hl)',
            'Google interface language. It can also influence which results are chosen for international queries. '
            'To restrict results to documents in a language, use <strong>Restrict to languages (lr)</strong>.',
        ),
        'google_domain': {
            **select(
                'Google domain',
                'The Google domain to search, for example <code>google.co.uk</code>. This is independent of country, '
                'language, and location.',
                spec_enum(_G, 'google_domain'),
                spec_enum(_G, 'google_domain'),
            ),
            'default': spec_prop(_G, 'google_domain')['default'],
        },
        'location': text(
            'Location',
            'Search as if from a named place, for example <code>Baltimore,Maryland,United States</code>. The value '
            'must be an active <em>Canonical Name</em> from <a href="https://developers.google.com/google-ads/api/'
            'data/geotargets" target="_blank">Google\'s geo-target list</a>. Cannot be combined with coordinates or '
            'UULE.',
        ),
        'latitude': {
            **LATITUDE,
            'description': 'Searcher latitude, for example <code>39.2904</code>. Set together '
            'with longitude. Cannot be combined with location or UULE.',
        },
        'longitude': {
            **LONGITUDE,
            'description': 'Searcher longitude, for example <code>-76.6122</code>. Set together with latitude.',
        },
        'radius': integer(
            'Radius (meters)',
            'Bias results to within this many meters of the coordinates; results outside it may still appear. '
            'Requires latitude and longitude. Maximum 199 for desktop or no device, 1,000 for mobile or tablet.',
            minimum=1,
            maximum=1000,
        ),
        'device': select(
            'Device',
            'Search as a desktop, mobile, or tablet device. Rankings and SERP features can differ by device. Leave '
            "empty for PrismCrawl's default.",
            spec_enum(_G, 'device'),
            [v.capitalize() for v in spec_enum(_G, 'device')],
        ),
        'tbm': {
            **section(
                'Search type and filters',
                'Choose a Google search tab and narrow the results. Use either a tbm vertical or a udm tab, not both.',
            ),
            **select(
                'Search vertical (tbm)',
                'Search a Google vertical instead of the regular results page. Leave empty for regular web results. '
                'Cannot be combined with <strong>Search tab (udm)</strong>.',
                spec_enum(_G, 'tbm'),
                [f'{TBM_NAMES[v]} ({v})' for v in spec_enum(_G, 'tbm')],
            ),
        },
        'udm': select(
            'Search tab (udm)',
            'Select a Google search tab by its numeric <code>udm</code> value, for example <em>Web</em> (links only) '
            'or <em>AI Mode</em>. Availability varies by market. Cannot be combined with <strong>Search vertical '
            '(tbm)</strong>.',
            spec_enum(_G, 'udm'),
            [f'{UDM_NAMES[v]} ({v})' for v in spec_enum(_G, 'udm')],
        ),
        'tbs': text(
            'Time and advanced filters (tbs)',
            "Google's native advanced-filter string. Common time filters: <code>qdr:h</code> (past hour), "
            '<code>qdr:d</code> (past day), <code>qdr:w</code> (past week), <code>qdr:m</code> (past month), '
            '<code>qdr:y</code> (past year); add a number for multiples, e.g. <code>qdr:m6</code>. Custom range: '
            '<code>cdr:1,cd_min:8/1/2026,cd_max:8/12/2026</code>. Sort by date (News): <code>sbd:1</code>. Supported '
            'filters vary by vertical and market.',
            maxLength=512,
        ),
        'safe': select(
            'SafeSearch',
            "Turn Google's SafeSearch filtering on or request unfiltered results. Leave empty for Google's default.",
            spec_enum(_G, 'safe'),
            [{'active': 'On (active)', 'off': 'Off'}[v] for v in spec_enum(_G, 'safe')],
        ),
        'lr': {
            **section('Advanced Google controls', "Rarely needed. Leave empty to use Google's defaults."),
            **text(
                'Restrict to languages (lr)',
                'Only return documents in these languages, using <code>lang_&lt;code&gt;</code> syntax. Separate '
                'alternatives with <code>|</code>, e.g. <code>lang_fr|lang_de</code>.',
                pattern=spec_prop(_G, 'lr')['pattern'],
            ),
        },
        'cr': text(
            'Restrict to countries (cr)',
            'Only return documents from these countries, using <code>country&lt;CC&gt;</code> syntax. Separate '
            'alternatives with <code>|</code>, e.g. <code>countryUS|countryCA</code>.',
            pattern=spec_prop(_G, 'cr')['pattern'],
        ),
        'uule': text(
            'Encoded location (uule)',
            'A raw Google-encoded location (starting with <code>w+</code> or <code>a+</code>), forwarded unchanged. '
            'Google may ignore unsupported values. Prefer <strong>Location</strong> unless you already have UULE '
            'strings. Cannot be combined with location or coordinates.',
            pattern=spec_prop(_G, 'uule')['pattern'],
        ),
        'nfpr': select(
            'Spelling correction (nfpr)',
            'Whether Google may automatically correct the spelling of your query.',
            ['1', '0'],
            ['Search the exact query, no auto-correction (1)', 'Normal correction (0)'],
        ),
        'filter': select(
            'Duplicate filtering (filter)',
            "Request Google's duplicate-result filtering on or off. Google does not guarantee this for regular "
            'search pages.',
            ['1', '0'],
            ['Filter duplicates (1)', 'Show duplicates (0)'],
        ),
        'pws': select(
            'Personalization (pws)',
            'Ask Google to turn personalization off or permit it. This does not disable location, language, or '
            'device effects.',
            ['0', '1'],
            ['Request personalization off (0)', 'Permit personalization (1)'],
        ),
        'zero_trace': ZERO_TRACE,
    },
    required=['prismcrawlApiKey', 'query'],
    views={'results': WEB_RESULTS_VIEW, 'serp_features': SERP_FEATURES_VIEW},
    target='Google search results',
    intro='runs **live Google searches** through the PrismCrawl API and saves the **normalized JSON response** to an '
    'Apify dataset: ranked results, **SERP features** (featured snippets, People also ask, knowledge panels, news, '
    'shopping, local results, AI summaries, and more when Google shows them), and **pagination metadata**.',
    why=[
        '**Rank tracking and SERP monitoring**: schedule the same keyword with fixed location, language, and device, '
        'and compare positions over time.',
        '**SEO and competitor research**: see which pages rank and which SERP features appear for a keyword set.',
        '**Local and international search**: search as if from a country, a named city, or exact coordinates, on any '
        'supported Google domain, in any supported interface language.',
        '**AI agents and research tools**: give an agent current search results with titles, snippets, and source '
        "URLs. The Actor also supports Apify's Standby mode for low-latency HTTP calls.",
    ],
    input_rows=[
        ('Search query', '`query`', 'The Google search. Required, up to 8,192 UTF-8 bytes.'),
        ('Maximum pages', '–', 'Pages to fetch (1–10, default 1). Each page uses one credit.'),
        ('Start offset', '`start`', 'Zero-based result offset for the first page.'),
        ('Country', '`gl`', 'Two-letter result country (default `us`). Boosts results from that country.'),
        ('Interface language', '`hl`', 'Google interface language (default `en-US`).'),
        ('Google domain', '`google_domain`', 'For example `google.co.uk` (default `google.com`).'),
        (
            'Location',
            '`location`',
            'A named place such as `Baltimore,Maryland,United States` ([Google geo-target]'
            '(https://developers.google.com/google-ads/api/data/geotargets) Canonical Name).',
        ),
        ('Latitude / Longitude', '`coordinates`', 'Search from exact coordinates.'),
        ('Radius', '`radius`', 'Meters around the coordinates (1–199 for desktop, up to 1,000 for mobile or tablet).'),
        ('Device', '`device`', '`desktop`, `mobile`, or `tablet`.'),
        ('Search vertical', '`tbm`', 'News, Videos, Images, Shopping, Local, or Books.'),
        ('Search tab', '`udm`', 'Local, Images, Forums, Videos, News, Web, Shopping, Books, or AI Mode.'),
        (
            'Time and advanced filters',
            '`tbs`',
            'For example `qdr:d` (past day), `qdr:w` (past week), or `cdr:1,cd_min:8/1/2026,cd_max:8/12/2026`.',
        ),
        ('SafeSearch', '`safe`', '`active` or `off`.'),
        (
            'Restrict to languages / countries',
            '`lr` / `cr`',
            'For example `lang_fr\\|lang_de` or `countryUS\\|countryCA`.',
        ),
        ('Encoded location', '`uule`', 'A raw Google-encoded location, for advanced users.'),
        (
            'Spelling correction, duplicate filtering, personalization',
            '`nfpr`, `filter`, `pws`',
            "Google's native 0/1 controls.",
        ),
    ],
    input_notes="Some fields can't be combined. Use only one of location, coordinates, or UULE. Radius requires "
    'coordinates. Use either a search vertical or a search tab, not both.',
    example_input={
        'query': 'best coffee shops in Baltimore',
        'gl': 'us',
        'hl': 'en-US',
        'location': 'Baltimore,Maryland,United States',
        'device': 'mobile',
        'maxPages': 2,
    },
    example_output=response_example('/v1/google/search'),  # type: ignore[arg-type]
    example_is_illustrative=False,
    data_fields=[
        ('`data.content.search_parameters`', 'The parameters PrismCrawl used for the search.'),
        (
            '`data.content.results[]`',
            'Ranked results: `rank`, `type` (e.g. `organic`, `ad`, `news`, `shopping`), '
            '`title`, `url`, `display_url`, `snippet`, `domain`, `source_name`, `position`, `domain_info`.',
        ),
        (
            '`data.content.serp_features[]`',
            'SERP features: `type` (e.g. `featured_snippet`, `people_also_ask`, '
            '`knowledge_panel`, `ai_summary`), `title`, `text`, `items`, `links`, `source_result_ids`, `confidence`.',
        ),
        ('`data.content.has_next_page`', 'Whether Google shows another results page.'),
    ],
    tips=[
        '**Keep targeting fixed for rank tracking.** Compare runs that use the same country, language, location, and '
        'device.',
        '**Use a time filter for fresh results**, for example `qdr:d` for the past day, or pick the News vertical '
        '(`tbm`) or tab (`udm`).',
        '**Source HTML** (`html`, `rewrite_links`), pre-encoded queries (`query_encoded`), and `color_scheme` are '
        "PrismCrawl parameters that this Actor doesn't expose, because they don't change the normalized results.",
    ],
    faq=[
        (
            'Which SERP features will I get?',
            'It depends on the query, market, and device. Features appear only when '
            'Google shows them and PrismCrawl recognizes them.',
        ),
    ],
    pagination_note='Later pages advance `start` by 10.',
    standby_note='Use `start` to request later pages.',
    related=['bing-search', 'google-maps-places', 'google-shopping-product'],
)


# Google Maps Places -----------------------------------------------------------------------------------------------

_M = 'GoogleMapsSearchRequest'
GOOGLE_MAPS_PLACES = ActorDef(
    slug='google-maps-places',
    name='prismcrawl-google-maps-places-api',
    title='PrismCrawl Google Maps Places API',
    description='Search Google Maps places around any coordinates through the PrismCrawl API: names, ratings, '
    'reviews count, addresses, phones, websites, hours, and more as structured JSON.',
    paths=['/v1/google/maps/search'],
    fields={
        'prismcrawlApiKey': API_KEY,
        'query': text(
            'Search query',
            'A place, business, product, or category to search on Google Maps, such as <code>coffee shops</code> or '
            '<code>dentist</code>.',
            prefill='coffee shops',
        ),
        'latitude': {
            **LATITUDE,
            'title': 'Map center latitude',
            'prefill': 39.2904,
            'description': 'Latitude of the map center, for example <code>39.2904</code>.',
        },
        'longitude': {
            **LONGITUDE,
            'title': 'Map center longitude',
            'prefill': -76.6122,
            'description': 'Longitude of the map center, for example <code>-76.6122</code>.',
        },
        'zoom': number(
            'Zoom',
            'Google Maps viewport zoom, from 3 to 21. Lower values cover a wider area; higher values focus more '
            f'tightly around the center. PrismCrawl defaults to {spec_prop(_M, "zoom")["default"]}.',
            minimum=spec_prop(_M, 'zoom')['minimum'],
            maximum=spec_prop(_M, 'zoom')['maximum'],
        ),
        'maxPages': max_pages(10, 'up to 20 places each'),
        'start': integer(
            'Start offset',
            'Zero-based offset of the first place, in multiples of 20 (for example <code>20</code> starts at the '
            'second page). Leave empty to start at the first place.',
            minimum=0,
        ),
        'gl': {**section('Language and country'), **gl_field(_M, 'Two-letter Google country hint.')},
        'hl': hl_field(_M, 'Language (hl)', 'Google Maps interface language.'),
        'zero_trace': ZERO_TRACE,
    },
    required=['prismcrawlApiKey', 'query', 'latitude', 'longitude'],
    views={
        'places': table_view(
            'Places',
            'One row per place.',
            [
                ('rank', 'Rank', 'number'),
                ('thumbnail', 'Photo', 'image'),
                ('title', 'Name', 'text'),
                ('category', 'Category', 'text'),
                ('rating', 'Rating', 'number'),
                ('reviews', 'Reviews', 'number'),
                ('price', 'Price', 'text'),
                ('address', 'Address', 'text'),
                ('phone', 'Phone', 'text'),
                ('website', 'Website', 'link'),
                ('open_state', 'Open state', 'text'),
                ('google_maps_url', 'Google Maps', 'link'),
                ('place_id', 'Place ID', 'text'),
            ],
        ),
    },
    target='Google Maps places',
    intro='searches **Google Maps places** around any map center through the PrismCrawl API and saves the '
    '**normalized JSON** to an Apify dataset: up to 20 places per page with **name, category, rating, review count, '
    'address, phone, website, opening hours, popular times, coordinates, and place IDs**.',
    why=[
        '**Lead generation**: collect businesses of a given type in a city, with phone numbers and websites.',
        '**Local SEO and market research**: see which businesses rank in Google Maps for a category and area, and '
        'how they are rated.',
        '**Location intelligence**: map competitors, gaps, and density for any category around any coordinates.',
        '**Review collection**: use the returned `place_id` with the PrismCrawl Google Maps Reviews Actor to fetch '
        'full review text.',
    ],
    input_rows=[
        ('Search query', '`query`', 'What to search on Google Maps. Required.'),
        ('Map center latitude / longitude', '`coordinates`', 'The center of the map. Required.'),
        ('Zoom', '`zoom`', 'Viewport zoom from 3 (wide) to 21 (close). Default 13.1.'),
        ('Maximum pages', '–', 'Pages to fetch (1–10, default 1), up to 20 places each. Each page uses one credit.'),
        ('Start offset', '`start`', 'Zero-based offset in multiples of 20.'),
        ('Country', '`gl`', 'Two-letter Google country hint (default `us`).'),
        ('Language', '`hl`', 'Google Maps interface language (default `en-US`).'),
    ],
    example_input={
        'query': 'coffee shop',
        'latitude': 30.2672,
        'longitude': -97.7431,
        'zoom': 13.1,
        'gl': 'us',
        'hl': 'en-US',
    },
    example_output=response_example('/v1/google/maps/search'),  # type: ignore[arg-type]
    example_is_illustrative=False,
    data_fields=[
        (
            '`data.content.results[]`',
            'Places: `title`, `category`, `categories`, `rating`, `reviews`, `price`, '
            '`address`, `structured_address`, `phone`, `website`, `gps_coordinates`, `open_state`, `hours`, '
            '`operating_hours`, `popular_times`, `review_snippets`, `attributes`, `place_id`, `data_id`, '
            '`google_maps_url`, `reviews_link`, and more.',
        ),
        ('`data.content.has_next_page`', 'True when Google returned a full 20-place page.'),
        ('`data.content.search_parameters`', 'The query, coordinates, zoom, offset, country, and language used.'),
    ],
    tips=[
        '**Adjust zoom to control the area.** Lower zoom covers a wider area around the center; higher zoom focuses '
        'on the immediate neighborhood.',
        '**Cover a large city in tiles.** Run several searches with different map centers instead of many pages from '
        'one center.',
    ],
    pagination_note='Later pages advance `start` by 20.',
    standby_note='Use `start` (in multiples of 20) to request later pages.',
    related=['google-maps-reviews', 'google-search', 'yelp'],
)


# Google Maps Reviews ----------------------------------------------------------------------------------------------

_MR = '/v1/google/maps/reviews'
GOOGLE_MAPS_REVIEWS = ActorDef(
    slug='google-maps-reviews',
    name='prismcrawl-google-maps-reviews-api',
    title='PrismCrawl Google Maps Reviews API',
    description='Get full Google Maps reviews for any place, or all reviews written by a Google contributor, through '
    'the PrismCrawl API as structured JSON.',
    paths=[_MR, '/v1/google/contributor/reviews'],
    fields={
        'prismcrawlApiKey': API_KEY,
        'mode': mode_select(
            ['place', 'contributor'],
            ['Reviews of a place', 'Reviews by a contributor'],
            'place',
            'Fetch the reviews of one place (in relevance order), or the reviews written by one Google Maps '
            'contributor (newest first, covering their first 200 reviews).',
        ),
        'id': text(
            'Place ID or contributor ID',
            'For a place, the <code>place_id</code> from Google Maps search results (for example from the PrismCrawl '
            'Google Maps Places Actor), not the <code>data_id</code>. For a contributor, the numeric ID in their '
            'Google Maps contributor profile URL.',
            prefill=request_example(_MR)['id'],
        ),
        'maxPages': max_pages(100, 'one page of reviews each'),
        'limit': integer(
            'Reviews per page',
            'Maximum reviews per page: up to 10 for a place, up to 50 for a contributor. Google may return fewer.',
            minimum=1,
            maximum=50,
        ),
        'country': {**section('Localization'), **COUNTRY},
        'language': LANGUAGE,
        'device': DEVICE,
        'zero_trace': ZERO_TRACE,
    },
    required=['prismcrawlApiKey', 'id'],
    views={'reviews': REVIEWS_VIEW},
    target='Google Maps reviews',
    intro='fetches **complete Google Maps review text** for any place, or every review written by a **Google Maps '
    'contributor**, through the PrismCrawl API. Each review includes the **rating, text, author, date, language, '
    'photos, helpful votes, and owner response** when available.',
    why=[
        '**Reputation monitoring**: track new reviews and ratings for your locations or competitors on a schedule.',
        '**Sentiment and product research**: analyze what customers praise and complain about.',
        '**Contributor analysis**: review everything a Local Guide or reviewer has written.',
    ],
    input_rows=[
        ('What to fetch', '–', '`place` (reviews of a place) or `contributor` (reviews by a person).'),
        (
            'Place ID or contributor ID',
            '`id`',
            'A `place_id` from Google Maps results, or a numeric contributor ID. Required.',
        ),
        ('Maximum pages', '–', 'Pages to fetch (1–100, default 1). Each page uses one credit.'),
        ('Reviews per page', '`limit`', 'Up to 10 for places, 50 for contributors.'),
        ('Country / Language', '`country` / `language`', 'For example `us` and `en`.'),
        ('Device', '`device`', '`desktop`, `mobile`, or `tablet`.'),
    ],
    example_input={
        'mode': 'place',
        'id': request_example(_MR)['id'],
        'country': 'us',
        'language': 'en',
        'limit': 10,
        'maxPages': 3,
    },
    example_output=catalog_example(
        'google',
        'reviews',
        [
            {
                'id': '<review id>',
                'position': 1,
                'rating': 5,
                'rating_max': 5,
                'text': 'Friendly staff and great coffee.',
                'author': 'Example Reviewer',
                'date': '2026-09-01',
                'language': 'en',
                'helpful_votes': 3,
            }
        ],
    ),
    example_is_illustrative=True,
    data_fields=[
        REVIEW_FIELDS_ROW,
        (
            '`data.content.has_next_page` / `next_page_token`',
            'Whether more reviews are available, and the token the Actor uses to fetch them.',
        ),
        (
            '`data.content.search_parameters`',
            'Includes `pagination_limited` and `access_limited` when Google restricts access to further reviews.',
        ),
    ],
    tips=[
        '**Get place IDs first.** Run the PrismCrawl Google Maps Places Actor and use the `place_id` of each result.',
        '**Place reviews come in pages of up to 10.** Raise Maximum pages to collect more; each page is one credit.',
        '**Contributor reviews cover the first 200 reviews** of the profile, newest first.',
    ],
    faq=[
        (
            'Why did pagination stop early?',
            'Google sometimes restricts further review access. PrismCrawl then marks the '
            'response with `pagination_limited` (and `access_limited` when only a preview is available) and returns no '
            'next-page token.',
        ),
    ],
    pagination_note='The Actor follows `next_page_token` from each response.',
    standby_note="Pass the previous response's `next_page_token` in the body to get the next page.",
    related=['google-maps-places', 'yelp', 'tripadvisor'],
)


# Amazon Search ----------------------------------------------------------------------------------------------------

_A = 'AmazonSearchRequest'
AMAZON_SEARCH = ActorDef(
    slug='amazon-search',
    name='prismcrawl-amazon-search-api',
    title='PrismCrawl Amazon Search API',
    description='Search Amazon marketplaces through the PrismCrawl API and get product results with prices, ratings, '
    'badges, and delivery info, plus filters, categories, and related searches.',
    paths=['/v1/amazon/search'],
    fields={
        'prismcrawlApiKey': API_KEY,
        'query': text(
            'Search query', 'What to search for on Amazon. Limited to 8,192 UTF-8 bytes.', prefill='espresso machine'
        ),
        'maxPages': max_pages(20, 'one Amazon results page each'),
        'page': integer(
            'First page', 'One-based Amazon results page to start from (1–1,000). Default 1.', minimum=1, maximum=1000
        ),
        'amazon_domain': {
            **section('Marketplace and delivery'),
            **select(
                'Amazon marketplace',
                'The Amazon marketplace to search.',
                spec_enum(_A, 'amazon_domain'),
                spec_enum(_A, 'amazon_domain'),
            ),
            'default': spec_prop(_A, 'amazon_domain')['default'],
        },
        'language': select(
            'Language',
            'Amazon locale. It must be supported by the selected marketplace; leave empty for the marketplace '
            'default. For example, amazon.com supports en_US, es_US, and others; amazon.de supports de_DE, en_GB, and '
            'others.',
            spec_enum(_A, 'language'),
            [language_title(v) for v in spec_enum(_A, 'language')],
        ),
        'delivery_country': select(
            'Delivery country',
            'Where products would be delivered. Controls catalog availability, delivery promises, and shipping '
            "context. Leave empty for the marketplace's home country.",
            spec_enum(_A, 'delivery_country'),
            [region_title(v) for v in spec_enum(_A, 'delivery_country')],
        ),
        'postal_code': text(
            'Delivery postal code',
            'Exact delivery postal code, for example <code>10001</code> on amazon.com. Only accepted when the '
            "delivery country is the marketplace's home country.",
            minLength=1,
            maxLength=16,
        ),
        'currency': select(
            'Display currency',
            "Changes displayed prices only. Leave empty for the marketplace's native currency. Most marketplaces only "
            'accept their native currency; amazon.com with US delivery only supports USD.',
            spec_enum(_A, 'currency'),
            [f'{NAMES["currencies"][v]} ({v})' for v in spec_enum(_A, 'currency')],
        ),
        'device': {
            **select(
                'Device',
                'Device profile used for the Amazon request.',
                spec_enum(_A, 'device'),
                [v.capitalize() for v in spec_enum(_A, 'device')],
            ),
            'default': spec_prop(_A, 'device')['default'],
        },
        'sort_by': {
            **section('Sorting and filters'),
            **select(
                'Sort by',
                'Amazon-native result ordering. Leave empty for the default.',
                spec_enum(_A, 'sort_by'),
                [v.replace('_', ' ').capitalize() for v in spec_enum(_A, 'sort_by')],
            ),
        },
        'category_id': text(
            'Category ID',
            'Amazon category or browse-node identifier.',
            pattern=spec_prop(_A, 'category_id')['pattern'],
            maxLength=40,
        ),
        'rh': text(
            'Refinements (rh)',
            'Comma-separated Amazon <code>key:value</code> refinements, as used in Amazon search URLs.',
            pattern=spec_prop(_A, 'rh')['pattern'],
            maxLength=2000,
        ),
        'merchant_id': text(
            'Merchant ID',
            'Restrict results to one Amazon merchant (seller) ID.',
            pattern=spec_prop(_A, 'merchant_id')['pattern'],
            maxLength=64,
        ),
        'direct_search': {
            'title': 'Direct category search',
            'type': 'boolean',
            'default': False,
            'description': "Use Amazon's direct category-search mode.",
        },
        'zero_trace': ZERO_TRACE,
    },
    required=['prismcrawlApiKey', 'query'],
    views={
        'products': table_view(
            'Products',
            'One row per product result.',
            [
                ('rank', 'Rank', 'number'),
                ('image', 'Image', 'image'),
                ('title', 'Title', 'text'),
                ('asin', 'ASIN', 'text'),
                ('price', 'Price', 'object'),
                ('rating', 'Rating', 'number'),
                ('reviews', 'Reviews', 'number'),
                ('sponsored', 'Sponsored', 'boolean'),
                ('prime', 'Prime', 'boolean'),
                ('best_seller', 'Best seller', 'boolean'),
                ('delivery', 'Delivery', 'text'),
                ('url', 'URL', 'link'),
            ],
        ),
    },
    target='Amazon search results',
    intro='searches **Amazon** through the PrismCrawl API and saves the **normalized JSON** to an Apify dataset: '
    'product results with **ASIN, title, price, rating, review count, Prime and badge flags, delivery and '
    "availability**, plus the page's **filters, categories, related searches**, and search information.",
    why=[
        '**Price and assortment monitoring**: track prices, badges, and positions for your products or competitors.',
        '**Product and keyword research**: see which products rank for a search and how they are rated.',
        '**Localized results**: search 20+ Amazon marketplaces with a specific delivery country, postal code, '
        'language, and display currency.',
    ],
    input_rows=[
        ('Search query', '`query`', 'What to search for. Required.'),
        ('Maximum pages', '–', 'Pages to fetch (1–20, default 1). Each page uses one credit.'),
        ('First page', '`page`', 'One-based page to start from.'),
        ('Amazon marketplace', '`amazon_domain`', 'For example `amazon.com`, `amazon.co.uk`, `amazon.de`.'),
        ('Language', '`language`', 'A locale supported by the marketplace, such as `en_US`.'),
        ('Delivery country / postal code', '`delivery_country` / `postal_code`', 'Delivery destination.'),
        ('Display currency', '`currency`', 'Changes displayed prices only.'),
        ('Device', '`device`', '`desktop` (default) or `mobile`.'),
        ('Sort by', '`sort_by`', 'For example `price_low_to_high`, `average_review`, `most_recent`.'),
        ('Category ID, refinements, merchant ID', '`category_id`, `rh`, `merchant_id`', 'Amazon-native filters.'),
        ('Direct category search', '`direct_search`', "Amazon's direct category-search mode."),
    ],
    input_notes='PrismCrawl checks marketplace-specific rules (supported locales and postal-code formats) and '
    'rejects invalid combinations without charging a credit.',
    example_input={
        'query': 'espresso machine',
        'amazon_domain': 'amazon.com',
        'sort_by': 'average_review',
        'maxPages': 2,
    },
    example_output=response_example('/v1/amazon/search'),  # type: ignore[arg-type]
    example_is_illustrative=False,
    data_fields=[
        (
            '`data.content.results[]`',
            'Products: `asin`, `rank`, `type`, `sponsored`, `title`, `url`, `image`, '
            '`price` / `old_price` (`raw`, `value`, `currency`), `rating`, `reviews`, `prime`, `best_seller`, '
            '`amazon_choice`, `badges`, `bought_last_month`, `coupon`, `delivery`, `availability`, and more.',
        ),
        ('`data.content.search_information`', 'Page classification (`surface`), total results, page, and total pages.'),
        (
            '`data.content.filters` / `categories` / `related_searches`',
            'Filters, categories, and related searches shown on the page.',
        ),
    ],
    tips=[
        '**Check `search_information.surface`.** `navigation` and `empty_results` pages are valid Amazon responses '
        'without product results.',
        "**Use a postal code for accurate delivery promises** in the marketplace's home country.",
    ],
    pagination_note='Later pages increase `page` by 1.',
    standby_note='Use `page` to request later pages.',
    related=['google-shopping-product', 'google-search'],
)


# Bing Search ------------------------------------------------------------------------------------------------------

_B = 'MicrosoftSearchRequest'
BING_SEARCH = ActorDef(
    slug='bing-search',
    name='prismcrawl-bing-search-api',
    title='PrismCrawl Bing Search API',
    description='Run live Bing searches through the PrismCrawl API and receive normalized search results, SERP '
    'features, and pagination metadata.',
    paths=['/v1/microsoft/search'],
    fields={
        'prismcrawlApiKey': API_KEY,
        'query': text(
            'Search query',
            'What to search for on Bing. Search operators such as <code>site:</code> work '
            'as usual. Limited to 8,192 UTF-8 bytes.',
            prefill='best coffee shops in Baltimore',
        ),
        'maxPages': max_pages(10, 'one Bing results page each'),
        'cc': {
            **section('Location and language'),
            **select(
                'Country (cc)',
                "Two-letter Bing result-country code, from Bing's published country list.",
                spec_enum(_B, 'cc'),
                [region_title(v) for v in spec_enum(_B, 'cc')],
            ),
            'default': spec_prop(_B, 'cc')['default'],
        },
        'setlang': text(
            'Interface language (setlang)',
            'Bing interface-language hint, such as <code>en-US</code>. It affects interface strings such as '
            'related-search labels; it does not restrict results to that language.',
            default=spec_prop(_B, 'setlang')['default'],
        ),
        'latitude': {
            **LATITUDE,
            'description': 'Searcher latitude. Bing uses it as a location signal to bias local '
            'relevance, not as a strict filter. Set together with longitude.',
        },
        'longitude': LONGITUDE,
        'device': select(
            'Device',
            'Search as a desktop, mobile, or tablet device.',
            spec_enum(_B, 'device'),
            [v.capitalize() for v in spec_enum(_B, 'device')],
        ),
        'tbs': {
            **section('Filters'),
            **text(
                'Time range (tbs)',
                "Time filter in Google-compatible syntax, translated to Bing's date filter: <code>qdr:d</code> (past "
                'day), <code>qdr:w</code> (past week), <code>qdr:m</code> (past month), <code>qdr:y</code> (past '
                'year), with an optional number such as <code>qdr:m6</code>; or a custom range '
                '<code>cdr:1,cd_min:8/1/2026,cd_max:8/12/2026</code>. Hour ranges are not supported.',
            ),
        },
        'safe': select(
            'SafeSearch',
            'Bing Strict SafeSearch (<code>active</code>) or unfiltered results '
            '(<code>off</code>). Leave empty for the default.',
            spec_enum(_B, 'safe'),
            [{'active': 'Strict (active)', 'off': 'Off'}[v] for v in spec_enum(_B, 'safe')],
        ),
        'zero_trace': ZERO_TRACE,
    },
    required=['prismcrawlApiKey', 'query'],
    views={'results': WEB_RESULTS_VIEW, 'serp_features': SERP_FEATURES_VIEW},
    target='Bing search results',
    intro='runs **live Bing searches** through the PrismCrawl API and saves the **normalized JSON response** to an '
    'Apify dataset: ranked results, **SERP features** when Bing shows them, and **pagination metadata**, in the same '
    'result format PrismCrawl uses for Google.',
    why=[
        '**Rank tracking beyond Google**: monitor positions on Bing, which also powers other search experiences.',
        '**SEO research**: compare Bing and Google results for the same keywords with a consistent result format.',
        '**AI agents and research tools**: give an agent a second live search source.',
    ],
    input_rows=[
        ('Search query', '`query`', 'The Bing search. Required.'),
        ('Maximum pages', '–', 'Pages to fetch (1–10, default 1). Each page uses one credit.'),
        ('Country', '`cc`', 'Two-letter Bing result country (default `us`).'),
        ('Interface language', '`setlang`', 'Interface-language hint (default `en-US`).'),
        ('Latitude / Longitude', '`coordinates`', 'Client location signal for local relevance.'),
        ('Device', '`device`', '`desktop`, `mobile`, or `tablet`.'),
        ('Time range', '`tbs`', 'For example `qdr:w` (past week). Hour ranges are not supported.'),
        ('SafeSearch', '`safe`', '`active` or `off`.'),
    ],
    example_input={'query': 'best espresso machines', 'cc': 'us', 'setlang': 'en-US', 'maxPages': 2},
    example_output=response_example('/v1/microsoft/search'),  # type: ignore[arg-type]
    example_is_illustrative=False,
    data_fields=[
        (
            '`data.content.results[]`',
            'Ranked results: `rank`, `type`, `title`, `url`, `display_url`, `snippet`, '
            '`domain`, `source_name`, `position`, `domain_info`.',
        ),
        ('`data.content.serp_features[]`', 'SERP features when present.'),
        ('`data.next_page_token`', 'The token the Actor uses to fetch the next page.'),
    ],
    tips=[
        '**Source HTML** (`html`), `color_scheme`, and the best-effort `sp` spelling hint are PrismCrawl parameters '
        "that this Actor doesn't expose.",
    ],
    pagination_note="The Actor follows Bing's `next_page_token` from each response.",
    standby_note="Pass the previous response's `next_page_token` in the body to get the next page.",
    related=['google-search'],
)


# Google Shopping Product ------------------------------------------------------------------------------------------

_SP = '/v1/google/shopping/product'
GOOGLE_SHOPPING_PRODUCT = ActorDef(
    slug='google-shopping-product',
    name='prismcrawl-google-shopping-product-api',
    title='PrismCrawl Google Shopping Product API',
    description='Look up a Google Shopping product through the PrismCrawl API: current details, merchant offers, '
    'images, specifications, and ratings as structured JSON.',
    paths=[_SP],
    fields={
        'prismcrawlApiKey': API_KEY,
        'id': text(
            'Product ID',
            'The <code>product_id</code> from a Google Shopping result, for example from the '
            'PrismCrawl Google Search API Actor with the Shopping vertical.',
            prefill=request_example(_SP)['id'],
        ),
        'query': text(
            'Original Shopping query',
            'The Google Shopping query that returned this product ID. Google '
            'uses it to supply current product details.',
            prefill=request_example(_SP)['query'],
        ),
        'country': {**section('Localization'), **COUNTRY},
        'language': LANGUAGE,
        'zero_trace': ZERO_TRACE,
    },
    required=['prismcrawlApiKey', 'id', 'query'],
    views={
        'product': table_view(
            'Product',
            'Product details.',
            [
                ('thumbnail', 'Image', 'image'),
                ('title', 'Title', 'text'),
                ('brand', 'Brand', 'text'),
                ('rating', 'Rating', 'number'),
                ('rating_count', 'Ratings', 'number'),
                ('description', 'Description', 'text'),
                ('offers', 'Offers', 'array'),
                ('specifications', 'Specifications', 'array'),
                ('product_id', 'Product ID', 'text'),
                ('url', 'URL', 'link'),
            ],
        ),
    },
    target='Google Shopping product details',
    intro='looks up a **Google Shopping product** by its product ID through the PrismCrawl API and saves the '
    '**normalized JSON**: current **title, brand, description, merchant offers, images, specifications, variants, '
    'and ratings** as supplied by Google.',
    why=[
        '**Price comparison**: see every merchant offer Google lists for a product.',
        '**Product data enrichment**: collect specifications, images, and ratings for catalog work.',
    ],
    input_rows=[
        ('Product ID', '`id`', 'A `product_id` from a Google Shopping result. Required.'),
        ('Original Shopping query', '`query`', 'The query that returned the product ID. Required.'),
        ('Country / Language', '`country` / `language`', 'For example `us` and `en`.'),
    ],
    example_input=request_example(_SP),
    example_output=catalog_example(
        'google',
        'product',
        [
            {
                'id': request_example(_SP)['id'],
                'product_id': request_example(_SP)['id'],
                'title': 'Example Wireless Headphones',
                'brand': 'Example Brand',
                'rating': 4.6,
                'rating_count': 1200,
                'offers': [{'merchant': 'Example Store', 'price': 329.99, 'currency': 'USD', 'price_text': '$329.99'}],
            }
        ],
        token=False,
    ),
    example_is_illustrative=True,
    data_fields=[
        (
            '`data.content.results[]`',
            'The product: `title`, `brand`, `description`, `rating`, `rating_count`, '
            '`images`, `specifications`, `variants`, `offers`, `product_id`, `url`.',
        ),
        (
            '`data.content.search_parameters.product_unavailable`',
            'True when the product was not found; see `product_unavailable_reason`.',
        ),
    ],
    tips=[
        '**Keep the original query.** Google needs the query that produced the product ID to return current details.',
        '**Get product IDs from Google Shopping results**: run the PrismCrawl Google Search API Actor with the '
        'Shopping vertical (`tbm: shop`) and read `items[].product_id` in the Shopping SERP features.',
    ],
    faq=[
        (
            'Why is the result empty?',
            "If the product is no longer among the query's Shopping results, PrismCrawl "
            'returns a successful empty response with `product_unavailable: true` and a reason. This still uses one '
            'credit, because the lookup completed.',
        ),
    ],
    related=['google-search', 'amazon-search'],
)


# Google Play ------------------------------------------------------------------------------------------------------

_GP = '/v1/google/play/reviews'
GOOGLE_PLAY = ActorDef(
    slug='google-play',
    name='prismcrawl-google-play-api',
    title='PrismCrawl Google Play API',
    description='Search Google Play apps, games, books, and movies, get product details, and collect app reviews '
    'through the PrismCrawl API as structured JSON.',
    paths=[
        '/v1/google/play/apps/search',
        '/v1/google/play/games/search',
        '/v1/google/play/books/search',
        '/v1/google/play/movies/search',
        '/v1/google/play/product',
        _GP,
    ],
    fields={
        'prismcrawlApiKey': API_KEY,
        'mode': mode_select(
            ['apps', 'games', 'books', 'movies', 'product', 'reviews'],
            [
                'Search apps',
                'Search or browse games',
                'Search books',
                'Search movies',
                'Product details',
                'App reviews',
            ],
            'apps',
            'Choose what to fetch. Searches use <strong>Search query</strong>; product details and reviews use '
            '<strong>Product ID</strong>.',
        ),
        'query': text(
            'Search query',
            'Text to search for (search modes). Optional for games when a games category is set.',
            prefill='weather',
        ),
        'gamesCategory': text(
            'Games category',
            'For games: a Google Play Games category to browse, such as '
            '<code>GAME_ACTION</code> or <code>GAME_PUZZLE</code>. Combine with a query to return '
            'only games in that category.',
        ),
        'id': text(
            'Product ID',
            'For product details and reviews: the ID from Google Play search results or the '
            '<code>id</code> parameter of the store URL, such as <code>com.google.android.apps.maps</code>. '
            'App names are not IDs.',
            pattern='^[a-zA-Z0-9_.-]{1,250}$',
        ),
        'productCategory': select(
            'Product type',
            'For product details: the store section of the product. Leave empty for apps.',
            spec_enum('Catalog_google_play_product_Request', 'category'),
            ['Apps', 'Books', 'Movies', 'Audiobooks', 'TV'],
        ),
        'sort_by': select(
            'Review order',
            'For reviews: the order to return them in.',
            spec_enum('Catalog_google_play_reviews_Request', 'sort_by'),
            ['Newest', 'Most relevant', 'Rating'],
        ),
        'maxPages': max_pages(100, 'searches and reviews only'),
        'limit': integer(
            'Items per page',
            'Maximum results or reviews per page (1–100). Google Play may return fewer.',
            minimum=1,
            maximum=100,
        ),
        'country': {**section('Localization'), **COUNTRY},
        'language': LANGUAGE,
        'device': DEVICE,
        'zero_trace': ZERO_TRACE,
    },
    required=['prismcrawlApiKey'],
    views={'items': APPS_VIEW, 'reviews': REVIEWS_VIEW},
    target='Google Play data',
    intro='searches **Google Play** apps, games, books, and movies, fetches **product details**, and collects **app '
    'reviews** through the PrismCrawl API. Results include **title, developer, rating, rating count, price, installs, '
    'category, version, screenshots**, and for reviews the **rating, text, author, date, app version, and developer '
    'response**.',
    why=[
        '**App store optimization (ASO)**: see which apps rank for your keywords in each country.',
        '**Competitor tracking**: monitor ratings, installs, versions, and release notes.',
        '**Review analysis**: collect user reviews to find bugs, feature requests, and sentiment.',
    ],
    input_rows=[
        ('What to fetch', '–', '`apps`, `games`, `books`, `movies` (searches), `product`, or `reviews`.'),
        ('Search query', '`query`', 'For searches.'),
        ('Games category', '`category`', 'For game searches, such as `GAME_ACTION`.'),
        ('Product ID', '`id`', 'For product details and reviews, such as `com.google.android.apps.maps`.'),
        ('Product type', '`category`', 'For product details: `apps`, `books`, `movies`, `audiobooks`, or `tv`.'),
        ('Review order', '`sort_by`', 'For reviews: `newest`, `relevant`, or `rating`.'),
        ('Maximum pages', '–', 'Pages to fetch (1–100, default 1). Each page uses one credit.'),
        ('Items per page', '`limit`', '1–100.'),
        ('Country / Language / Device', '`country` / `language` / `device`', 'For example `us`, `en`, `mobile`.'),
    ],
    input_notes="Fields that don't apply to the selected mode are ignored, and the run log lists them.",
    example_input={'mode': 'reviews', **request_example(_GP), 'sort_by': 'newest', 'limit': 50, 'maxPages': 2},
    example_output=catalog_example(
        'google_play',
        'reviews',
        [
            {
                'id': '<review id>',
                'position': 1,
                'rating': 4,
                'text': 'Accurate directions, but offline maps could be easier to find.',
                'author': 'Example User',
                'date': '2026-09-20',
                'version': '11.140.0',
                'helpful_votes': 12,
            }
        ],
    ),
    example_is_illustrative=True,
    data_fields=[
        (
            '`data.content.results[]` (searches, product)',
            'Apps and other items: `id`, `title`, `developer`, `rating`, '
            '`rating_count`, `price` / `price_text`, `free`, `installs`, `category`, `content_rating`, `version`, '
            '`updated`, `screenshots`, `description`, `url`.',
        ),
        (
            '`data.content.results[]` (reviews)',
            'Reviews: `rating`, `text`, `author`, `date`, `version`, `helpful_votes`, `developer_response`.',
        ),
    ],
    tips=[
        '**Find product IDs with a search first**, then run product details or reviews on the `id` values.',
        '**Game searches only return verified games.** Pages can be shorter than the requested limit while more '
        'pages remain.',
    ],
    pagination_note='The Actor follows `next_page_token` from each response. Product details are a single page.',
    standby_note="Pass the previous response's `next_page_token` in the body to get the next page.",
    related=['apple-app-store'],
)


# Apple App Store --------------------------------------------------------------------------------------------------

_AS = '/v1/apple/app-store/reviews'
APPLE_APP_STORE = ActorDef(
    slug='apple-app-store',
    name='prismcrawl-app-store-api',
    title='PrismCrawl Apple App Store API',
    description='Search the Apple App Store, get app details, and collect app reviews through the PrismCrawl API as '
    'structured JSON.',
    paths=['/v1/apple/app-store/search', '/v1/apple/app-store/product', _AS],
    fields={
        'prismcrawlApiKey': API_KEY,
        'mode': mode_select(
            ['search', 'product', 'reviews'],
            ['Search apps', 'App details', 'App reviews'],
            'search',
            'Choose what to fetch. Search uses <strong>Search query</strong>; app details and reviews use '
            '<strong>App ID</strong>.',
        ),
        'query': text('Search query', 'For search: text to search the App Store for.', prefill='weather'),
        'category': select(
            'Platform',
            'For search: which App Store catalog to search.',
            spec_enum('Catalog_apple_app_store_Request', 'category'),
            ['iPhone apps', 'iPad apps', 'Mac apps'],
        ),
        'id': text(
            'App ID',
            'For app details and reviews: the numeric App Store ID, as returned by search or shown in '
            "the app's URL (for example <code>284882215</code>).",
        ),
        'sort_by': select(
            'Review order',
            'For reviews: the order to return them in.',
            spec_enum('Catalog_apple_app_store_reviews_Request', 'sort_by'),
            ['Newest', 'Most helpful'],
        ),
        'maxPages': max_pages(10, 'search and reviews only'),
        'limit': integer(
            'Items per page',
            'Maximum apps or reviews per page (1–100). Apple may return fewer.',
            minimum=1,
            maximum=100,
        ),
        'country': {**section('Localization'), **COUNTRY},
        'language': text(
            'Language',
            'For search and app details: a language code such as <code>en</code>. Search '
            'supports <code>en</code> and <code>ja</code>. Not used for reviews.',
        ),
        'device': DEVICE,
        'zero_trace': ZERO_TRACE,
    },
    required=['prismcrawlApiKey'],
    views={'items': APPS_VIEW, 'reviews': REVIEWS_VIEW},
    target='Apple App Store data',
    intro='searches the **Apple App Store**, fetches **app details**, and collects **app reviews** through the '
    'PrismCrawl API. Results include **title, developer, rating, rating count, price, category, version, release '
    'notes, screenshots**, and for reviews the **rating, title, text, author, date, and app version**.',
    why=[
        '**App store optimization (ASO)**: see which apps rank for your keywords in each storefront.',
        '**Competitor tracking**: monitor ratings, versions, and release notes.',
        '**Review analysis**: collect reviews to find bugs, feature requests, and sentiment.',
    ],
    input_rows=[
        ('What to fetch', '–', '`search`, `product` (app details), or `reviews`.'),
        ('Search query', '`query`', 'For search.'),
        ('Platform', '`category`', 'For search: `software` (iPhone), `iPadSoftware`, or `macSoftware`.'),
        ('App ID', '`id`', 'For app details and reviews, such as `284882215`.'),
        ('Review order', '`sort_by`', 'For reviews: `newest` or `helpful`.'),
        ('Maximum pages', '–', 'Pages to fetch (1–10, default 1). Each page uses one credit.'),
        ('Items per page', '`limit`', '1–100.'),
        ('Country / Language / Device', '`country` / `language` / `device`', 'For example `us`, `en`, `mobile`.'),
    ],
    input_notes="Fields that don't apply to the selected mode are ignored, and the run log lists them.",
    example_input={'mode': 'reviews', **request_example(_AS), 'sort_by': 'newest', 'maxPages': 3},
    example_output=catalog_example(
        'apple_app_store',
        'reviews',
        [
            {
                'id': '<review id>',
                'position': 1,
                'rating': 5,
                'title': 'Works great',
                'text': 'Fast and reliable after the latest update.',
                'author': 'Example User',
                'date': '2026-09-18',
                'version': '9.12',
            }
        ],
    ),
    example_is_illustrative=True,
    data_fields=[
        (
            '`data.content.results[]` (search, details)',
            'Apps: `id`, `title`, `developer`, `rating`, `rating_count`, '
            '`price` / `price_text`, `category`, `version`, `release_notes`, `screenshots`, `description`, `url`.',
        ),
        ('`data.content.results[]` (reviews)', 'Reviews: `rating`, `title`, `text`, `author`, `date`, `version`.'),
    ],
    tips=[
        '**Search covers up to 200 apps per query.** Pagination stays within that inventory.',
        "**Apple's review feed exposes up to 10 pages.**",
    ],
    pagination_note='The Actor follows `next_page_token` from each response. App details are a single page.',
    standby_note="Pass the previous response's `next_page_token` in the body to get the next page.",
    related=['google-play'],
)


# Yelp -------------------------------------------------------------------------------------------------------------

_Y = '/v1/yelp/search'
YELP = ActorDef(
    slug='yelp',
    name='prismcrawl-yelp-api',
    title='PrismCrawl Yelp API',
    description='Look up Yelp businesses by keyword and location, and collect complete Yelp reviews, through the '
    'PrismCrawl API as structured JSON.',
    paths=[_Y, '/v1/yelp/reviews'],
    fields={
        'prismcrawlApiKey': API_KEY,
        'mode': mode_select(
            ['search', 'reviews'],
            ['Business lookup', 'Business reviews'],
            'search',
            'Look up businesses by keyword and location, or fetch the reviews of one business.',
        ),
        'query': text(
            'Search query',
            'For business lookup: what to search for, such as <code>restaurants</code>.',
            prefill=request_example(_Y)['query'],
        ),
        'location': text(
            'Location',
            'For business lookup: where to search, such as <code>Austin, TX</code>. Use '
            'either a location or coordinates.',
            prefill=request_example(_Y)['location'],
        ),
        'latitude': {
            **LATITUDE,
            'description': 'For business lookup: latitude to search around, instead of a '
            'location. Set together with longitude.',
        },
        'longitude': LONGITUDE,
        'id': text(
            'Business alias',
            'For reviews: the business alias from its Yelp URL, such as <code>halcyon-austin-2</code>.',
        ),
        'sort_by': select(
            'Review order',
            'For reviews: the order to return them in.',
            spec_enum('Catalog_yelp_reviews_Request', 'sort_by'),
            ['Recommended', 'Newest', 'Oldest', 'Highest rating', 'Lowest rating', 'Elite reviewers first'],
        ),
        'maxPages': max_pages(100, 'one page of businesses or reviews each'),
        'page': integer(
            'First page',
            'One-based page to start from. Business lookup covers the first 200 businesses.',
            minimum=1,
            maximum=1000,
        ),
        'limit': integer(
            'Items per page',
            'Businesses or reviews per page (1–100). Business lookup defaults to 20.',
            minimum=1,
            maximum=100,
        ),
        'language': {**section('Localization'), **LANGUAGE},
        'device': DEVICE,
        'zero_trace': ZERO_TRACE,
    },
    required=['prismcrawlApiKey'],
    views={
        'businesses': table_view(
            'Businesses',
            'One row per business (business lookup).',
            [
                ('rank', 'Rank', 'number'),
                ('thumbnail', 'Photo', 'image'),
                ('title', 'Name', 'text'),
                ('rating', 'Rating', 'number'),
                ('review_count', 'Reviews', 'number'),
                ('price', 'Price', 'text'),
                ('categories', 'Categories', 'array'),
                ('city', 'City', 'text'),
                ('snippet', 'Snippet', 'text'),
                ('id', 'Alias / ID', 'text'),
                ('url', 'URL', 'link'),
            ],
        ),
        'reviews': REVIEWS_VIEW,
    },
    target='Yelp businesses and reviews',
    intro='looks up **Yelp businesses** by keyword and location, and collects **complete Yelp reviews** for any '
    'business, through the PrismCrawl API. Business results include **name, rating, review count, price, categories, '
    'neighborhood, coordinates, and photos**; reviews include **rating, text, author, date, and photos**.',
    why=[
        '**Local lead generation**: list businesses of a type in any city.',
        '**Reputation monitoring**: collect new reviews for your locations or competitors on a schedule.',
        '**Market research**: compare ratings and price levels across an area.',
    ],
    input_rows=[
        ('What to fetch', '–', '`search` (business lookup) or `reviews`.'),
        ('Search query', '`query`', 'For business lookup.'),
        (
            'Location or Latitude / Longitude',
            '`location` / `coordinates`',
            'For business lookup: exactly one is required.',
        ),
        ('Business alias', '`id`', 'For reviews, such as `halcyon-austin-2`.'),
        (
            'Review order',
            '`sort_by`',
            'For reviews: `recommended`, `newest`, `oldest`, `highest_rating`, `lowest_rating`, `elites`.',
        ),
        ('Maximum pages', '–', 'Pages to fetch (1–100, default 1). Each page uses one credit.'),
        ('First page', '`page`', 'One-based page to start from.'),
        ('Items per page', '`limit`', '1–100.'),
        ('Language / Device', '`language` / `device`', 'For example `en`, `mobile`.'),
    ],
    input_notes="Business lookup covers Yelp's first 200 businesses for a search, so `(page - 1) × limit` must be "
    "under 200. Fields that don't apply to the selected mode are ignored, and the run log lists them.",
    example_input={'mode': 'search', **request_example(_Y), 'limit': 20, 'maxPages': 3},
    example_output=catalog_example(
        'yelp',
        'search',
        [
            {
                'id': '<business alias>',
                'rank': 1,
                'title': 'Example Cafe',
                'rating': 4.5,
                'review_count': 210,
                'price': '$$',
                'city': 'Austin',
                'url': 'https://www.yelp.com/biz/<business alias>',
            }
        ],
        token=False,
    ),
    example_is_illustrative=True,
    data_fields=[
        (
            '`data.content.results[]` (lookup)',
            'Businesses: `id`, `business_id`, `title`, `rating`, `review_count`, '
            '`price`, `categories`, `city`, `neighborhoods`, `coordinates`, `snippet`, `photos`, `url`.',
        ),
        ('`data.content.results[]` (reviews)', 'Reviews: `rating`, `text`, `author`, `date`, `photos`.'),
        (
            '`data.content.search_parameters`',
            'Includes `location_not_found`, `source_result_count`, and `review_count` when relevant.',
        ),
    ],
    tips=["**Get business aliases from a lookup**: each result's Yelp URL ends with its alias."],
    faq=[
        (
            'Why did a lookup return no businesses?',
            "If Yelp can't resolve the location, PrismCrawl returns a "
            'successful empty result with `location_not_found: true`. This still uses one credit, because the lookup '
            'completed.',
        ),
    ],
    pagination_note='Later pages increase `page` by 1.',
    standby_note='Use `page` to request later pages.',
    related=['google-maps-places', 'tripadvisor'],
)


# Tripadvisor ------------------------------------------------------------------------------------------------------

_T = '/v1/tripadvisor/search'
TRIPADVISOR = ActorDef(
    slug='tripadvisor',
    name='prismcrawl-tripadvisor-api',
    title='PrismCrawl Tripadvisor API',
    description='Search Tripadvisor hotels, restaurants, and attractions, get place details, and collect reviews '
    'through the PrismCrawl API as structured JSON.',
    paths=[_T, '/v1/tripadvisor/place', '/v1/tripadvisor/reviews'],
    fields={
        'prismcrawlApiKey': API_KEY,
        'mode': mode_select(
            ['search', 'place', 'reviews'],
            ['Search', 'Place details', 'Place reviews'],
            'search',
            'Search Tripadvisor, or fetch the details or reviews of one place.',
        ),
        'query': text(
            'Search query',
            'For search: what to look for, such as <code>restaurants</code> or <code>hotels</code>.',
            prefill=request_example(_T)['query'],
        ),
        'location': text(
            'Location',
            'For search: where to search, such as <code>Austin, TX</code>.',
            prefill=request_example(_T)['location'],
        ),
        'id': text(
            'Place URL',
            'For place details and reviews: the canonical Tripadvisor URL of the hotel, '
            'restaurant, or attraction, as returned by search.',
        ),
        'sort_by': select(
            'Review order',
            'For reviews: the order to return them in.',
            spec_enum('Catalog_tripadvisor_reviews_Request', 'sort_by'),
            ['Recommended', 'Newest', 'Most recent', 'Detailed reviews first'],
        ),
        'maxPages': max_pages(100, 'search and reviews only'),
        'limit': integer(
            'Items per page', 'Results per page (1–30 for search) or reviews per page (1–100).', minimum=1, maximum=100
        ),
        'language': {**section('Localization'), **LANGUAGE},
        'device': DEVICE,
        'zero_trace': ZERO_TRACE,
    },
    required=['prismcrawlApiKey'],
    views={
        'places': table_view(
            'Places',
            'One row per place (search and place details).',
            [
                ('position', 'Position', 'number'),
                ('thumbnail', 'Photo', 'image'),
                ('title', 'Name', 'text'),
                ('category', 'Category', 'text'),
                ('rating', 'Rating', 'number'),
                ('review_count', 'Reviews', 'number'),
                ('address', 'Address', 'text'),
                ('phone', 'Phone', 'text'),
                ('website', 'Website', 'link'),
                ('url', 'Tripadvisor URL', 'link'),
            ],
        ),
        'reviews': REVIEWS_VIEW,
    },
    target='Tripadvisor places and reviews',
    intro='searches **Tripadvisor** hotels, restaurants, and attractions, fetches **place details**, and collects '
    '**reviews** through the PrismCrawl API. Places include **name, category, rating, review count, address, phone, '
    'website, and coordinates**; reviews include **rating, text, author, and date**.',
    why=[
        '**Travel and hospitality research**: compare ratings and review volume across hotels or restaurants.',
        '**Reputation monitoring**: collect new reviews for your properties or competitors.',
        '**Lead generation**: list places in a destination with contact details.',
    ],
    input_rows=[
        ('What to fetch', '–', '`search`, `place` (details), or `reviews`.'),
        ('Search query / Location', '`query` / `location`', 'For search.'),
        ('Place URL', '`id`', 'For details and reviews: the canonical Tripadvisor URL from search.'),
        ('Review order', '`sort_by`', 'For reviews: `recommended`, `newest`, `most_recent`, or `detailed_review`.'),
        ('Maximum pages', '–', 'Pages to fetch (1–100, default 1). Each page uses one credit.'),
        ('Items per page', '`limit`', '1–30 for search, 1–100 for reviews.'),
        ('Language / Device', '`language` / `device`', 'For example `en`, `mobile`.'),
    ],
    input_notes="Fields that don't apply to the selected mode are ignored, and the run log lists them.",
    example_input={'mode': 'search', **request_example(_T), 'maxPages': 2},
    example_output=catalog_example(
        'tripadvisor',
        'search',
        [
            {
                'id': '<place id>',
                'position': 1,
                'title': 'Example Restaurant',
                'category': 'Restaurant',
                'rating': 4.5,
                'review_count': 850,
                'url': 'https://www.tripadvisor.com/Restaurant_Review-<...>.html',
            }
        ],
    ),
    example_is_illustrative=True,
    data_fields=[
        (
            '`data.content.results[]` (search, place)',
            'Places: `title`, `category`, `rating`, `review_count`, '
            '`address`, `phone`, `website`, `latitude` / `longitude`, `description`, `url`.',
        ),
        ('`data.content.results[]` (reviews)', 'Reviews: `rating`, `title`, `text`, `author`, `date`.'),
    ],
    tips=['**Use the `url` from search results** as the Place URL for details and reviews.'],
    pagination_note='The Actor follows `next_page_token` from each response. Place details are a single page.',
    standby_note="Pass the previous response's `next_page_token` in the body to get the next page.",
    related=['yelp', 'google-maps-reviews'],
)


# YouTube --------------------------------------------------------------------------------------------------------

VIDEOS_VIEW = table_view(
    'Videos and channels',
    'One row per video, channel, playlist, or transcript segment.',
    [
        ('position', 'Position', 'number'),
        ('thumbnail', 'Thumbnail', 'image'),
        ('type', 'Type', 'text'),
        ('title', 'Title', 'text'),
        ('channel', 'Channel', 'text'),
        ('view_count', 'Views', 'number'),
        ('duration', 'Duration', 'text'),
        ('published_at', 'Published', 'text'),
        ('start_seconds', 'Start (s)', 'number'),
        ('text', 'Text', 'text'),
        ('url', 'URL', 'link'),
    ],
)
_YT = '/v1/youtube/search'
YOUTUBE = ActorDef(
    slug='youtube',
    name='prismcrawl-youtube-api',
    title='PrismCrawl YouTube API',
    description='Search YouTube, get video and channel details, and download video transcripts through the '
    'PrismCrawl API as structured JSON.',
    paths=[_YT, '/v1/youtube/video', '/v1/youtube/channel', '/v1/youtube/transcript'],
    fields={
        'prismcrawlApiKey': API_KEY,
        'mode': mode_select(
            ['search', 'video', 'channel', 'transcript'],
            ['Search videos', 'Video details', 'Channel videos', 'Video transcript'],
            'search',
            'Choose what to fetch. Search uses <strong>Search query</strong>; the others use '
            '<strong>Video or channel ID</strong>.',
        ),
        'query': text('Search query', 'For search: text to search YouTube for.', prefill='espresso machine review'),
        'sp': text(
            'Search filter token',
            'For search: the <code>sp</code> value from a YouTube search filter link, such as upload date or '
            'duration. Kept fixed while paging.',
        ),
        'id': text(
            'Video or channel ID',
            'A video ID such as <code>jNQXAC9IVRw</code>, or a channel handle or ID such as <code>@Google</code>.',
        ),
        'tab': select(
            'Channel tab',
            'For channels: which part of the channel to list. Defaults to videos.',
            spec_enum('Catalog_youtube_channel_Request', 'tab'),
            ['Videos', 'Shorts', 'Live streams', 'Podcasts', 'Playlists', 'Posts'],
        ),
        'sort': select(
            'Channel sort',
            'For channels: <code>latest</code>, <code>popular</code>, or <code>oldest</code> for videos, '
            'shorts, and streams; <code>dd</code> (date added) or <code>lad</code> (last video added) for playlists.',
            spec_enum('Catalog_youtube_channel_Request', 'sort'),
            ['Latest', 'Popular', 'Oldest', 'Date added (playlists)', 'Last video added (playlists)'],
        ),
        'search_query': text('Search within channel', "For channels: search the channel's videos and playlists."),
        'about': {
            'title': 'Include channel details',
            'type': 'boolean',
            'description': 'For channels: also return the country, join date, total views, and links. Uses an '
            'extra source request.',
        },
        'language_code': text(
            'Transcript language',
            'For transcripts: preferred caption language, such as <code>en</code>. Falls back to the first '
            'available track.',
        ),
        'title': text('Caption track title', 'For transcripts: pick a caption track by its title.'),
        'type': select(
            'Caption type',
            'For transcripts: set to use automatically generated captions.',
            spec_enum('Catalog_youtube_video_transcript_Request', 'type'),
            ['Auto-generated'],
        ),
        'maxPages': max_pages(20, 'search, videos, and channels only'),
        'country': {**section('Localization'), **COUNTRY},
        'language': text('Language', 'Interface language, such as <code>en</code>. Not used for transcripts.'),
        'device': DEVICE,
        'zero_trace': ZERO_TRACE,
    },
    required=['prismcrawlApiKey'],
    views={'items': VIDEOS_VIEW},
    target='YouTube data',
    intro='searches **YouTube**, fetches **video details** and **channel listings**, and downloads **video '
    'transcripts** through the PrismCrawl API. Results include **title, channel, views, duration, publish date, '
    'thumbnail, and URL**, and transcripts come back as timed text segments.',
    why=[
        '**Content research**: see which videos rank for a topic and how they perform.',
        "**Channel tracking**: list a channel's latest or most popular videos, shorts, and streams.",
        '**Transcripts for AI**: feed video captions to summarization, search, or RAG pipelines.',
    ],
    input_rows=[
        ('What to fetch', '–', '`search`, `video`, `channel`, or `transcript`.'),
        ('Search query', '`query`', 'For search.'),
        ('Video or channel ID', '`id`', 'For video details, channels, and transcripts.'),
        ('Channel tab / sort', '`tab` / `sort`', 'For channels, such as `videos` and `popular`.'),
        ('Transcript language', '`language_code`', 'For transcripts, such as `en`.'),
        ('Maximum pages', '–', 'Pages to fetch (1–20, default 1). Each page uses one credit.'),
        ('Country / Language / Device', '`country` / `language` / `device`', 'For example `us`, `en`, `mobile`.'),
    ],
    input_notes="Fields that don't apply to the selected mode are ignored, and the run log lists them.",
    example_input={'mode': 'search', **request_example(_YT), 'maxPages': 2},
    example_output=catalog_example(
        'youtube',
        'search',
        [
            {
                'position': 1,
                'type': 'video',
                'id': '<video id>',
                'title': 'Example video title',
                'channel': 'Example Channel',
                'view_count': 120000,
                'duration': '12:34',
                'published_at': '2026-10-01',
                'url': 'https://www.youtube.com/watch?v=<video id>',
            }
        ],
    ),
    example_is_illustrative=True,
    data_fields=[
        (
            '`data.content.results[]` (search, channel)',
            'Videos, channels, and playlists: `type`, `id`, `title`, `channel`, `channel_id`, `view_count`, '
            '`duration`, `published_at`, `thumbnail`, `url`.',
        ),
        ('`data.content.results[]` (video)', 'Video details, plus `likes`, `comments`, and `related_videos`.'),
        ('`data.content.results[]` (transcript)', 'Caption segments: `start_seconds`, `duration_seconds`, `text`.'),
    ],
    tips=[
        '**Transcripts need public captions.** Videos without captions return an empty result.',
        '**Use a search filter token** (`sp`) from a YouTube filter link to filter by upload date, type, or length.',
    ],
    pagination_note='The Actor follows `next_page_token` from each response. Transcripts are a single page.',
    standby_note="Pass the previous response's `next_page_token` in the body to get the next page.",
)


# Walmart --------------------------------------------------------------------------------------------------------

PRODUCTS_VIEW = table_view(
    'Products and offers',
    'One row per product or seller offer.',
    [
        ('position', 'Position', 'number'),
        ('thumbnail', 'Image', 'image'),
        ('title', 'Title', 'text'),
        ('id', 'ID', 'text'),
        ('price', 'Price', 'number'),
        ('currency', 'Currency', 'text'),
        ('rating', 'Rating', 'number'),
        ('review_count', 'Reviews', 'number'),
        ('seller', 'Seller', 'text'),
        ('seller_name', 'Seller name', 'text'),
        ('availability', 'Availability', 'text'),
        ('url', 'URL', 'link'),
    ],
)
_W = '/v1/walmart/search'
WALMART = ActorDef(
    slug='walmart',
    store_title='Walmart Product, Seller & Review Scraper | PrismCrawl API',
    store_description=(
        'Search Walmart and get product details, prices, availability, third-party seller offers, and '
        'customer reviews as clean JSON. Track prices, compare sellers, and analyze reviews. Uses your '
        'PrismCrawl API key, with 100 free credits and no card needed.'
    ),
    name='prismcrawl-walmart-api',
    title='PrismCrawl Walmart API',
    description='Search Walmart products, get product details and seller offers, and collect product reviews '
    'through the PrismCrawl API as structured JSON.',
    paths=[_W, '/v1/walmart/product', '/v1/walmart/product/sellers', '/v1/walmart/reviews'],
    fields={
        'prismcrawlApiKey': API_KEY,
        'mode': mode_select(
            ['search', 'product', 'sellers', 'reviews'],
            ['Search products', 'Product details', 'Seller offers', 'Product reviews'],
            'search',
            'Choose what to fetch. Search uses <strong>Search query</strong>; the others use '
            '<strong>Product ID</strong>.',
        ),
        'query': text('Search query', 'For search: text to search Walmart for.', prefill='coffee maker'),
        'cat_id': text(
            'Category path',
            'For search (US only): an underscore-separated Walmart category path. Can replace the query.',
        ),
        'sort': select(
            'Search sort',
            'For search: result order. Walmart Mexico supports price and best match only.',
            spec_enum('Catalog_walmart_Request', 'sort'),
            ['Price: low to high', 'Price: high to low', 'Best sellers', 'Best match', 'Highest rated', 'Newest'],
        ),
        'min_price': number('Minimum price', 'For search.', minimum=0),
        'max_price': number('Maximum price', 'For search.', minimum=0),
        'id': text('Product ID', 'For details, sellers, and reviews: the product ID from search results.'),
        'store_id': text(
            'Store ID',
            'Walmart store for local availability and pricing. Required for seller offers.',
        ),
        'rating': integer(
            'Star rating', 'For reviews: only return reviews with this rating (1–5).', minimum=1, maximum=5
        ),
        'reviewSort': select(
            'Review sort',
            'For reviews: the order to return them in.',
            spec_enum('Catalog_walmart_reviews_Request', 'sort'),
            ['Most relevant', 'Most helpful', 'Newest', 'Oldest', 'Highest rating', 'Lowest rating'],
        ),
        'maxPages': max_pages(100, 'search and reviews only'),
        'walmart_domain': {
            **section('Marketplace'),
            **select(
                'Marketplace',
                'For search: Walmart US or Walmart Mexico. Defaults to walmart.com.',
                spec_enum('Catalog_walmart_Request', 'walmart_domain'),
                ['Walmart US (walmart.com)', 'Walmart Mexico (walmart.com.mx)'],
            ),
        },
        'device': DEVICE,
        'zero_trace': ZERO_TRACE,
    },
    required=['prismcrawlApiKey'],
    views={'items': PRODUCTS_VIEW, 'reviews': REVIEWS_VIEW},
    target='Walmart product data',
    intro='searches **Walmart**, fetches **product details** and **seller offers**, and collects **product reviews** '
    'through the PrismCrawl API. Results include **title, price, rating, review count, seller, availability, '
    'images, and URL**.',
    why=[
        '**Price monitoring**: track prices and availability by store.',
        '**Marketplace research**: compare third-party seller offers for the same item.',
        '**Review analysis**: collect reviews to understand product quality and complaints.',
    ],
    input_rows=[
        ('What to fetch', '–', '`search`, `product`, `sellers`, or `reviews`.'),
        ('Search query / Category path', '`query` / `cat_id`', 'For search; one is required.'),
        ('Search sort', '`sort`', 'For search, such as `price_low` or `best_seller`.'),
        ('Product ID', '`id`', 'For details, sellers, and reviews.'),
        ('Store ID', '`store_id`', 'Local availability and pricing; required for seller offers.'),
        ('Review sort / Star rating', '`sort` / `rating`', 'For reviews.'),
        ('Maximum pages', '–', 'Pages to fetch (1–100, default 1). Each page uses one credit.'),
    ],
    input_notes="Fields that don't apply to the selected mode are ignored, and the run log lists them.",
    example_input={'mode': 'search', **request_example(_W), 'sort': 'best_seller', 'maxPages': 2},
    example_output=catalog_example(
        'walmart',
        'search',
        [
            {
                'position': 1,
                'id': '<product id>',
                'title': 'Example 12-cup coffee maker',
                'price': 29.97,
                'currency': 'USD',
                'rating': 4.5,
                'review_count': 1820,
                'seller': 'Walmart.com',
                'availability': 'in_stock',
                'url': 'https://www.walmart.com/ip/<product id>',
            }
        ],
    ),
    example_is_illustrative=True,
    data_fields=[
        (
            '`data.content.results[]` (search, details)',
            'Products: `id`, `title`, `price`, `currency`, `rating`, `review_count`, `seller`, `availability`, '
            '`sponsored`, `thumbnail`, `url`.',
        ),
        (
            '`data.content.results[]` (sellers)',
            'Offers: `seller_name`, `seller_type`, `price`, `availability`, `return_policy`.',
        ),
        REVIEW_FIELDS_ROW,
    ],
    tips=[
        '**Seller offers need a store ID.** Use the store whose prices you want to compare.',
        '**Search returns filters too** when Walmart shows them, so you can refine with `facet` in Standby mode.',
    ],
    pagination_note='The Actor increments `page` while `has_next_page` is true. Details and seller offers are a '
    'single page.',
    standby_note='Pass `page` in the body to get a specific page.',
    related=['amazon-search', 'ebay'],
)


# eBay -----------------------------------------------------------------------------------------------------------

_E = '/v1/ebay/search'
EBAY = ActorDef(
    slug='ebay',
    name='prismcrawl-ebay-api',
    title='PrismCrawl eBay API',
    description='Search eBay listings, get item details, and look up sellers and their inventory through the '
    'PrismCrawl API as structured JSON.',
    paths=[_E, '/v1/ebay/product', '/v1/ebay/seller'],
    fields={
        'prismcrawlApiKey': API_KEY,
        'mode': mode_select(
            ['search', 'product', 'seller'],
            ['Search listings', 'Item details', 'Seller'],
            'search',
            'Choose what to fetch. Search uses <strong>Search query</strong>; item details and sellers use '
            '<strong>Item or seller ID</strong>.',
        ),
        'query': text('Search query', 'For search: text to search eBay for.', prefill='vintage camera'),
        'category_id': text('Category ID', 'For search: a numeric eBay category ID. Can replace the query.'),
        'buying_format': select(
            'Buying format',
            'For search: auctions, Buy It Now, or Best Offer.',
            spec_enum('Catalog_ebay_Request', 'buying_format'),
            ['Auction', 'Buy It Now', 'Best Offer'],
        ),
        '_udlo': number('Minimum price', 'For search.', minimum=0),
        '_udhi': number('Maximum price', 'For search.', minimum=0),
        'show_only': text(
            'Listing filters',
            'For search: comma-separated eBay filters, such as free shipping or free returns.',
        ),
        'LH_ItemCondition': text(
            'Item condition IDs',
            'For search: pipe-separated eBay condition IDs, such as <code>1000|3000</code>.',
        ),
        '_stpos': text('Postal code', 'For search: ZIP or postal code for delivery and distance filters.'),
        'id': text('Item or seller ID', 'For item details: the item ID. For sellers: the public username.'),
        'shipping_country': select(
            'Ship to',
            'For item details: the destination used for delivery estimates.',
            spec_enum('Catalog_ebay_product_Request', 'shipping_country'),
            [region_title(code) for code in spec_enum('Catalog_ebay_product_Request', 'shipping_country')],
        ),
        'type': select(
            'Seller inventory',
            "For sellers: list the seller's user or store inventory. Leave empty for the profile only.",
            spec_enum('Catalog_ebay_seller_Request', 'type'),
            ['User listings', 'Store listings'],
        ),
        'limit': integer(
            'Items per page',
            'For seller inventory: maximum listings per page (1–100).',
            minimum=1,
            maximum=100,
        ),
        'maxPages': max_pages(100, 'search and seller inventory only'),
        'ebay_domain': {
            **section('Marketplace'),
            **select(
                'Marketplace',
                'Regional eBay site. Defaults to ebay.com.',
                spec_enum('Catalog_ebay_Request', 'ebay_domain'),
                spec_enum('Catalog_ebay_Request', 'ebay_domain'),
            ),
        },
        'device': DEVICE,
        'zero_trace': ZERO_TRACE,
    },
    required=['prismcrawlApiKey'],
    views={'items': PRODUCTS_VIEW},
    target='eBay listing data',
    intro='searches **eBay listings**, fetches **item details**, and looks up **sellers and their inventory** '
    'through the PrismCrawl API. Results include **title, price, condition, shipping, seller, images, and URL**.',
    why=[
        '**Resale research**: see what items list and sell for across regional eBay sites.',
        "**Seller monitoring**: track a seller's feedback and current inventory.",
        '**Price comparison**: compare eBay listings with Amazon and Walmart.',
    ],
    input_rows=[
        ('What to fetch', '–', '`search`, `product` (item details), or `seller`.'),
        ('Search query / Category ID', '`query` / `category_id`', 'For search; one is required.'),
        ('Buying format / Price range', '`buying_format` / `_udlo` / `_udhi`', 'For search.'),
        ('Item or seller ID', '`id`', 'For item details and sellers.'),
        ('Seller inventory', '`type`', 'For sellers: `user` or `store`; leave empty for the profile.'),
        ('Maximum pages', '–', 'Pages to fetch (1–100, default 1). Each page uses one credit.'),
        ('Marketplace', '`ebay_domain`', 'For example `ebay.co.uk`.'),
    ],
    input_notes="Fields that don't apply to the selected mode are ignored, and the run log lists them.",
    example_input={'mode': 'search', **request_example(_E), 'buying_format': 'BIN', 'maxPages': 2},
    example_output=catalog_example(
        'ebay',
        'search',
        [
            {
                'position': 1,
                'id': '<item id>',
                'title': 'Example vintage 35mm film camera',
                'price': 89.99,
                'condition': 'Pre-Owned',
                'shipping': 'Free delivery',
                'url': 'https://www.ebay.com/itm/<item id>',
            }
        ],
    ),
    example_is_illustrative=True,
    data_fields=[
        (
            '`data.content.results[]` (search, seller inventory)',
            'Listings: `id`, `title`, `price`, `condition`, `shipping`, `thumbnail`, `url`.',
        ),
        ('`data.content.results[]` (item details)', 'Item: `title`, `price`, `brand`, `images`, `offers`, `shipping`.'),
        ('`data.content.seller`', 'Seller profile: name, feedback score, and positive feedback.'),
    ],
    tips=[
        '**Seller inventory needs a type.** Set `user` or `store`; without it you get the profile only.',
        '**Regional sites differ.** Some sort orders and filters are unavailable on specific eBay domains.',
    ],
    pagination_note='The Actor increments `page` while `has_next_page` is true. Item details are a single page.',
    standby_note='Pass `page` in the body to get a specific page.',
    related=['walmart', 'amazon-search'],
)

ACTORS = [
    GOOGLE_SEARCH,
    GOOGLE_MAPS_PLACES,
    GOOGLE_MAPS_REVIEWS,
    AMAZON_SEARCH,
    BING_SEARCH,
    GOOGLE_SHOPPING_PRODUCT,
    GOOGLE_PLAY,
    APPLE_APP_STORE,
    YELP,
    TRIPADVISOR,
    YOUTUBE,
    WALMART,
    EBAY,
]
