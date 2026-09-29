# Current State

Last verified against the working repository on September 28, 2026 (task 4.7 offline full-refresh/backfill validation; Phases 2 and 3 remain complete).

This document describes what exists in code today. Planned components belong in `ARCHITECTURE.md` and `ROADMAP.md`.

## Status summary

| Area | Status | Current implementation |
|---|---|---|
| Repository scaffolding | Complete | `src/`, `tests/`, `dbt/`, `dags/`, `docker/`, `app/`, `data/` exist |
| Local setup / repository baseline | Phase 1 verified | Fresh Python 3.11 install, offline unit tests, CLI help, and dbt scaffold parsing pass; previously tracked artifacts remain reported below |
| Configuration | Implemented | Environment-backed `Settings`, `.env.example`, cached settings loader |
| Logging | Implemented | Shared logger with configurable log level |
| Twitch OAuth | Implemented | Client-credentials token request, in-memory token cache, expiration buffer |
| IGDB client | Implemented | APIcalypse POST requests, headers, retries/backoff, 401 token refresh |
| Games extraction | Implemented | Shared pagination requests the existing nine fields plus genre/platform/involved-company record IDs; offline and repeated live validation passed |
| Local raw archive | Implemented | Separate timestamped JSONL archives for each CLI-selected entity; default games path retained |
| PostgreSQL games load | Implemented | Connections, schema/table creation, and `ON CONFLICT` upsert into `raw_games` live in `src/storage/raw_games.py` |
| Ingestion run metadata | Implemented | Shared runner records running/succeeded/failed runs for the supplied entity with UTC timestamps, counts, and safe failure summaries |
| Python tests | Implemented for current modules | 410 passing offline tests cover explicit refresh/backfill, consecutive incremental runs, runtime checkpoint gates, overlap preparation, optional windows, persisted lookup, and existing entity/runner behavior |
| Additional IGDB entities | Genres, platforms, companies, and involved companies implemented and smoke verified | All use the shared runner with `raw_genres` / `raw_platforms` / `raw_companies` / `raw_involved_companies` |
| Incremental extraction | Normal, full-refresh, and backfill CLI paths verified offline | Games/companies/involved companies look up per-entity progress for normal/refresh runs. Normal runs bootstrap or use frozen overlap windows; explicit refresh reads unfiltered and may publish a newer eligible cutoff. Explicit backfills filter all selected entities over a caller interval and never publish progress. Genres/platforms stay unfiltered with NULL bounds on normal/refresh runs. |
| Generalized ingestion framework | Phase 2 complete (tasks 2.1–2.6) | CLI selects one or all five entities through an explicit ordered callback mapping and reusable lifecycle runner; offline tests cover the composed path with real helpers and fake external boundaries |
| dbt project | Scaffolded | Project/profile and layer directories exist; no models yet |
| dbt sources/tests/docs | Not implemented | No source YAML or models yet |
| Docker | Not implemented | `docker/` is a placeholder |
| Airflow | Not implemented | `dags/` is a placeholder |
| Streamlit | Not implemented | `app/` is a placeholder |
| AI layer | Not implemented / deferred | `src/ai/` is a placeholder |
| CI | Not implemented | No automated repository checks observed |

## Existing ingestion flow

