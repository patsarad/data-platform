# Target Architecture

## System overview

```text
                       ┌─────────────────┐
                       │ Twitch OAuth    │
                       └────────┬────────┘
                                │ token
                                ▼
┌──────────┐   APIcalypse   ┌───────────────┐
│ IGDB API │ ─────────────► │ Python ingest │
└──────────┘                 └───────┬───────┘
                                    │
                         ┌──────────┴──────────┐
                         │                     │
                         ▼                     ▼
                 JSONL raw archive     PostgreSQL raw schema
                                             │
                                             ▼
                                      dbt source models
                                             │
                         ┌───────────────────┼───────────────────┐
                         ▼                   ▼                   ▼
                      staging           intermediate           marts
                         └───────────────────┬───────────────────┘
                                             │
                                             ▼
                                        Streamlit

Airflow orchestrates ingestion → dbt build/test.
Docker Compose provides reproducible local services.
```

## Layer responsibilities

### Source layer — IGDB

IGDB is the authoritative external source. Requests use APIcalypse over HTTP POST and authenticate using a Twitch application access token.

The pipeline should initially ingest these entities:

- games
- genres
- platforms
- companies
- involved_companies

These entities provide enough structure for meaningful many-to-many analytics without expanding into every IGDB endpoint.

### Ingestion layer — Python

Python owns concerns that happen before data enters the warehouse:

- OAuth token lifecycle
- API requests
- pagination
- retry/backoff behavior
- incremental extraction filters
- raw file archival
- raw table loading/upserts
- run metadata and logging

It should not perform analytics-oriented transformations that belong in dbt.

Currently, `src/ingestion/run_ingestion.py` parses options, chooses per-entity archive paths, and composes the five existing entities through an explicit ordered callback mapping. `--entity` defaults to games; `all` runs games → genres → platforms → companies → involved_companies sequentially, applying fetch limits independently. `src/ingestion/pipeline.py::ingest_entity()` coordinates client creation, fetching, JSONL archival, raw loading, and run lifecycle connections. It accepts an entity contract and fetch/archive/table/upsert callbacks, returning acknowledged fetched/loaded counts. `src/storage/raw_games.py` retains PostgreSQL connection creation, raw-games DDL, and upserts. This boundary preserves the existing games schema and separate DDL/load commits without dynamic discovery or a generic SQL loader.

`src/entities.py` holds the shared, immutable `EntityConfig` and the `GAMES`, `GENRES`, `PLATFORMS`, `COMPANIES`, and `INVOLVED_COMPANIES` configurations. It describes the endpoint, ordered requested fields, unqualified raw table, source primary key, raw primary-key column, and optional source update field. Fetch and storage consume this data-only contract; entity-specific query construction and row preparation remain in their own modules. `updated_at` remains inside the raw JSONB payload and is checked for checkpoint eligibility on normal incremental runs. All five entities are selectable in the CLI.

Task 3.1 adds `fetch_genres.py` and `raw_genres.py` callbacks for direct composition with the same runner. Genres use the shared paginator and the existing metadata/connection lifecycle, with a separate small entity-specific archive writer and SQL loader. No generic SQL framework or new connection factory is needed. The genres helpers pass offline tests and two bounded live runs verified archives, PostgreSQL upserts, and successful run metadata.

Task 3.2 adds `fetch_platforms.py` and `raw_platforms.py` following the genres pattern. Platforms request only ID/name/slug/update time and use the same paginator, five-column raw shape, and runner lifecycle. Offline tests and two bounded live runs verified the path.

Task 3.3 adds `fetch_companies.py` and `raw_companies.py` following the same lookup pattern. Companies request ID/name/slug/update time and compose with the existing paginator and runner. Offline tests and two bounded live runs verified archival, raw upserts, timestamp refresh, and metadata; relationship ingestion is described below.

