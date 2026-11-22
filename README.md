# PrismCrawl Apify Actors

Apify Actors that wrap the [PrismCrawl API](https://www.prismcrawl.com/docs). Each Actor is a thin integration: it
turns Apify input into one PrismCrawl request, follows pagination, and stores PrismCrawl's response unchanged in the
run's dataset. Users bring their own PrismCrawl API key (a secret input).

| Actor | Directory | PrismCrawl endpoints |
| --- | --- | --- |
| PrismCrawl Google Search API | `actors/google-search` | `/v1/google/search` |
| PrismCrawl Google Maps Places API | `actors/google-maps-places` | `/v1/google/maps/search` |
| PrismCrawl Google Maps Reviews API | `actors/google-maps-reviews` | `/v1/google/maps/reviews`, `/v1/google/contributor/reviews` |
| PrismCrawl Amazon Search API | `actors/amazon-search` | `/v1/amazon/search` |
| PrismCrawl Bing Search API | `actors/bing-search` | `/v1/microsoft/search` |
| PrismCrawl Google Shopping Product API | `actors/google-shopping-product` | `/v1/google/shopping/product` |
| PrismCrawl Google Play API | `actors/google-play` | `/v1/google/play/*` (apps, games, books, movies, product, reviews) |
| PrismCrawl Apple App Store API | `actors/apple-app-store` | `/v1/apple/app-store/*` (search, product, reviews) |
| PrismCrawl Yelp API | `actors/yelp` | `/v1/yelp/search`, `/v1/yelp/reviews` |
| PrismCrawl Tripadvisor API | `actors/tripadvisor` | `/v1/tripadvisor/*` (search, place, reviews) |
| PrismCrawl YouTube API | `actors/youtube` | `/v1/youtube/*` (search, video, channel, transcript) |
| PrismCrawl Walmart API | `actors/walmart` | `/v1/walmart/*` (search, product, sellers, reviews) |
| PrismCrawl eBay API | `actors/ebay` | `/v1/ebay/*` (search, product, seller) |

## Layout

```
shared/                  Runtime shared by every Actor (source of truth)
  prismcrawl.py          HTTP transport: errors, retries, API-key redaction
  runtime.py             ActorRequest, pagination, input helpers
  main.py, standby.py    Batch run and Standby HTTP server
  Dockerfile, requirements.txt, .dockerignore, .actorignore
scripts/
  actor_defs.py          Input fields, output views, and README content for every Actor
  build_actors.py        Generates each Actor's .actor/ files and README, and copies shared/ into it
actors/<slug>/
  my_actor/endpoint.py   Hand-written: maps this Actor's input to its PrismCrawl endpoint(s)
  everything else        Generated; don't edit directly
spec/
  openapi.json           Snapshot of https://www.prismcrawl.com/openapi.json
  display_names.json     Country, language, and currency names for input dropdowns
tests/                   Unit tests; PrismCrawl is always mocked
```

Each `actors/<slug>` directory is self-contained, because `apify push` only uploads the Actor's own directory.

## Common tasks

```bash
# Regenerate Actors after editing shared/ or scripts/actor_defs.py
python scripts/build_actors.py

# Tests (needs the Apify SDK: pip install -r shared/requirements.txt)
python -m unittest discover -s tests -t .

# Deploy one Actor
npx apify-cli push --dir actors/google-search
```

**Changing shared behavior** (retries, logging, Standby): edit `shared/`, run the build script, and commit the
regenerated copies. `tests/test_generated.py` fails if any copy is stale.

**Changing an Actor's input form or README**: edit its entry in `scripts/actor_defs.py`, then run the build script.

**Adding an Actor**: add an `ActorDef` to `scripts/actor_defs.py` and `ACTORS`, write
`actors/<slug>/my_actor/endpoint.py` (export `ACTOR_TITLE`, `STANDBY_EXAMPLE`, and `build_request`), run the build
script, and add a full input for each mode to `FULL_INPUTS` in `tests/test_endpoints.py`.

**Updating the PrismCrawl spec**: download a fresh `https://www.prismcrawl.com/openapi.json` into `spec/`, run the
build script, and run the tests. `tests/test_endpoints.py` fails if an Actor sends a parameter, or offers a dropdown
value, that the spec doesn't document.