Local PostgreSQL is managed on demand: `brew services run postgresql@17` via native `/opt/homebrew/bin/brew` starts it without login registration, and `services stop` ends the work session. A restart check preserved five genres and two run records. The server was left stopped and unregistered on September 26, 2026; its on-disk databases remain intact. See [Local development](engineering/LOCAL_DEVELOPMENT.md#local-postgresql-on-apple-silicon).

The current command-line flow is:

```text
run_ingestion.py (entity selection, arguments, per-entity paths/callbacks)
    ↓
for each selected entity (games → genres → platforms → companies → involved_companies for all)
    ↓
pipeline.ingest_entity()
    ↓
metadata DDL commit, then per-entity lookup and fixed cutoff for incremental entities
    ↓
commit ingestion_runs start (separate connection, closed before fetching)
    ↓
create IGDB client
    ↓
TwitchTokenManager → Twitch OAuth token
    ↓
IGDBClient.query(entity.endpoint, APIcalypse query)
    ↓
entity fetcher
    ├── timestamped raw_<entity> JSONL archive
    └── PostgreSQL <POSTGRES_SCHEMA>.raw_<entity> upsert
    ↓
commit guarded ingestion_runs success and eligible cutoff together (after raw context exits)
```

Exceptions after the start trigger a best-effort failed-run update on a fresh connection, then propagate. Failure reporting never replaces the original error.

`raw_games` currently contains:

- `igdb_id` — primary key
- `name`
- `slug`
- `payload` — complete fetched object as JSONB
- `fetched_at` — pipeline fetch timestamp

`fetch_games_batches()` now delegates pagination to `src/ingestion/pagination.py::fetch_paginated()`, passing the games endpoint and a callback to the existing games query builder. Task 3.5 appends three relationship fields; ordering, pagination defaults, list output, stopping rules, custom-field overrides, and CLI/storage behavior are preserved.

The CLI retains arguments/defaults, output-path selection, and start/finish logging. It binds fetch options with `functools.partial` and passes an explicit `RunSelection` plus the selected entity’s fetch, archive, table-creation, and upsert callbacks to `src/ingestion/pipeline.py::ingest_entity()`. This reusable runner owns client creation, fetch/archive/load ordering, the UTC load timestamp, connection contexts, checkpoint gates, and lifecycle handling; it returns acknowledged fetched/loaded counts. Direct callers without selection context retain fetching/loading but cannot publish progress. `src/storage/raw_games.py` still owns connection creation, raw-games DDL, and upserts. Storage helpers explicitly commit successful DDL and non-empty upserts separately; database settings, schema, SQL, and row preparation are unchanged.

`src/storage/ingestion_runs.py` owns metadata DDL, committed start/success/failure helpers, and `get_source_watermark()`. For incremental CLI entities, the runner reads committed history after metadata DDL, captures one cutoff, and records the actual inclusive lower bound on the running row (NULL for bootstrap). Lookup failure aborts before source work. It uses separate, short-lived metadata connections and retains the raw-load context. An eligible end is committed with guarded success only after raw context exit; ineligible successes and failed/running rows retain NULL ends. A terminal acknowledgment error can leave durable success despite command failure. Full transaction boundaries, count meanings, and outage/interruption limitations are in [Raw storage](pipeline/RAW_STORAGE.md).

`src/entities.py` defines a frozen `EntityConfig` with `GAMES`, `GENRES`, `PLATFORMS`, `COMPANIES`, and `INVOLVED_COMPANIES`. The games fetcher uses its endpoint, ordered fields, and source primary key (`id`); storage uses its raw table (`raw_games`) and the source-to-raw key mapping (`id` → `igdb_id`). `DEFAULT_GAME_FIELDS` remains a compatibility alias. Genres request `id`, `name`, `slug`, and `updated_at` and use the same key mapping into `raw_genres`, with the same five-column raw shape. Platforms and companies request the same four minimal fields and map into separate five-column `raw_platforms` and `raw_companies` tables. The configured update field (`updated_at`) remains in the payload; task 4.3 adds optional filters only to games/companies/involved companies, with no new column in existing tables. Task 3.6 adds explicit CLI selection/composition.

`INVOLVED_COMPANIES` requests `id`, `game`, `company`, `developer`, `publisher`, and officially supported `updated_at`. `raw_involved_companies` has only `igdb_id`, complete JSONB `payload`, and `fetched_at`. References and roles remain in the payload; the relationship record ID is the upsert key. No name/slug fields, foreign keys, or reference-existence requirements are added.

## Existing games fields requested from IGDB

The current extractor requests:

- `id`
- `name`
- `slug`
- `first_release_date`
- `rating`
- `rating_count`
- `total_rating`
- `total_rating_count`
- `updated_at`
- `genres` — genre ID array
- `platforms` — platform ID array
- `involved_companies` — involved-company record ID array, not company IDs

Only ID/name/slug are broken out into raw table columns today; the remaining fields are retained inside `payload`.

## Existing strengths

The current foundation already demonstrates several useful engineering practices:

- credentials are environment-backed rather than hard-coded;
- OAuth tokens are cached and refreshed;
- transient HTTP failures are retried;
- raw source JSON is preserved;
- database writes use upserts, making repeated loads safer;
- components are separated into auth, client, fetch, storage, config, logging, and orchestration-entry modules;
- current behavior has unit tests using fakes rather than live external services.

## Gaps to address next

The highest-value gaps are not UI or AI. They are the pieces that turn the working games proof-of-concept into an actual data platform:

1. create dbt sources, staging models, relationships, marts, and tests;
2. containerize PostgreSQL and pipeline dependencies;
3. orchestrate the pipeline with Airflow;
4. add a thin analytics application;
5. add CI and final operational polish.

## Phase 1 verification

- Installed unchanged `requirements.txt` into a new temporary virtual environment using Python 3.11.0 on macOS; `python -m pip check` reported no broken requirements.
- `python -m pytest -q`: all 15 existing tests passed. Repeated successfully in a clean source copy without `.env`, caches, or inherited environment variables. No application or test changes were necessary.
- `python -m src.ingestion.run_ingestion --help`: passed without external services.
- `dbt parse --project-dir dbt --profiles-dir dbt`: passed using dbt Core 1.12.5 / dbt-postgres 1.11.0. The three unused model-directory configuration warnings are expected while the project is scaffold-only.
- README and local setup docs now select Python 3.11 explicitly, describe configuration and a limited live ingestion run, and distinguish offline dbt parsing from database connectivity checks.
- Ignore-rule checks passed for 19 generated/private/local paths and seven paths that must remain visible, including `.env.example`.

Live IGDB ingestion and PostgreSQL connectivity were not exercised in this phase. The unit tests verify SQL preparation with fakes, not database-level upsert semantics. Python versions newer than 3.11 and Windows setup have not been validated. Dependency ranges remain bounded rather than locked, so resolved versions can change over time.

## Task 2.1 verification

- Reused the Phase 1 Python 3.11.0 environment; `python -m pip check` reported no broken requirements. No dependencies were changed.
- Before changes, the focused games tests passed (3 tests).
- After extraction, the focused pagination/games tests passed (16 tests), followed by the full Python suite (28 tests).
- CLI help passed; `git diff --check` passed. Exact Python verification commands are recorded in [Testing](engineering/TESTING.md).
- Tests cover empty/partial pages, full-page offset progression, ordered accumulation, batch caps (including existing non-positive cap behavior), propagated client failures, and unchanged games default/custom queries.
- Bytecode and pytest cache writes were disabled. Existing user edits and tracked generated artifacts were preserved.

Validation used fakes, without live IGDB or PostgreSQL access. Fetching still accumulates records in memory and retains existing argument handling. At that point, only task 2.1 was complete in Phase 2.

## Task 2.2 verification

- Extracted the three database helpers into `src/storage/raw_games.py`, preserving their signatures and implementation. The CLI change is limited to imports and removal of the moved definitions.
- Before extraction, both existing ingestion-helper tests passed. After extraction, all 30 focused storage/CLI/games/pagination tests and all 40 Python tests passed on Python 3.11.0. CLI help and `git diff --check` passed.
- Storage tests cover connection settings, unchanged DDL/upsert SQL, JSONB payloads, iterable input, missing optional fields, empty loads, missing IDs, and propagated database failures. CLI tests exercise the real storage helpers with a fake connection, checking archive order, output paths, timestamps, commits, and failure exit.
- Exact commands and the corrected test-mock assertion from the initial focused run are recorded in [Testing](engineering/TESTING.md).
- No dependencies changed. Existing user edits and tracked generated artifacts were preserved; bytecode and pytest cache writes were disabled.

Validation used fakes, without live IGDB or PostgreSQL access; actual PostgreSQL rollback/upsert behavior was not integration-tested. DDL remains committed separately before loading, and empty upserts still return zero without opening a cursor or committing. At that point, only tasks 2.1 and 2.2 were complete in Phase 2.

## Task 2.3 verification

- Added the shared immutable games contract, with explicit source/raw primary-key names and ordered tuple fields. Fetch/storage helpers consume it without changing their public signatures, generated queries/SQL, or transaction boundaries.
- Before changes, all 30 focused regression tests passed. After integration, all 33 focused tests and all 43 Python tests passed on Python 3.11.0; CLI help and `git diff --check` also passed. Exact commands are recorded in [Testing](engineering/TESTING.md).
- Added contract/immutability and custom-field isolation coverage; storage coverage now explicitly retains `updated_at` only in JSONB while asserting the unchanged SQL. Existing tests still cover missing IDs, missing optional fields, empty loads, pagination, and database failures.
- No dependencies changed. Existing user edits and tracked generated artifacts were preserved; bytecode and pytest cache writes were disabled.

Validation used fakes, without live IGDB or PostgreSQL access. At that point, only games was configured; run metadata, broader CLI generalization, incremental ingestion, and additional entities remained unimplemented.

## Task 2.4 verification

- Added `ingestion_runs` DDL and helpers for committed running/succeeded/failed records, using UUIDs, UTC timestamps, counts, and guarded terminal updates. Nullable watermark columns are reserved and never populated.
- Integrated only the existing games command. Start, raw load, and completion use separate connections; raw-games DDL/load commits and fetch/archive ordering are preserved. Stage failures are recorded with safe summaries; failure-reporting errors are logged without masking the original exception.
- The 33 baseline focused tests passed. After implementation, 66 focused tests passed; adding a raw-load commit-failure regression brought the final focused set to 67 passes. All 77 Python tests then passed on Python 3.11.0. CLI help and `git diff --check` passed. Exact commands are in [Testing](engineering/TESTING.md).
- Coverage includes empty success, source/archive/DDL/upsert/commit failures, metadata setup and completion failures, connection outages, unchanged raw transaction ordering, protected terminal transitions, and secondary-error handling.
- No dependencies changed. Existing user edits and tracked artifacts were preserved, with bytecode and pytest cache writes disabled.

Validation used fakes, without live IGDB/PostgreSQL checks. Metadata is not atomic with the raw load: an outage or interruption can leave a running record, and a failure after the raw commit cannot undo the data. No broader CLI refactor, incremental ingestion, additional entities, or task 2.6 work was begun. Only task 2.4 was newly marked complete.

## Task 2.5 verification

- Extracted `pipeline.ingest_entity()` as a callback-based runner; the CLI composes the existing games helpers. No registry, new entities, generic SQL loader, incremental behavior, or new dependencies were added.
- Preserved games queries, fetch/archive behavior, CLI arguments/defaults, raw schema, separate commits, durable start, success after raw context exit, and best-effort failure reporting. Existing lifecycle regression assertions remain in place with mocks patched at their new owning module.
- All 67 baseline focused tests passed. After refactoring, all 71 focused tests and all 81 unit tests passed on Python 3.11.0. CLI help and `git diff --check` passed. Exact commands are in [Testing](engineering/TESTING.md).
- New tests cover default/custom CLI composition, the existing zero batch cap, and direct runner use without argument parsing, including returned load counts. User edits and tracked artifacts were preserved; bytecode/cache writes were disabled.

Validation used fakes, without live IGDB/PostgreSQL checks. Existing transaction gaps and interruption limitations still apply. Watermark columns remain NULL. Only task 2.5 was newly completed; task 2.6 remains next.

## Task 2.6 verification

- Audited existing pagination, games, storage, metadata, CLI, and runner tests. Retained their isolated stopping-rule, SQL, and lifecycle coverage without duplicating the full test matrix.
- Added five composed-path cases in `tests/test_pipeline.py`, using real pagination, games fetch/archive, raw storage, and metadata helpers with fake API/database boundaries. They cover empty results, full-page termination, repeated-ID row preparation/counts, later-page failure, missing-ID preparation failure, and raw context-exit failure after an acknowledged load.
- All 71 baseline focused tests passed. After additions, all six runner tests, 76 focused tests, and all 86 unit tests passed on Python 3.11.0. Exact commands and the coverage audit are in [Testing](engineering/TESTING.md).
- No production code, dependencies, CLI arguments/defaults, schemas, transaction boundaries, or lifecycle semantics changed. User edits and tracked artifacts were preserved; bytecode/cache writes were disabled.

Validation used fakes without live IGDB/PostgreSQL access; database constraints, actual rollback/upsert effects, and ambiguous commit outcomes remain outside unit-test validation. Watermarks remain NULL. Only task 2.6 was newly completed; task 3.1 (genres) is next.

## Task 3.1 implementation and verification

- Verified the genres endpoint and minimal fields against official IGDB documentation; source links and a bounded direct runner invocation are in [Ingestion](pipeline/INGESTION.md#genres-task-31).
- Added the immutable `GENRES` contract, shared-pagination fetcher, JSONL archive writer, and `raw_genres` DDL/upsert callbacks. Full fetched payloads are retained; only ID/name/slug are extracted. The new SQL quotes identifiers and parameterizes values.
- All 76 baseline focused tests passed, followed by 30 narrow affected tests, 98 expanded focused tests, and all 108 unit tests on Python 3.11.0. CLI help passed. Exact commands and coverage are in [Testing](engineering/TESTING.md#task-31-offline-verification-and-smoke-limitation).
- Existing games production modules, CLI arguments/defaults, schemas, runner lifecycle, and transaction boundaries are unchanged. Watermarks remain NULL. No dependencies changed; user edits and tracked artifacts were preserved.

The initial smoke attempt was blocked by an unavailable PostgreSQL server. On September 26, native Apple Silicon Homebrew PostgreSQL 17.11 was started; the missing configured login and `gaming_analytics` database were created. The project login owns its database and has no superuser, database-creation, or role-creation privileges. Existing `.env` settings were retained.

Two live `ingest_entity()` runs each fetched and loaded five genres (IDs 2, 4, 5, 7, 8). Archives matched the complete stored payloads, the second run refreshed `fetched_at` while the raw table remained at five distinct rows, and both metadata rows were `succeeded` with 5/5 counts and NULL watermarks. The 30 narrow tests and all 108 unit tests were repeated successfully before the live runs. Task 3.1 is complete; no later roadmap task was implemented. This bounded smoke does not validate full endpoint coverage, failure rollback, or ambiguous commits. Exact commands/results are in [Testing](engineering/TESTING.md#task-31-live-smoke-completion).

## Task 3.2 implementation and verification

- Verified the platforms endpoint and minimal `id`, `name`, `slug`, `updated_at` fields against official IGDB documentation. Added `PLATFORMS`, a shared-pagination fetcher, JSONL writer, and quoted/parameterized `raw_platforms` DDL/upsert helpers following genres.
- The 30 baseline focused tests passed; after implementation, 36 focused tests and all 130 offline tests passed on Python 3.11.0. CLI help and whitespace checks passed. No dependencies changed.
- Two bounded live five-record runs passed for IDs `[3, 4, 5, 6, 7]`: source/archive/JSONB fidelity, duplicate-free upserts, refreshed timestamps, durable running records, succeeded metadata with 5/5 counts, and NULL watermarks. The table remained at five rows. An earlier startup probe and an overly strict timestamp-display assertion in the manual harness failed; details are retained in [Testing](engineering/TESTING.md#task-32-verification).
- PostgreSQL was stopped on every validation exit. Final service verification reported `Running: false`, `Loaded: false`, `Schedulable: false`; readiness reported no response. Existing databases/settings were retained.
- Games/genres production behavior, CLI arguments/defaults, existing schemas, runner lifecycle, and transaction boundaries are unchanged. User edits and tracked artifacts were preserved. Only task 3.2 is newly complete.

The bounded sample does not establish full endpoint coverage, failure rollback, or ambiguous commit recovery. Watermarks remain NULL and extraction still starts at offset zero.

## Task 3.3 implementation and verification

- Verified the companies endpoint and minimal `id`, `name`, `slug`, `updated_at` fields against official IGDB documentation. Added `COMPANIES`, shared-pagination fetch/archive helpers, and quoted/parameterized `raw_companies` DDL/upserts following genres/platforms.
- On Python 3.11.0, all 36 baseline focused tests passed, then 42 affected tests and all 152 offline tests passed. CLI help and whitespace checks passed; dependencies are unchanged.
- Two bounded live five-record runs passed for IDs `[1, 2, 3, 4, 5]`: source/archive/JSONB equality, extracted fields, duplicate-free upserts, refreshed timezone-aware timestamp instants, independently visible durable starts, succeeded 5/5 metadata, and NULL watermarks. The initially absent table ended with five distinct rows; the harness accounts for existing rows without clearing tables.
- PostgreSQL was started with `services run` after offline validation, awaited readiness, and stopped on exit. Final checks showed `Running: false`, `Loaded: false`, `Schedulable: false`, and no response on port 5432. Databases/settings were retained; login startup was not enabled.
- Existing games/genres/platforms modules, CLI arguments/defaults, schemas, shared runner, transaction boundaries, and best-effort failure reporting are unchanged. User edits and tracked artifacts were retained. Only task 3.3 is newly complete.

See [Testing](engineering/TESTING.md#task-33-verification) for exact commands, the repeatable harness, and run IDs. The bounded sample does not validate full endpoint coverage, failure rollback, or ambiguous commit recovery. Watermarks remain NULL.

## Task 3.4 implementation and verification

- Added the official involved-companies contract, shared-pagination fetch/archive helpers, and minimal raw DDL/upserts. The source record ID is the conflict key; references, roles, and supported update time remain unchanged in JSONB for later dbt extraction.
- Python 3.11.0 validation passed: 42 baseline focused tests, 48 affected tests, and all 174 offline tests. Games CLI help and whitespace checks passed; no dependencies changed.
- Two five-record live runs passed for `[2, 6, 7, 8, 9]`: source/archive/JSONB equality, integer game/company references, boolean roles, refreshed timestamp instants, duplicate-free upserts, durable starts, succeeded 5/5 metadata, and NULL watermarks. The table was initially absent and contained five distinct rows after each run. The harness accounts for existing rows without clearing tables and makes no reference-existence assertions.
- PostgreSQL was started on demand, readiness awaited, and stopped through an EXIT trap. Final service flags were all false and `pg_isready` returned no response. Existing databases/settings and login startup behavior were retained.
- Existing entity modules, CLI/defaults, schemas, runner transactions, durable start, success after raw context exit, and best-effort failure reporting are unchanged. User edits and tracked artifacts were preserved. Only task 3.4 is newly complete.

Validation occurred September 26 locally (September 27 UTC). See [Testing](engineering/TESTING.md#task-34-verification) for exact commands, harness, and run IDs. Full endpoint coverage, live failure rollback, and ambiguous commit recovery remain unverified. Watermarks remain NULL.

## Task 3.5 implementation and verification

- Appended only `genres`, `platforms`, and `involved_companies` to the existing nine games fields. Official field types and reference semantics were checked; [Ingestion](pipeline/INGESTION.md#games-relationships-task-35) records the analytics rationale. No related objects are expanded.
- The existing fetch alias, shared paginator, runner, archive writer, and loader consume the expanded contract without further production changes. `raw_games` still has exactly `igdb_id`, `name`, `slug`, `payload`, and `fetched_at`. Complete payloads retain absent keys, empty arrays, source order, explicit nulls, and extra values without transformations or reference-existence requirements.
- Python 3.11.0: 50 baseline focused tests, 55 affected tests, and all 179 offline tests passed. CLI help and whitespace checks passed. New composed tests cover relationships through pagination/archive/raw preparation and preserve lifecycle ordering.
- Two live default-field samples (`batch_size=5`, `max_batches=1`) returned games `[1, 2, 3, 4, 5]`, each with all three nonempty relationship arrays. Source/archive/JSONB matched, five rows remained five distinct IDs on repeat, timestamps advanced, durable starts were independently visible, and both metadata records succeeded with 5/5 counts and NULL watermarks. No validation-only filter was needed.
- PostgreSQL readiness was awaited; the EXIT trap stopped it. Final service flags were all false and `pg_isready` returned no response. Existing database files/settings, user edits, and tracked artifacts were preserved.

Verified September 26 locally (September 27 UTC). [Testing](engineering/TESTING.md#task-35-verification) records exact commands, the harness, and run IDs. The live sample does not establish full source coverage or missing/empty relationship behavior (covered offline), reference completeness, live failure rollback, or ambiguous commit recovery. At that point only task 3.5 was newly completed; task 3.6 verification follows.

## Task 3.6 implementation and verification

- Extended only the CLI production module: `--entity` accepts all five names and `all`, defaults to games, and composes each entity’s existing callbacks. All mode runs games → genres → platforms → companies → involved_companies sequentially with independent batch limits and archives. Single-entity output overrides are supported; ambiguous all-mode overrides fail during parsing.
- The shared runner and entity modules are unchanged. Each entity keeps its durable start, raw context, success after raw exit, best-effort failure reporting, and acknowledged counts. Fail-fast behavior leaves earlier successful runs committed and never starts later entities. Queries, complete payloads, schemas, transactions, custom fields, relationship IDs, and NULL watermarks are preserved.
- Python 3.11.0: 71 baseline focused tests, 88 affected tests, and all 196 offline tests passed. CLI help and whitespace checks passed. New tests cover every selection/callback/path, original defaults/options, parse rejection before side effects, actual per-entity pagination limits/counts, and later failures retaining earlier successes. Existing lifecycle regressions remain intact.
- Two actual `--entity all --batch-size 5 --max-batches 1` CLI subprocesses passed. Ten distinct archives matched complete JSONB payloads; every table started and ended with five distinct rows; all sampled timestamps advanced. Ten new metadata records succeeded with 5/5 counts and NULL watermarks. All five games exercised each of the three relationship arrays on both runs. Existing archives/metadata were unchanged, and tables were never cleared.
- PostgreSQL was started only for live validation, readiness awaited, and stopped through an EXIT trap. Final service flags were all false; `pg_isready` exited 2 with no response. Database files/settings, unrelated user edits, and tracked artifacts were preserved.

Verified September 26 locally (September 27 UTC). [Testing](engineering/TESTING.md#task-36-verification) records exact commands, harness, and results. The live sample covers successful bounded runs, not full source/reference coverage, live failures, or ambiguous commit recovery. Durable-start visibility and failure ordering remain covered by offline regressions and earlier direct-runner smoke checks; this live CLI harness validates terminal metadata. Archive filenames retain second resolution and may collide for the same entity within a second. **Task 3.6 is complete; at that point Phase 4 had not been implemented.**

## Task 4.1 design verification

The [high-water-mark contract](pipeline/WATERMARKS.md) is accepted and checked against official IGDB documentation and the existing implementation. It defines entity policies, timestamp/window meanings, overlap, bounded-run eligibility, failure handling, examples, and implications for tasks 4.2–4.7. This completes design task 4.1 only: no runtime or test file changed; queries still start unfiltered at offset zero and watermarks remain NULL. CLI defaults, custom-field behavior, payloads, schemas, transactions, and existing artifacts are unchanged.

On September 26, 2026, all 88 focused lifecycle tests and 196 offline tests passed on Python 3.11.0; documentation links/examples and whitespace checks passed. [Testing](engineering/TESTING.md#task-41-design-verification) records commands/results. PostgreSQL was not started; read-only service inspection reported all three service flags false. No live ingestion or database writes occurred. At that point task 4.2 was next.

## Task 4.2 implementation and verification

Added `get_source_watermark(connection, schema_name, entity) -> datetime | None` in the existing metadata module. It selects the greatest successful non-NULL end with quoted schema and parameterized entity, ignores completion order/failed/running/NULL-ended rows, and returns `None` for no eligible history. All lookup failures propagate. It manages only its cursor, with no DDL, writes, explicit transaction management, or connection lifecycle changes. Caller transaction visibility determines the history read.

On September 27, 2026, all **41 metadata tests** and **217 offline tests** passed on Python 3.11.0. [Testing](engineering/TESTING.md#task-42-lookup-verification) records exact commands and fake/SQL coverage limits. PostgreSQL remained stopped/unregistered; no live ingestion or database validation occurred. Existing user edits and tracked artifacts were preserved with bytecode/cache writes disabled.

At that point only task 4.2 was newly complete and tasks 4.3–4.7 remained unchecked. The runner/CLI do not call the helper; default extraction still starts unfiltered from offset zero, retaining complete payloads/counts/transactions and NULL watermarks.

## Task 4.3 implementation and verification

Added immutable `SourceWindow` and `calculate_source_window(watermark, *, run_started_at)` in `src/ingestion/windows.py`. Explicit aware times yield a UTC whole-second cutoff; existing watermarks select `[max(0, W - 86400), U)` and reject `U <= W`. Bootstrap retains `U` with no lower bound and emits no filter. Games, companies, and involved-companies builders/fetchers accept optional `window=`; genres/platforms remain unfiltered reference reads. Default queries, ID ordering, offset-zero starts, stopping rules, complete returned payloads, and exact custom projections are preserved. Games now materializes iterable projections once, matching the other fetchers.

On September 27, 2026, **144 affected tests** passed before **315 total offline tests** on Python 3.11.0. [Testing](engineering/TESTING.md#task-43-window-verification) records commands and coverage limits. No live API/database validation occurred; PostgreSQL remained stopped/unregistered. Bytecode/cache writes were disabled and before/after snapshots preserve reviewability of existing untracked files and user changes.

At that point only task 4.3 was newly complete. CLI/shared-runner ingestion still performs no persisted lookup or window calculation/application, defaults to unfiltered reads from offset zero, and leaves watermarks NULL. Schemas, counts, archival, loading, dependencies, and transaction boundaries are unchanged. Eligibility, checkpoint writes, and tasks 4.4–4.7 remained deferred.

## Task 4.4 verification

Audited existing coverage and added `tests/test_raw_overlap.py` for games, companies, and involved companies. The existing loaders already satisfy the replay contract; no production changes were necessary. Eighteen deterministic cases verify optional overlapping fetches through real row preparation, source `id` → raw `igdb_id` conflict SQL, tied distinct IDs, changed/repeated/stale payloads, complete optional/nested values, input order, refreshed fetch timestamps/extracted columns, acknowledged input-row counts, and commit calls. Existing regressions retain empty loads, error propagation, and transaction boundaries.

On September 27, 2026, **120 baseline affected tests**, then **138 affected tests** and **333 total offline tests** passed on Python 3.11.0. [Testing](engineering/TESTING.md#task-44-overlap-upsert-verification) records exact commands, the audit, and coverage limits. These tests assert preparation, not live PostgreSQL constraint enforcement, idempotency, rollback, durability, or source completeness. Upserts do not enforce source-version ordering: a later stale response can overwrite a newer payload.

Only task 4.4 is newly complete; tasks 4.5–4.7 remain unchecked. Runtime incremental ingestion stays inactive with NULL watermarks. PostgreSQL remained stopped/unregistered, with no live ingestion or database writes. No dependencies, schemas, CLI flags, reference behavior, archival, counts, loading order, or transaction boundaries changed. Bytecode/cache writes were disabled; before/after snapshots cover already-untracked files and preserve existing user changes and tracked artifacts.

## Task 4.5 runtime checkpoint activation

Completed September 28, 2026 with 147 affected and 371 full offline tests passing on Python 3.11.0. Normal CLI runs for games, companies, and involved companies now look up their own greatest eligible end, capture one run-start cutoff, bootstrap unfiltered when no end exists, or apply the frozen overlap window across every page from offset zero. The running record stores the actual inclusive lower bound when filtered. After archive, acknowledged raw load, and successful raw context exit, the existing guarded terminal metadata update commits an eligible exclusive cutoff with success. Every supplied cap, custom/default-field override, arbitrary callback without trusted selection, invalid timestamp, or count mismatch withholds progress with a fixed safe warning while preserving returned payloads and acknowledged counts. Empty uncapped success can advance after the existing empty archive/raw DDL lifecycle. Genres/platforms remain unfiltered with both bounds NULL. All mode retains independent per-entity lifecycles and fail-fast order.

The verification uses queued fake source responses and database mocks. It checks emitted SQL, parameters, prepared rows, counts, commit calls, and context ordering, not live PostgreSQL constraint enforcement, rollback, durability, ambiguous commit outcomes, or IGDB completeness. PostgreSQL remained stopped/unregistered; no live ingestion or database writes occurred. Existing offset drift, timestamp visibility, stale-response overwrite, and ambiguous acknowledgment limits remain. At that point tasks 4.6–4.7 were unchecked; see [verification](engineering/TESTING.md#task-45-runtime-checkpoint-verification).

## Task 4.6 incremental behavior tests

Completed September 28, 2026 with 254 affected and 380 full offline tests passing on Python 3.11.0. Nine focused cases added consecutive bootstrap, overlap replay with tied IDs, and empty no-change runs; runtime UTC conversion, whole-second cutoffs, and epoch clamp; source/archive/raw failure counts and safe summaries; all-mode failure after earlier eligible successes; and retry from the prior boundary after a failed raw context exit. Existing tests already cover other timestamp, cap, projection, page-size/count, lookup, guard, and ambiguous acknowledgment cases. No production behavior changed. These fake boundaries establish emitted SQL, bound parameters, prepared rows, counts, commit calls, and context order, not live database effects or source completeness. PostgreSQL remained stopped/unregistered. Task 4.7 remains unchecked; see [verification](engineering/TESTING.md#task-46-incremental-test-verification).

## Task 4.7 explicit refresh and backfill

Completed September 28, 2026 with 189 affected and 410 full offline tests passing on Python 3.11.0. The CLI now accepts `--full-refresh` or paired `--backfill-start A --backfill-end B` with exact whole-second UTC `Z` instants. Parsing rejects incompatible/malformed intervals before settings or external work. Full refresh ignores prior progress for extraction, reads unfiltered from offset zero, and applies the existing eligibility gates plus `U > W` before publishing a cutoff for incremental entities. Backfill filters every page for all selected entities, records `A`, and always leaves end NULL. Subsequent normal runs use the greatest earlier eligible end or bootstrap. Reference entities remain unfiltered with NULL bounds outside explicit backfill. Raw upserts never delete rows.

Offline tests cover CLI rejection, query/metadata SQL and parameters, prepared payloads/counts/commit ordering, caps, timestamp and failure gates, reference entities, all mode, and reruns. They do not prove live PostgreSQL constraint enforcement, rollback, durability, ambiguous commit outcomes, IGDB filtering, or source completeness. PostgreSQL stayed stopped and unregistered; no live ingestion or database writes occurred. See [verification](engineering/TESTING.md#task-47-refresh-and-backfill-verification).

## Known repository hygiene items

The root `.gitignore` now covers Python/pytest caches, local environments and secret variants (while preserving `.env.example`), dbt targets/logs/packages/user metadata, raw local data, IDE/OS artifacts, and `docs/portfolio/`.

Ignore rules do not untrack existing files. The following **26 already tracked artifacts** were reported and left untouched, per task 1.1:

- 23 Python bytecode files under `src/**/__pycache__/` and `tests/__pycache__/`;
- `data/raw/raw_games_20260421T045948Z.jsonl`;
- `dbt/logs/dbt.log`;
- `dbt/.user.yml` (generated local dbt user metadata).

List the exact tracked paths with `git ls-files -ci --exclude-standard`. Removing them from the index is a separate reviewed cleanup; no index or history changes were made. `.env`, `.venv/`, and `docs/portfolio/` have no tracked files in this audit.