Task 3.4 adds `fetch_involved_companies.py` and `raw_involved_companies.py` with the same paginator and runner. The relationship contract requests its own ID, game/company IDs, developer/publisher roles, and the documented source update time. The raw table uses only `igdb_id`, complete JSONB `payload`, and `fetched_at`; references/roles remain in JSONB for dbt, without foreign keys to bounded raw samples or invented name/slug columns. Offline tests and two bounded live runs verified this path. No existing entity schema changed.

Task 3.5 appends genre, platform, and involved-company record ID arrays to the games contract. The existing fetch/archive/load path preserves them inside complete raw payloads; the games schema and runner are unchanged. Involved-company record IDs lead to company references and role flags, not directly to companies. Array extraction and relationship joins remain future dbt work.

Task 3.6 composes each selected entity with its own durable start, raw-load context, and terminal metadata. The loop is fail-fast: a failure propagates and later entities are never started; earlier completed entities remain committed. There is no group transaction or parent run. A single-entity output override is allowed, but `all` with `--output-path` is rejected during argument parsing before source/database work. The fixed order does not imply reference-existence requirements.

`src/storage/ingestion_runs.py` now owns operational run metadata. The reusable runner commits the start before fetching and success after the existing raw-load context exits, using separate connections for metadata. Failure records are best-effort and cannot mask the original error. Raw data and terminal metadata are deliberately separate transactions to preserve existing raw-load semantics; see [Raw storage](pipeline/RAW_STORAGE.md) for failure cases.

### Raw layer — PostgreSQL

Raw tables are a durable representation of source records. Each entity should retain:

- stable IGDB identifier;
- a small number of operationally useful columns when appropriate;
- the full source payload as JSONB;
- ingestion timestamp (`fetched_at`);
- source update timestamp where available/needed for incremental logic.

Recommended raw tables:

```text
raw_games
raw_genres
raw_platforms
raw_companies
raw_involved_companies
```

Upserts should use the IGDB identifier as the conflict key. Rerunning the same source window must not create duplicates.

### Transformation layer — dbt

The dbt project owns warehouse transformations.

#### Sources

Declare the PostgreSQL raw tables as dbt sources, including freshness expectations where they are useful and reliable.

#### Staging

Staging models should:

- rename source fields consistently;
- cast timestamps and numeric values;
- extract needed JSONB fields;
- normalize booleans/nulls;
- remain close to one source entity per model.

Target models:

```text
stg_games
stg_genres
stg_platforms
stg_companies
stg_involved_companies
```

#### Intermediate

Intermediate models should resolve relationships and reusable business logic. Likely examples include:

```text
int_game_genres
int_game_platforms
int_game_companies
```

Exact models should follow the final source payload design rather than being created speculatively.

#### Marts

Marts should answer concrete analytics questions and expose a stable contract to Streamlit. Keep the number small and purposeful. Candidate marts include:

```text
mart_game_catalog
mart_release_trends
mart_genre_performance
mart_platform_performance
mart_company_output
```

The final mart set should be chosen after staging/intermediate models exist and real source coverage is understood.

### Orchestration layer — Airflow

Airflow should coordinate, not contain business logic. DAG tasks should call reusable Python/dbt commands rather than duplicate their internals.

Target dependency graph:

```text
start
  ↓
ingest reference entities
  ↓
ingest games / relationships
  ↓
dbt build
  ↓
end
```

If source dependencies do not require strict ordering, independent ingestion tasks can run in parallel.

### Consumption layer — Streamlit

Streamlit should query marts only. It should not call IGDB directly or reimplement transformations.

The app exists to prove the curated layer is useful, not to become a large frontend project. A few well-designed views are enough:

- release trends;
- genre/platform comparison;
- company/developer output;
- game explorer with filters.

## Incremental ingestion strategy

