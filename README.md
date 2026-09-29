# IGDB Data Platform

A production-style data engineering project that ingests video-game metadata from IGDB, stores source records in PostgreSQL, transforms them with dbt, orchestrates the pipeline with Airflow, and exposes curated analytics through Streamlit.

> **Project status:** active development. Games ingestion and raw PostgreSQL loading are implemented. Genres, platforms, companies, and involved-companies ingestion are implemented and verified with offline tests and two bounded live smoke runs per entity. Games genre/platform/involved-company references and a single CLI for one or all five entities are implemented. Two bounded all-entity CLI runs passed. dbt models, Docker, Airflow, and Streamlit are being built incrementally.

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
- dbt project scaffolding

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

Use Python **3.11** (the verified development baseline). Run these commands from the repository root on macOS/Linux; do not assume the system `python3` is 3.11:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python --version
python -m pip install -r requirements.txt
python -m pip check
```

Run the unit tests; these need neither `.env`, IGDB credentials, nor PostgreSQL:

```bash
python -m pytest -q
```

For live ingestion, copy `.env.example` to `.env` if it does not already exist. Set `igdb_client_id`, `igdb_client_secret`, and the `POSTGRES_*` values for an existing database. Python loads this file automatically; exported environment variables take precedence. Never commit `.env`.

Inspect CLI options without external services, then run a limited smoke test with valid credentials and PostgreSQL available:

```bash
python -m src.ingestion.run_ingestion --help
python -m src.ingestion.run_ingestion --max-batches 1
python -m src.ingestion.run_ingestion --entity genres --batch-size 5 --max-batches 1
python -m src.ingestion.run_ingestion --entity all --batch-size 5 --max-batches 1
python -m src.ingestion.run_ingestion --entity companies --full-refresh --max-batches 1
python -m src.ingestion.run_ingestion --entity companies --backfill-start 2026-09-01T00:00:00Z --backfill-end 2026-09-02T00:00:00Z --max-batches 1
```

The default games smoke run requests at most 500 games, writes `data/raw/raw_games_<timestamp>.jsonl`, and upserts `<POSTGRES_SCHEMA>.raw_games` (default: `analytics.raw_games`). It records its lifecycle in `<POSTGRES_SCHEMA>.ingestion_runs`, committing a start record before fetching. The database must exist; the configured user needs schema/table creation and write privileges, including for the metadata table. See [raw storage](docs/pipeline/RAW_STORAGE.md) for transaction and failure semantics.

`all` runs games → genres → platforms → companies → involved_companies once each, sequentially. Fetch limits apply separately to each entity; the bounded command above requests at most 25 records total. Each gets its own `raw_<entity>_<timestamp>.jsonl`, raw-load context, and metadata lifecycle. Failure stops the command before later entities start; earlier successful loads remain committed. `--output-path` is supported for one entity and rejected with `all` because one filename is ambiguous.

The bounded smoke commands above never publish a checkpoint, even if the source returns fewer records than the cap. An uncapped CLI run looks up each incremental entity's last successful cutoff, reads the full endpoint if none exists, or applies the overlap window from offset zero. It records the actual lower bound at start and publishes the fixed exclusive cutoff only when the default-field extraction, timestamp/count checks, archive, raw context, and terminal metadata commit succeed. A successful run can load rows with a NULL end and a safe warning. Reference entities always have NULL bounds. This path has offline test coverage but has not been validated with live IGDB/PostgreSQL since activation.

Full refresh reads selected endpoints unfiltered and upserts without deleting existing raw rows. An uncapped eligible refresh may publish a newer cutoff for incremental entities. Backfill accepts an explicit inclusive/exclusive UTC interval, filters each page, records its lower bound, and always leaves its end NULL; the next normal run uses the prior eligible cutoff or bootstraps. Both modes work with `--entity all`. See [CLI details](docs/pipeline/INGESTION.md#explicit-refresh-and-backfill-task-47). These modes have offline validation only.

Phase 3 is complete. See [CLI behavior](docs/pipeline/INGESTION.md#cli-entity-selection-task-36), [validation](docs/engineering/TESTING.md#task-36-verification), and [on-demand PostgreSQL commands](docs/engineering/LOCAL_DEVELOPMENT.md#local-postgresql-on-apple-silicon).

Validate the current dbt scaffold without a database connection:

```bash
dbt parse --project-dir dbt --profiles-dir dbt
```

Warnings about unused staging/intermediate/marts configuration are expected until models exist. To check PostgreSQL connectivity, export the database settings first, then run `dbt debug --project-dir dbt --profiles-dir dbt`. dbt does not automatically load `.env`; see [local development](docs/engineering/LOCAL_DEVELOPMENT.md) for the full procedure. `dbt build` cannot validate analytics yet because there are no sources or models.

## Documentation

Start at [docs/INDEX.md](docs/INDEX.md).

The documentation separates **current implementation** from **target architecture** so planned components are never presented as already complete.

## Project philosophy

This project deliberately favors a compact, explainable data platform over unnecessary infrastructure. The emphasis is on authenticated ingestion, incremental/idempotent loading, relational modeling, data quality, orchestration, reproducibility, and clear engineering tradeoffs.
