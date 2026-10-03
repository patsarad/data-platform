# IGDB Data Platform

A production-style data engineering project that ingests video-game metadata from IGDB, stores source records in PostgreSQL, transforms them with dbt, orchestrates the pipeline with Airflow, and exposes curated analytics through Streamlit.

> **Project status:** active development. Five-entity ingestion, incremental raw loading, and thirteen dbt models with 46 database tests are implemented. Phase 7 is complete: the documented Compose workflow passed two bounded live ingestions and a full dbt build from new volumes, with persistence across container replacement. Airflow and Streamlit remain future work.

## Architecture

```text
IGDB API
   │
   ▼
Python ingestion ──► raw JSONL archive
   │
   ▼
PostgreSQL raw tables
   │
   ▼
dbt: staging → intermediate → marts
   │
   ▼
Streamlit analytics

Airflow orchestrates ingestion → dbt.
Docker Compose provides the local runtime.
```

## Implemented today

- Twitch OAuth client-credentials authentication with token caching
- reusable IGDB API client with retries/backoff and 401 token refresh
- paginated games extraction with genre, platform, and involved-company record IDs
- timestamped raw JSONL archive
- PostgreSQL `raw_games` creation and idempotent upsert
- PostgreSQL ingestion run records with start/success/failure status and counts
- genres contract, paginated fetch, JSONL archive, and `raw_genres` upsert callbacks for the shared runner (offline and live smoke verified)
- platforms contract, paginated fetch, JSONL archive, and `raw_platforms` upsert callbacks for the shared runner (offline and live smoke verified)
- companies contract, paginated fetch, JSONL archive, and `raw_companies` upsert callbacks for the shared runner (offline and live smoke verified)
- involved-companies contract, paginated fetch, JSONL archive, and minimal `raw_involved_companies` upsert callbacks (offline and live smoke verified)
- one CLI with `--entity games|genres|platforms|companies|involved_companies|all` (default: games)
- normal CLI incremental selection for games, companies, and involved companies: unfiltered bootstrap, then frozen 24-hour overlap windows; eligible uncapped default-field successes commit the cutoff after raw loading ([watermark policy](docs/pipeline/WATERMARKS.md)); genres/platforms remain unfiltered on normal runs
- explicit `--full-refresh` and `--backfill-start A --backfill-end B` modes for one or all entities; backfills use whole-second UTC bounds and never advance normal progress
- unit tests for the implemented Python components
- dbt staging, relationship views and five curated mart tables
- Docker Compose PostgreSQL with persistent storage and an on-demand non-root Python/dbt runtime
- dbt `igdb` source declarations for the five raw tables, with ten source-key tests verified against PostgreSQL
- `stg_games`, `stg_genres`, `stg_platforms`, `stg_companies`, and `stg_involved_companies` as dbt staging views, built and queried against PostgreSQL
- opt-in PostgreSQL/dbt integration checks for transactions, checkpoints, schema compatibility, and staging values

See [docs/CURRENT_STATE.md](docs/CURRENT_STATE.md) for the exact implementation state and [docs/ROADMAP.md](docs/ROADMAP.md) for the build plan.

## Planned stack

- Python 3.11+
- PostgreSQL
- dbt Core
- Docker Compose
- Apache Airflow
- Streamlit
- pytest

## Quick start — current development state

Start with [Compose first use and subsequent sessions](docs/engineering/LOCAL_DEVELOPMENT.md#compose-first-use-and-subsequent-sessions-task-74).
It covers prerequisites, isolated environment selection, image build, PostgreSQL
readiness, explicit ingestion → dbt commands, persistent volumes, artifact export,
shutdown and restart. Ordinary startup runs only PostgreSQL. The live ingestion
sequence contacts IGDB and modifies data. Task 7.5 verified bounded clean-volume
startup, repeat upserts, all 13 models/46 tests and persistence; see the
[validation record](docs/engineering/TESTING.md#task-75-clean-volume-live-workflow-verification).
This sample does not establish full source coverage or an uncapped bootstrap.

For host development, follow [Python 3.11 setup](docs/engineering/LOCAL_DEVELOPMENT.md#python-setup)
and [native PostgreSQL operation](docs/engineering/LOCAL_DEVELOPMENT.md#local-postgresql-on-apple-silicon).
Preserve any existing `.env`; [schema compatibility](docs/engineering/LOCAL_DEVELOPMENT.md#schema-names-and-existing-analytics-installations)
explains how to retain existing raw tables and watermark history. Host and Docker
storage are separate. With the host environment activated, these checks need no
external services:

```bash
python -m src.ingestion.run_ingestion --help
python -m pytest -q -p no:cacheprovider
```

See [ingestion CLI behavior](docs/pipeline/INGESTION.md#cli-entity-selection-task-36),
[dbt build requirements](docs/pipeline/DBT_TRANSFORMATIONS.md#build-contract) and
[testing](docs/engineering/TESTING.md#postgresql-integration-tests) for details.

## Documentation

Start at [docs/INDEX.md](docs/INDEX.md).

The documentation separates **current implementation** from **target architecture** so planned components are never presented as already complete.

## Project philosophy

This project deliberately favors a compact, explainable data platform over unnecessary infrastructure. The emphasis is on authenticated ingestion, incremental/idempotent loading, relational modeling, data quality, orchestration, reproducibility, and clear engineering tradeoffs.