Task 4.1 accepts the [high-water-mark design](pipeline/WATERMARKS.md). Task 4.2 adds `ingestion_runs.get_source_watermark()`, a read-only metadata lookup using the caller's connection and the greatest successful non-NULL end for the exact schema/entity. It propagates lookup failures and manages no transactions or connection lifecycle. Task 4.3 adds a pure window calculator and immutable bounds in `src/ingestion/windows.py`, plus optional `window=` support in the three relevant query/fetch paths. Task 4.5 wires them through explicit CLI selection and the shared runner. Games, companies, and involved companies bootstrap with full reads, then select `updated_at` in `[previous successful cutoff - 24 hours, fixed run-start cutoff)`, clamping the lower bound to the Unix epoch. Genres/platforms keep full endpoint reads by deliberate lookup-entity policy, although both document update timestamps.

The committed watermark is the exclusive extraction cutoff, **not the maximum returned timestamp**. It is written only with eligible terminal success after raw context exit, including for empty results. All capped runs are ineligible. Per-entity successful progress is independent; failed/running metadata rows cannot supply it. Raw and metadata commits remain separate, including the documented ambiguous-acknowledgment case.

Primary-key upserts make overlap duplicate-safe. Fixed bounds and deterministic ID ordering do not supply source snapshot isolation: changing offset pages can still omit records. Task 4.7 adds explicit unfiltered full refresh for one or all entities and historical `[A, B)` backfills across all five endpoints. Full refresh can publish a newer eligible cutoff for incremental entities; backfill always leaves the end NULL, so normal progress still comes from the greatest earlier eligible end. Neither mode deletes raw rows. Direct fetcher callers remain unfiltered unless they supply a window. See the [mode policy](pipeline/WATERMARKS.md#full-refresh-and-backfill-task-47).

## Run metadata

Implemented in task 2.4: a lightweight ingestion-run table in the configured PostgreSQL schema makes entity runs inspectable:

```text
ingestion_runs
- run_id
- entity
- started_at
- completed_at
- status
- records_fetched
- records_loaded
- source_watermark_start
- source_watermark_end
- error_message
```

Each entity invocation gets a UUID and transitions from `running` to `succeeded` or `failed`, with UTC timestamps and known fetch/load counts. Terminal updates target only a running record. Failure summaries use fixed stage descriptions to avoid copying sensitive exception text. Normal incremental runs record an actual lower bound when windowed and publish an eligible cutoff with terminal success. Ineligible and reference runs keep NULL ends. Outages and abrupt interruptions can leave records running; no automatic recovery is implemented.

## Schemas

The configured schema boundary is:

- `raw` by default — Python-owned `raw_<entity>` tables and `ingestion_runs`, selected by `POSTGRES_RAW_SCHEMA`;
- `analytics` by default — dbt-managed model outputs, selected independently by `DBT_SCHEMA` in the dbt profile.

Five dbt `igdb` sources and Python resolve their raw schema identically: `POSTGRES_RAW_SCHEMA`, then legacy `POSTGRES_SCHEMA`, then `raw`. This allows an existing `analytics` raw installation to retain its data and watermark lookup until an explicit move. `stg_games`, `stg_genres`, `stg_platforms`, `stg_companies`, and `stg_involved_companies` are views in independent `DBT_SCHEMA`; their builds, source tests, and row values have been verified against PostgreSQL. All five preserve one row per raw entity ID; involved companies uses the relationship record ID and exposes nullable game/company references and independent developer/publisher flags. Configuration and source declarations do not migrate tables or run history; see [local development](engineering/LOCAL_DEVELOPMENT.md#schema-names-and-existing-analytics-installations).

## Reliability principles

- Retry only failures that are plausibly transient.
- Fail loudly after retry exhaustion.
- Do not advance incremental state on failed loads.
- Make raw loads idempotent.
- Keep secrets out of Git and logs.
- Make pipeline steps independently runnable for debugging.
- Add database/dbt integration checks in addition to pure unit tests.
- Let Airflow orchestrate commands that also work outside Airflow.

## Deliberate non-goals

The project does not need Kubernetes, Kafka, Spark, a cloud warehouse, microservices, or a custom web frontend to demonstrate the intended skills. Those additions would increase operational surface area without improving the core story proportionally.
