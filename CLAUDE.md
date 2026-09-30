@AGENTS.md

## This repository

This repo holds several Actors under `actors/<slug>/`, generated from `shared/` and `scripts/actor_defs.py`. See
`README.md`. Only `actors/<slug>/my_actor/endpoint.py` is hand-written per Actor; after changing `shared/` or
`scripts/actor_defs.py`, run `python scripts/build_actors.py`. The PrismCrawl OpenAPI snapshot in `spec/openapi.json`
is the source of truth for parameter names and values.
