# Current State

Last verified against the working repository on October 2, 2026 (Phases 6 and 7 complete; task 7.5 clean-volume bounded live workflow and all 533 enabled tests pass).

This document describes what exists in code today. Planned components belong in `ARCHITECTURE.md` and `ROADMAP.md`.

## Status summary

| Area | Status | Current implementation |
|---|---|---|
| Repository scaffolding | Complete | `src/`, `tests/`, `dbt/`, `dags/`, `docker/`, `app/`, `data/` exist |
| Local setup / repository baseline | Phase 1 verified | Fresh Python 3.11 install, offline unit tests, CLI help, and dbt scaffold parsing pass; previously tracked artifacts remain reported below |
| Configuration | Implemented | Environment-backed `Settings`, `.env.example`, cached settings loader; Python raw/metadata defaults to `raw`, dbt output defaults to `analytics` |
| Logging | Implemented | Shared logger with configurable log level |
| Twitch OAuth | Implemented | Client-credentials token request, in-memory token cache, expiration buffer |
| IGDB client | Implemented | APIcalypse POST requests, headers, retries/backoff, 401 token refresh |
| Games extraction | Implemented | Shared pagination requests the existing nine fields plus genre/platform/involved-company record IDs; offline and repeated live validation passed |
| Local raw archive | Implemented | Separate timestamped JSONL archives for each CLI-selected entity; default games path retained |
| PostgreSQL games load | Implemented | Connections, schema/table creation, and `ON CONFLICT` upsert into `raw_games` live in `src/storage/raw_games.py` |
| Ingestion run metadata | Implemented | Shared runner records running/succeeded/failed runs for the supplied entity with UTC timestamps, counts, and safe failure summaries |
| Python tests | Implemented for current modules | 450 passing offline tests cover staging/relationship/catalog/release-trend/performance/company-output SQL and documentation contracts, dbt sources, and existing ingestion behavior; 83 opt-in PostgreSQL/dbt cases bring the enabled suite to 533 passes; all 64 existing dbt behavior scenarios remain plus one catalog-container scenario, with three dedicated full-project schema checks |
| Additional IGDB entities | Genres, platforms, companies, and involved companies implemented and smoke verified | All use the shared runner with `raw_genres` / `raw_platforms` / `raw_companies` / `raw_involved_companies` |
| Incremental extraction | Offline and real-PostgreSQL integration checks pass; bounded live CLI modes verified | Games/companies/involved companies look up per-entity progress for normal/refresh runs. Normal runs bootstrap or use frozen overlap windows; explicit refresh reads unfiltered and may publish a newer eligible cutoff. Explicit backfills filter all selected entities over a caller interval and never publish progress. Genres/platforms stay unfiltered with NULL bounds on normal/refresh runs. |
| Generalized ingestion framework | Phase 2 complete (tasks 2.1–2.6) | CLI selects one or all five entities through an explicit ordered callback mapping and reusable lifecycle runner; offline tests cover the composed path with real helpers and fake external boundaries |
| dbt project | Five staging views, three relationship views, and five mart tables built and queried | `analytics.stg_games`, `analytics.stg_genres`, `analytics.stg_platforms`, `analytics.stg_companies`, and `analytics.stg_involved_companies` exist locally; five existing rows per staging model matched raw records; `analytics.int_game_genres` matched all 11 source-array pairs, including eight unmatched genre references; `analytics.int_game_platforms` matched all 14 platform pairs, including eight unmatched references; `analytics.int_game_companies` matched all five source records, including three with unmatched game/company references; `analytics.mart_game_catalog` matched all five staged games and every scalar/relationship value; `analytics.mart_release_trends` matched UTC yearly counts (1998: 2; 2000/2004/2014: 1 each), totaling five dated games plus zero undated; genre/platform performance marts match every source-derived value for four genre and nine platform rows, with summed game counts 11/14 across five games; company output matches all nine values for five observed company IDs, retaining two unloaded companies and two unloaded game references |
| dbt sources/tests/docs | Thirteen models and 80 columns documented; ten source, ten staging, eight relationship, four catalog, five release-trend, six performance, and three company-output tests pass against PostgreSQL | Python/dbt share `POSTGRES_RAW_SCHEMA` → legacy `POSTGRES_SCHEMA` → `raw` precedence. Opt-in tests build/query all thirteen models with explicit, legacy, and conflicting schema settings |
| Docker | Phase 7 complete; bounded clean-volume live workflow verified (7.5) | Profiled `runtime` supports direct Python/dbt commands, explicit `postgres:5432` connectivity, external allowlisted settings and non-root named archive/artifact volumes; ordinary startup runs only PostgreSQL; two bounded all-entity live runs, 13 models/46 dbt tests, container-replacement persistence and all 533 enabled tests pass through isolated Compose |
| Airflow | Not implemented | `dags/` is a placeholder |
| Streamlit | Not implemented | `app/` is a placeholder |
| AI layer | Not implemented / deferred | `src/ai/` is a placeholder |
| CI | Not implemented | No automated repository checks observed |

## Existing ingestion flow

Local PostgreSQL is managed on demand: `brew services run postgresql@17` via native `/opt/homebrew/bin/brew` starts it without login registration, and `services stop` ends the work session. A restart check preserved five genres and two run records. The server was left stopped and unregistered after October 2 verification; its on-disk databases remain intact. See [Local development](engineering/LOCAL_DEVELOPMENT.md#local-postgresql-on-apple-silicon).

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
    └── PostgreSQL <POSTGRES_RAW_SCHEMA>.raw_<entity> upsert
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

1. orchestrate the pipeline with Airflow (Phase 8);
2. add a thin analytics application;
3. add CI and final operational polish.

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

The original September 28 verification used queued fake source responses and database mocks. It checks emitted SQL, parameters, prepared rows, counts, commit calls, and context ordering, not live PostgreSQL constraint enforcement, rollback, durability, ambiguous commit outcomes, or IGDB completeness. PostgreSQL remained stopped/unregistered; no live ingestion or database writes occurred. Existing offset drift, timestamp visibility, stale-response overwrite, and ambiguous acknowledgment limits remain. At that point tasks 4.6–4.7 were unchecked; see [verification](engineering/TESTING.md#task-45-runtime-checkpoint-verification).

## Task 4.6 incremental behavior tests

Completed September 28, 2026 with 254 affected and 380 full offline tests passing on Python 3.11.0. Nine focused cases added consecutive bootstrap, overlap replay with tied IDs, and empty no-change runs; runtime UTC conversion, whole-second cutoffs, and epoch clamp; source/archive/raw failure counts and safe summaries; all-mode failure after earlier eligible successes; and retry from the prior boundary after a failed raw context exit. Existing tests already cover other timestamp, cap, projection, page-size/count, lookup, guard, and ambiguous acknowledgment cases. No production behavior changed. These fake boundaries establish emitted SQL, bound parameters, prepared rows, counts, commit calls, and context order, not live database effects or source completeness. PostgreSQL remained stopped/unregistered. Task 4.7 remains unchecked; see [verification](engineering/TESTING.md#task-46-incremental-test-verification).

## Task 4.7 explicit refresh and backfill

Completed September 28, 2026 with 189 affected and 410 full offline tests passing on Python 3.11.0. The CLI now accepts `--full-refresh` or paired `--backfill-start A --backfill-end B` with exact whole-second UTC `Z` instants. Parsing rejects incompatible/malformed intervals before settings or external work. Full refresh ignores prior progress for extraction, reads unfiltered from offset zero, and applies the existing eligibility gates plus `U > W` before publishing a cutoff for incremental entities. Backfill filters every page for all selected entities, records `A`, and always leaves end NULL. Subsequent normal runs use the greatest earlier eligible end or bootstrap. Reference entities remain unfiltered with NULL bounds outside explicit backfill. Raw upserts never delete rows.

Offline tests cover CLI rejection, query/metadata SQL and parameters, prepared payloads/counts/commit ordering, caps, timestamp and failure gates, reference entities, all mode, and reruns. They do not prove live PostgreSQL constraint enforcement, rollback, durability, ambiguous commit outcomes, IGDB filtering, or source completeness. PostgreSQL stayed stopped and unregistered; no live ingestion or database writes occurred. See [verification](engineering/TESTING.md#task-47-refresh-and-backfill-verification).

## Task 5.1 schema naming

The final defaults now separate `raw` for Python-owned source tables and `ingestion_runs` from `analytics` for future dbt-managed outputs. `POSTGRES_RAW_SCHEMA` selects the Python schema; `DBT_SCHEMA` selects the dbt profile output schema. Python falls back to legacy `POSTGRES_SCHEMA` only when the new variable is absent, so an explicitly configured `analytics` installation keeps reading its existing ingestion history. At task 5.1, no source or model had been created by dbt yet. Changing a default does not move old tables or watermark history; the [manual transition](engineering/LOCAL_DEVELOPMENT.md#schema-names-and-existing-analytics-installations) is required before an old installation adopts `raw`.

Focused configuration/CLI/storage/metadata tests passed (103), the full offline suite passed (412), and dbt parsed with generated output under `/private/tmp` without a database connection. PostgreSQL remained stopped and unregistered; no live ingestion or data movement occurred. See [verification](engineering/TESTING.md#task-51-schema-naming-verification).

## Task 5.2 dbt raw sources

`dbt/models/sources.yml` now declares the five Python-owned entity tables under `igdb`, using `POSTGRES_RAW_SCHEMA` (default `raw`) independently of dbt's `DBT_SCHEMA` output. Table and column descriptions reflect the actual raw DDL; each `igdb_id` has declared `unique` and `not_null` tests because it is the raw primary/upsert key. The involved-company ID belongs to the relationship record, while its game/company references and roles remain in JSONB. `ingestion_runs` is not an analytics source. There is no source freshness threshold because no ingestion cadence is documented.

Offline verification passed: 7 focused tests and 413 full-suite tests, dbt parsed five sources and ten key tests, and manifest checks resolved the source schema to both `raw` and `analytics` under corresponding `POSTGRES_RAW_SCHEMA` values. No dbt model, relation, or data migration was created; source tests still require a database to execute. The original source declaration required an explicit override for legacy installations; the September 29 correction adds the same `POSTGRES_SCHEMA` fallback used by Python. See [verification](engineering/TESTING.md#task-52-dbt-source-verification).

## Task 5.3 games staging

`dbt/models/staging/stg_games.sql` now selects only `source('igdb', 'raw_games')` at one row per game, exposing the raw key as `game_id`. It carries name/slug and fetch time, converts game first-release and source-update Unix seconds to `TIMESTAMPTZ`, casts ratings to `NUMERIC` and counts to `BIGINT`, and retains genre/platform/involved-company ID arrays as JSONB. Missing optional scalar values remain SQL NULL; empty arrays and zero counts are not replaced. See the [column contract](pipeline/DBT_TRANSFORMATIONS.md#stg_games-task-53).

The focused suite passed 19 tests and the full offline suite passed 415. dbt parsed and discovered one model without connecting to PostgreSQL. At that point the model had not been built or queried against raw data. The September 29 follow-up below closes that execution gap; at that point no other staging or relationship models existed.

## Tasks 4.5–5.3 reassessment fixes

Verified September 29, 2026 on Python 3.11.0 / PostgreSQL 17.11. The existing implementation is retained. dbt source resolution now shares Python’s legacy fallback, so the existing exported `POSTGRES_SCHEMA=analytics` works without editing `.env`, moving tables, or resetting ingestion history. `DBT_SCHEMA` remains independent.

Added `tests/integration/` with explicit `RUN_POSTGRES_INTEGRATION=1` opt-in, disposable schemas, cleanup on assertion failure, temporary dbt artifacts, and no live IGDB calls. Fifteen cases exercise the three incremental entities with real commits/rollback, overlap, caps, refresh/backfill, empty success, terminal failure/retry, and a simulated acknowledgment failure after a real terminal commit. Six dbt cases build all five populated sources and `stg_games` under explicit/legacy/precedence configurations, query every output column, and test invalid scalar reads. View creation does not evaluate row casts; the documentation now states this limitation correctly.

The focused configuration/SQL suite passed 11 cases (21 integration cases skipped by default). The full default suite passed **419**, with **21 skipped**; the full opted-in suite passed **440**. A separate build with the actual local settings passed all ten source tests, created `analytics.stg_games`, and verified its five rows against existing raw payloads. Raw-table and run-history hashes were unchanged. Temporary test schemas were removed, and PostgreSQL was stopped/unregistered after verification. See [exact commands and limits](engineering/TESTING.md#tasks-45-through-53-reassessment-fixes).

The preceding audit also ran two bounded live all-entity ingestions, backfills across all five endpoints, and a bounded full refresh in isolated schemas. No uncapped live bootstrap, source completeness guarantee, real network acknowledgment loss, or server-crash recovery was validated. At that point no later roadmap task was implemented; task 5.4 verification follows.

## Task 5.4 genres staging

`stg_genres` is a view selected directly from `igdb.raw_genres`, preserving one row per raw ID. It exposes `genre_id`, nullable raw `name`/`slug`, nullable Unix-seconds `source_updated_at` as `TIMESTAMPTZ`, and unchanged `fetched_at`. It follows the games conventions without joins, filtering, deduplication, defaults, or relationship expansion. See the [column contract](pipeline/DBT_TRANSFORMATIONS.md#stg_genres-task-54).

Verification passed: **17 narrow offline tests**, **420 full offline tests with 27 skipped**, **12 focused dbt/PostgreSQL cases**, and **447 full enabled tests**. The integration fixture now expects both views, retains games checks, and validates genre types, grain, every value, missing/null/empty fields, zero/negative timestamps, a large ID, and invalid timestamp reads across all three schema configurations.

The existing local configuration resolved raw and output schemas to `analytics`. A count first confirmed five stored genres; no live IGDB requests or additional ingestion were needed. `dbt build` created both views and passed ten source tests. All five genre rows (IDs 2, 4, 5, 7, 8) and five game rows were explicitly queried and compared with raw records. Before/after hashes for all five raw tables and ingestion history matched. Disposable schemas were removed; dbt artifacts went to `/private/tmp`, and PostgreSQL was restored to stopped/unregistered. `.env`, baseline edits, and tracked generated/private artifacts were preserved. See [exact commands and results](engineering/TESTING.md#task-54-genres-staging-verification).

At that point only task 5.4 was newly complete, with task 5.5 (`stg_platforms`) next; tasks 5.8–5.9 remain open. Invalid non-null source timestamps still fail on view reads, consistent with games; the stored five-row sample does not establish full source coverage.

## Task 5.5 platforms staging

`stg_platforms` is a single-source view over `igdb.raw_platforms`, with one row per raw ID. It exposes `platform_id`, nullable raw `name`/`slug`, nullable Unix-seconds `source_updated_at` as `TIMESTAMPTZ`, and unchanged `fetched_at`. It follows the existing staging convention without joins, filters, deduplication, relationship expansion, or business transformations. See the [column contract](pipeline/DBT_TRANSFORMATIONS.md#stg_platforms-task-55).

Verification passed: **18 narrow offline tests**, **421 full offline tests with 33 skipped**, **18 focused dbt/PostgreSQL cases**, and **454 full enabled tests**. Six added parameterized database cases verify platform types, grain, raw IDs, every output value, missing/null/empty optional fields, zero/negative timestamps, Unicode, a large ID, and invalid timestamp reads under all three schema configurations. Games and genres regression checks remain.

The unchanged local configuration built all three staging views and passed ten source tests in `analytics`. A count first confirmed five existing platforms, so no ingestion was needed. All five platforms (IDs 3–7), five games, and five genres were queried and compared with raw records. All raw-table and ingestion-history hashes matched before/after. Disposable schemas were removed, dbt artifacts stayed outside the repository, and PostgreSQL was restored to stopped/unregistered. Existing edits, `.env`, and tracked generated artifacts were preserved. See [exact commands, sample values, and cleanup](engineering/TESTING.md#task-55-platforms-staging-verification).

At that point only task 5.5 was newly complete; task 5.6 (`stg_companies`) was next. Tasks 5.8–5.9 remain open. The real sample has no missing platform values; synthetic database fixtures cover missing/null cases. Malformed non-null timestamps fail on view reads, and five stored rows do not establish full source coverage.

## Task 5.6 companies staging

`stg_companies` is a single-source view over `igdb.raw_companies`, preserving one row per raw ID. It exposes `company_id`, nullable raw `name`/`slug`, nullable Unix-seconds `source_updated_at` as `TIMESTAMPTZ`, and unchanged `fetched_at`. It uses the existing staging convention without joins, filters, deduplication, expansion, or business transformations. See the [column contract](pipeline/DBT_TRANSFORMATIONS.md#stg_companies-task-56).

Verification passed: **19 narrow offline tests**, **422 full offline tests with 39 skipped**, **24 focused dbt/PostgreSQL cases**, and **461 full enabled tests**. Six added parameterized company cases query actual types, view materialization, every output value, raw IDs and grain, missing/null/empty fields, Unicode, zero/negative/modern timestamps, a large ID, and invalid timestamp reads. All existing staging regressions and explicit/legacy/precedence schema checks remain.

Before the local build, a count confirmed five stored companies; no ingestion was needed. The unchanged local configuration built four views in `analytics` and passed ten source tests. All five companies (IDs 1–5), five games, five genres, and five platforms matched raw records, including timestamps and fetch times. All five raw-table and ingestion-history hashes matched before/after the build. Disposable schemas were removed, dbt artifacts stayed outside the repository, and PostgreSQL was restored to stopped/unregistered. Existing edits, `.env`, raw files, and tracked generated artifacts were preserved. See [exact commands, company values, and cleanup](engineering/TESTING.md#task-56-companies-staging-verification).

At that point only task 5.6 was newly complete; task 5.7 (`stg_involved_companies`) was next. Tasks 5.8–5.9 remain open. Missing/null cases are verified with synthetic database fixtures; the stored company sample has no missing values. Invalid non-null timestamps fail when read, and five real rows do not establish full IGDB coverage.

## Task 5.7 involved-companies staging

`stg_involved_companies` is a single-source view over `igdb.raw_involved_companies` at one row per relationship record ID (`involved_company_id`). It exposes nullable BIGINT `game_id`/`company_id`, nullable BOOLEAN `developer`/`publisher`, nullable Unix-seconds `source_updated_at` as TIMESTAMPTZ, and unchanged `fetched_at`. Missing/JSON-null scalars remain SQL NULL and false roles remain false. Repeated game/company pairs and references absent from bounded raw samples are retained. See the [column contract](pipeline/DBT_TRANSFORMATIONS.md#stg_involved_companies-task-57).

Verification passed: **20 narrow offline tests**, **423 full default tests with 45 skipped**, **30 focused dbt/PostgreSQL cases**, and **468 full enabled tests**. All earlier regressions remain. Six new parameterized database cases check actual types, view materialization, every value, relationship grain, missing/null fields, all four role combinations, repeated/unmatched pairs, large IDs, zero/negative/modern timestamps, and invalid scalar reads across the three schema settings.

A pre-build count confirmed five existing involved-company records, so no ingestion was needed. The unchanged local configuration built all five views in `analytics` and passed ten source tests. Every field in relationship IDs 2, 6, 7, 8, and 9 matched raw records, as did all five rows in each earlier view. All raw-table and ingestion-history hashes matched before tests and after the local build. No disposable schemas remained. dbt artifacts stayed outside the repository, and PostgreSQL was restored to stopped/unregistered. Existing edits, `.env`, raw archives, and tracked generated artifacts were retained; nothing was committed. See [exact commands, comparisons, environment repair, and cleanup](engineering/TESTING.md#task-57-involved-companies-staging-verification).

At that point only task 5.7 was newly complete; task 5.8 (dbt tests) was next. Task 5.9 remains open. Missing/null and both-true/both-false role cases use synthetic fixtures; the five stored relationships cover developer-only/publisher-only roles. Invalid non-null scalars fail on read, and a bounded sample does not establish complete references or source coverage.

## Task 5.8 dbt tests

Added ten `unique`/`not_null` tests for the five staging primary identifiers, alongside the existing ten source-key tests. Involved companies uses its own relationship record ID; references and game/company pairs need not be unique. Strict relationship checks remain deferred because independently bounded ingestion does not guarantee referenced entities, references may be absent/null, and games retain JSONB arrays without bridge models. See the [per-relationship policy](pipeline/DBT_TRANSFORMATIONS.md#staging-identifier-tests-task-58).

Verification passed: **12 narrow offline tests**, **424 full default tests with 51 skipped**, **36 focused dbt/PostgreSQL tests**, and **475 full enabled tests**. One new offline contract test and six database cases cover duplicate/NULL model output, exact model-test failures with valid raw keys, and recovery after view restoration under all three schema settings. Existing scalar, reference/role, source-schema precedence, independent output-schema, and ingestion regressions remain.

The local build created five views and passed **twenty dbt tests**. All five rows in every staging model matched the existing raw records; no ingestion was needed. Hashes of all five raw tables and 21 ingestion-run records matched before tests and after the build. Disposable schemas were removed and PostgreSQL was restored to stopped/unregistered. Existing edits, `.env`, raw archives, and tracked artifacts were preserved, with dbt artifacts outside the repository. See [exact commands and results](engineering/TESTING.md#task-58-dbt-tests-verification).

At that point only task 5.8 was newly complete; task 5.9 (model/column documentation and build verification) was next. Identifier tests do not validate all scalar casts or establish source completeness.

## Task 5.9 model documentation and build verification

All five staging models and all 35 output columns now have descriptions in `dbt/models/staging/schema.yml`, based on the verified source/model contracts. They document lineage, grain, types, scalar and JSONB null distinctions, timestamp meanings, rating/count pass-through, reference caveats, and independent nullable roles. Existing SQL, identifier tests, relationship-test deferrals, schema precedence, and independent `DBT_SCHEMA` are unchanged.

Verification passed: **17 narrow offline tests**, **429 full default tests with 51 skipped**, **36 focused dbt/PostgreSQL tests**, and **480 full enabled tests**. Five new offline cases check complete/nonempty documentation against SQL projections; existing database fixtures verify manifest descriptions against actual view columns under all three schema configurations.

The existing-data build created five views and passed twenty dbt tests. All model/column descriptions survived parsing exactly, and every output value for five existing rows per view matched raw records. No ingestion was needed. All five raw-table hashes and the hash of 21 ingestion-run records matched before tests and after the build. Disposable schemas were removed, artifacts stayed outside the repository, and PostgreSQL was restored to stopped/unregistered. Existing edits, `.env`, raw archives, and tracked artifacts were preserved. See [exact commands, results, and cleanup](engineering/TESTING.md#task-59-model-documentation-and-build-verification).

At that point task 5.9 completed Phase 5's documented/tested staging build criterion; task 6.1 follows below. View builds and identifier tests still do not evaluate every scalar cast or establish full source/reference coverage; the verification queries stored values separately and retains the existing relationship-test deferrals.

## Task 6.1 game-genre relationship

`int_game_genres` is a documented two-column view over `stg_games`, at one distinct BIGINT `(game_id, genre_id)` pair per represented association. Lateral JSONB expansion emits zero rows for absent/null/empty arrays and collapses duplicate pairs after casting. It retains IDs missing from independently bounded genre ingestion without a lookup join or reference-existence test. Null members fail a required-key test; malformed non-null arrays/members raise on evaluation. Staging/raw retain original array distinctions. See the [contract](pipeline/DBT_TRANSFORMATIONS.md#int_game_genres-task-61).

Validation passed: **15 narrow offline tests**, **15 new PostgreSQL cases**, **six affected staging failure/recovery cases**, **431 full default tests with 66 skipped**, and **497 full enabled tests**. Coverage includes exact values/types/grain, missing/null/empty arrays, repeated/reused/large/zero IDs, unmatched genres, malformed inputs, and intentional key/grain failures with recovery across all three source-schema modes. Source precedence and independent `DBT_SCHEMA` are unchanged.

The existing-data build created six views and passed 23 dbt tests. Documentation covers all six models and 37 columns; all staging rows matched raw values, and the new view matched all 11 pairs from existing game arrays. Eight pairs reference missing genres (IDs 12, 13, 31) and remain present. No ingestion was needed. Hashes of all five raw tables and 21 ingestion-run records matched before tests and after the build. Disposable schemas were removed; dbt artifacts stayed outside the repository. PostgreSQL was restored to stopped/unregistered with all three service flags false. Existing edits, `.env`, raw archives, and tracked artifacts were preserved. See [exact commands, results, and cleanup](engineering/TESTING.md#task-61-game-genre-relationship-verification).

At that point only task 6.1 was newly complete; task 6.2 verification follows below. This bounded sample does not establish source/reference completeness, and zero relationship rows do not prove a game has no real-world genres.

## Task 6.2 game-platform relationship

`int_game_platforms` is a documented two-column view over `stg_games`, at one distinct BIGINT `(game_id, platform_id)` pair per represented association. It follows the genre bridge's lateral expansion and post-cast deduplication: absent/null/empty arrays yield no rows, unmatched platform IDs survive, null members fail a required-key test, and malformed non-null arrays/members raise on evaluation. Two key tests and a singular pair-uniqueness test protect the model. The genre SQL, source-schema precedence, and independent `DBT_SCHEMA` behavior are unchanged. See the [platform contract](pipeline/DBT_TRANSFORMATIONS.md#int_game_platforms-task-62).

Validation passed: **17 narrow offline tests**, **15 new PostgreSQL cases**, **433 full default tests with 81 skipped**, and **514 full enabled tests**. The new cases cover values/types/grain/documentation, absent/null/empty arrays, duplicate and cast-normalized IDs, reused/large/zero/negative IDs, incomplete coverage, malformed inputs, and deliberate data/output failures with recovery under all three source-schema modes. Existing genre/staging and ingestion tests remain passing.

The existing-data build created seven views and passed 26 dbt tests. All seven models and 39 columns are documented. Every staging row matched raw records; the genre bridge still matched all 11 pairs, and the platform bridge matched all 14 pairs, including eight unmatched references. No ingestion was needed. Hashes of five raw tables and 21 ingestion-run records remained unchanged. Disposable schemas were removed and dbt artifacts stayed outside the repository. PostgreSQL was restored to stopped/unregistered; all three service flags were false and readiness reported no response. Existing edits, `.env`, archives, and tracked artifacts were preserved. See [exact commands, file inventory, results, and cleanup](engineering/TESTING.md#task-62-game-platform-relationship-verification).

At that point only task 6.2 was newly complete; task 6.3 verification follows below. Bounded ingestion does not prove full reference coverage, and zero bridge rows do not prove a game has no platform associations.

## Task 6.3 game-company relationship

`int_game_companies` is a five-column view over `stg_involved_companies`, at one
row per `involved_company_id`. Distinct IDs sharing game/company pairs remain
separate, even with identical roles. Nullable/unmatched references and independent
nullable developer/publisher flags pass through. Both-true, both-false, and unknown
roles are valid; only the record ID is required and unique. Staging casts remain
unchanged. See the [grain and role contract](pipeline/DBT_TRANSFORMATIONS.md#int_game_companies-task-63).

Validation passed: **18 narrow offline tests**, **12 new PostgreSQL cases**,
**435 full default tests with 93 skipped**, and **528 full enabled tests**.
Coverage includes exact values/types, repeated pairs, all nine nullable role
combinations, null/partial/unmatched references, castable strings, malformed-input
recovery, and deliberate duplicate/NULL identifier failures with recovery. All
existing staging, genre/platform, ingestion, and source-schema precedence checks
remain passing; independent `DBT_SCHEMA` behavior is retained.

The existing-data build created eight views and passed 28 dbt tests. All eight
models and 44 columns are documented. Every staging value and all 11 genre/14
platform pairs still match sources. The five company relationship rows match raw
and staged records exactly; records 2, 8, and 9 retain unloaded game/company
references. No ingestion was needed. Hashes of all five raw tables and 21 run
records remained unchanged; disposable schemas were removed, artifacts stayed
outside the repository, and PostgreSQL was restored to stopped/unregistered.
Existing uncommitted work, `.env`, archives, and tracked artifacts were preserved.
See [exact commands, results, files, and cleanup](engineering/TESTING.md#task-63-game-company-relationship-verification).

At that point only task 6.3 was newly complete; task 6.4 follows below. The bounded
sample does not establish source completeness. View creation and identifier tests
alone do not evaluate every reference/role cast; explicit queries verify values.

## Task 6.4 game catalog

`mart_game_catalog` is an eleven-column table with exactly one row per staged
game, including games with missing optional data. Eight descriptive/release/rating
columns pass through without defaults or thresholds. Independently aggregated,
numerically ordered JSONB arrays carry observed genres, platforms, and company
relationship records with available names. Unmatched references, repeated company
records, and independent nullable roles survive. Empty arrays mean no observed
rows in bounded stored data, not verified real-world absence. The table refreshes
on dbt rebuild. See the [contract defined before implementation](pipeline/DBT_TRANSFORMATIONS.md#mart_game_catalog-task-64).

Validation passed: **22 narrow offline tests**, **33 narrow PostgreSQL cases**
(27 new catalog cases plus six staging regressions), **438 full default tests with
120 skipped**, and **558 full enabled tests**. Exact scalar/object comparisons,
fanout/duplicate/nullable-role behavior, missing reference coverage, deliberate
output defects, malformed-input failure, recovery, and all three schema modes are
covered. Existing staging/relationship SQL and contracts remain unchanged.

The existing-data build created eight views and the catalog table and passed all
31 dbt tests. Nine models and 55 columns are documented. The catalog exactly covers
five staged games with 11 genre objects, 14 platform objects, and two company
relationship objects (records 6 and 7 for game 2). Eight unmatched genre references
and eight unmatched platform references remain with null names. Company records
2, 8, and 9 remain in the intermediate model for unloaded games; they do not create
catalog rows. Every staging/relationship value still matches its raw sources.
No ingestion was needed. Raw/history hashes matched before tests, before the build,
and afterward; disposable schemas were removed, artifacts stayed outside the
repository, and PostgreSQL was restored to stopped/unregistered. Earlier edits,
`.env`, raw archives, and tracked artifacts were preserved. Only roadmap checkbox
6.4 changed at that point; task 6.5 verification follows below. See [commands, results, files, and cleanup](engineering/TESTING.md#task-64-game-catalog-verification).

## Task 6.5 annual release trends

`mart_release_trends` is a documented two-column table directly over `stg_games`:
one row per observed UTC year of the game-level `first_release_at`, counting each
dated game once. NULL dates are excluded without implying unreleased games;
unobserved years are omitted, not zero-filled or treated as verified absence.
Existing zero/negative Unix epochs remain valid, without date cutoffs. No joins
introduce relationship fanout. Summed counts plus undated games reconcile to all
staged games at the same source snapshot. Rebuild after ingestion. See the
[contract](pipeline/DBT_TRANSFORMATIONS.md#mart_release_trends-task-65).

Validation passed: **19 narrow offline**, **45 narrow PostgreSQL** (39 new plus
six staging defect cases), **441 full default with 159 skipped**, and **600 full
enabled** tests. New cases cover exact grain/counts/types/docs, UTC boundaries
under three session timezones, multiple years/games, empty/all-undated input,
zero/negative epochs, snapshot behavior, and reconciliation. Nine deliberate
output defects prove all five dbt invariants fail and recover; malformed release
timestamps fail materialization and recover after correction. All earlier tests,
schema precedence, independent `DBT_SCHEMA`, and catalog behavior remain intact.

The existing-data build produced eight views plus two tables and passed 36 dbt
tests. Ten models and 57 columns are documented. Annual counts exactly match
staging and catalog: 1998 → 2; 2000/2004/2014 → 1 each. Five counted games plus
zero undated games equal all five stored games. Earlier model comparisons still
pass. No ingestion or settings/schema migration was needed. Raw/history hashes
and unrelated file hashes matched; disposable schemas were removed, external dbt
artifacts retained, and PostgreSQL stopped/unregistered. At that point only task 6.5 was newly
complete; task 6.6 verification follows below. See [exact commands, files, results, and
cleanup](engineering/TESTING.md#task-65-annual-release-trends-verification).

## Task 6.6 genre/platform performance

Separate seven-column `mart_genre_performance` and `mart_platform_performance`
tables have one row per observed dimension ID. Each independently deduplicates
bridge pairs, joins staged game ratings, aggregates by ID, and left joins its label.
Unmatched references, loaded NULL names and empty names survive; dimensions without
observed games are omitted. Five metrics expose game count, rated-game count,
unweighted mean rating, rating-count contributor count, and summed supplied rating
counts. NULL and supplied zero remain distinct; no valid staging value is filtered
or reinterpreted. Only rating/rating_count are used; total_rating stays separate.
See the [contract documented before implementation](pipeline/DBT_TRANSFORMATIONS.md#genreplatform-performance-task-66).

Validation passed: **16 narrow offline**, **27 narrow PostgreSQL** (21 new plus
six staging regression cases), **447 full default with 180 skipped**, and
**627 full enabled** tests. Every new column and all declared dbt invariants are
covered by deliberate output defects with exact failure assertions and recovery.
Doubled bridge rows cannot inflate any metric. Malformed projected inputs fail
materialization and recover after correction. Existing model SQL/contracts,
source-schema precedence, and independent DBT_SCHEMA behavior remain unchanged.

The existing-data build produced eight views and four tables with **42 passing dbt
tests**, twelve models and 71 documented columns. All earlier source comparisons
still pass. Every metric/label matches independent Python grouping for four genre
and nine platform rows; their counts sum to 11 and 14 across five distinct games.
No ingestion was needed. Raw/history hashes and unrelated baseline files match;
disposable schemas were removed and PostgreSQL stopped/unregistered. Existing
uncommitted work, .env, archives, and tracked artifacts were preserved. Only 6.6
was marked complete at that point; task 6.7 verification follows below. See [exact commands, rows,
files, and cleanup](engineering/TESTING.md#task-66-genreplatform-performance-verification).

These are snapshots of bounded observations: rebuild after ingestion. Missing
associations/dimensions do not establish real-world absence, rating-count sums
are not distinct raters, and cross-dimension totals can repeat games.

## Task 6.7 company output

`mart_company_output` is a nine-column table at one row per observed non-NULL
company ID from `int_game_companies`. Counts distinguish relationship records,
NULL-game records, distinct non-NULL game references (including unloaded games),
loaded games, and explicitly observed developer/publisher games. Company loading
state and nullable/empty labels preserve reference context. Repeated records
cannot inflate distinct-game metrics; any true role evidence qualifies a game,
unknown remains unknown, and role counts can overlap. Loaded unobserved companies
are omitted; NULL-company records remain upstream for reconciliation. See the
[contract defined before implementation](pipeline/DBT_TRANSFORMATIONS.md#mart_company_output-task-67).

The existing five relationship records were sufficient without ingestion: company
IDs 1/3/4/7/11 reference game IDs 2/37/38. Companies 7/11 and games 37/38 are
unloaded and retained. The build creates eight views and five tables, passes all
45 dbt tests, and documents thirteen models/80 columns. Every model comparison
and every company-output value matches independent source-derived results.

Validation: **14 narrow offline**, **45 focused PostgreSQL**, **450 full default
with 207 skipped**, and **657 full enabled** tests pass. New cases cover every
nullable role combination, source replay, repeated/conflicting pairs, unmatched
references, NULLs, valid zero/negative/large IDs, empty input, exact reconciliation,
lookup multiplicity, and deliberate invariant/cast failures with recovery.
Existing SQL/contracts, source precedence, and independent DBT_SCHEMA are unchanged.

Raw/history and unrelated file hashes match, disposable schemas are removed,
artifacts remain external, and PostgreSQL is stopped/unregistered. Existing
uncommitted work, .env, archives and tracked artifacts are preserved. Only task
6.7 is newly complete; 6.8 and later remain unchecked. See [exact commands,
results, rows, files and cleanup](engineering/TESTING.md#task-67-company-output-verification).
These are bounded observations, not complete company catalogs or verified absence.
Rebuild after ingestion; role and cross-company counts must not simply be summed
as distinct games.

## Test-harness optimization (October 2, 2026)

An explicitly requested optimization before task 6.8 separates 64 dbt behavior
scenarios from three full-project schema-configuration checks. All 38 existing
behavior test function bodies and non-schema parameters remain unchanged. Each
scenario still gets isolated schemas and cleanup; setup builds staging plus only
explicitly requested model dependencies. Repeated dbt commands reuse parsing only
within their own test. The three full-project cases retain the 13-model/45-test
build contract, verify explicit/legacy/precedence settings and independent output
schemas, and compare fresh/cached model resolution and documented columns.

The same eleven representative scenarios improved from **91.07s to 66.79s**.
The full enabled suite improved from **657 passed in 1,417.90s** to **532 passed in 358.87s (0:05:58)**
(**74.7% less time**). Case counts drop because the two alternate-schema
repetitions of each behavior scenario are replaced by dedicated configuration
checks; data-edge-case × schema-mode combinations are no longer exhaustively
multiplied. The default suite remains **450 passed**, with **82 skipped** database
cases. Narrow offline checks pass 20; all three full-project schema checks pass.

Production code, model SQL/YAML, 45 dbt invariants, dependencies, existing raw/history,
.env and earlier uncommitted work are unchanged. No ingestion or existing-data mart
rebuild was needed. Disposable schemas were cleaned and PostgreSQL restored to
stopped/unregistered. No roadmap checkbox changed; **6.8 remains open**. See
[coverage mapping, exact commands, timing evidence and cleanup](engineering/TESTING.md#test-harness-optimization-verification).

## Task 6.8 verification

Audited all five marts and their 36 columns; thirteen models/80 columns remain
fully documented. The [coverage matrix](engineering/DATA_QUALITY.md#mart-contract-coverage-matrix-task-68)
distinguishes dbt invariants, integration-only value checks, and bounded-data
limitations. Refresh, metric denominator and required catalog-container semantics
are explicit. Existing reconciliations and value checks were sufficient except
for one added catalog JSON-array-container invariant; no production model SQL changed.

The build passes **46 dbt tests** and every local mart row/metric matches independent
source-derived results. Validation passes **15 narrow offline**, **15 focused
PostgreSQL**, **450 default with 83 skipped**, and **533 full enabled** tests
(373.86s). All 64 prior behavior scenarios remain, plus one failure/recovery case;
three full-project schema checks and isolated per-test caches are preserved.

Raw/history and private-file hashes match, disposable schemas are cleaned, artifacts
are external, and PostgreSQL is stopped/unregistered. No ingestion, dependency,
settings, model SQL or architecture change was needed. Existing uncommitted work
and tracked artifacts remain intact; nothing was committed. **Only 6.8 is newly
complete; Phase 6 is complete and Phase 7/later remain unchecked.** See
[exact commands, results and task-only files](engineering/TESTING.md#task-68-mart-contract-audit-verification).

## Task 7.1 Docker PostgreSQL verification

Root `compose.yaml` now defines only `postgres:17.11-bookworm`, a TCP
`pg_isready` health check, and the project-scoped `postgres_data` volume at
`/var/lib/postgresql/data`. The default host binding is `127.0.0.1:5433`;
database/user/password are required externally. Official registry metadata
confirmed the version, ARM64 support, volume path and shutdown signal.

Standalone Compose 5.6.0 and installed Compose 5.5.1 configuration checks pass,
including required settings, port overrides and separate project volumes. After
the initial missing-engine blocker, the user selected Colima. Installed Colima
0.10.3/Lima 2.2.0/Docker CLI 29.8.1; the named VM runs Docker Engine 29.5.2.
Its separate Docker client configuration preserves the old Desktop credentials.

Health and authenticated access pass; an incorrect password is rejected. A
committed synthetic marker survives actual container removal/recreation against
the same named volume, and stop/start. The first full run exposed one test-only
reconnect that omitted its password. Passing the existing connection password
explicitly fixes that case without changing production code or optimized setup.
The affected case passes; the default suite passes **450 with 83 skipped** and
the full enabled suite passes **533 in 374.61s**. Each of the three full-project
schema modes retains 13 models, 80 documented columns and **46 passing dbt tests**.

Disposable schemas and Compose resources were cleaned. Colima and native PostgreSQL
are stopped; no login startup was enabled. Native cluster files, `.env`, archives,
tracked artifacts and earlier work are preserved. No live IGDB call or real-data
ingestion/migration occurred. **Only 7.1 is newly complete; 7.2 and later remain
unchecked.** See [service operation](engineering/LOCAL_DEVELOPMENT.md#docker-postgresql-task-71)
and [exact checks and runtime procedure](engineering/TESTING.md#task-71-docker-postgresql-validation).

## Task 7.2 shared Python/dbt image verification

`docker/Dockerfile` uses official `python:3.11.16-slim-bookworm` and installs
unchanged `requirements.txt`. Source, dbt definitions and tests live in `/app`;
commands run as UID 10001, and default invocation displays ingestion CLI help.
Existing Python and dbt commands need no wrapper or application changes. dbt
artifacts default to `/tmp`; telemetry and Python bytecode writes are disabled.
`.dockerignore` excludes credentials, Git, environments, archives, private docs
and generated files from the build context. Credentials are supplied only at runtime.

An actual Linux ARM64 build passes three context/image checks, `pip check`,
Python/dbt version checks, both CLI help commands, and offline dbt parsing.
All eleven image layers were audited; no source credentials or excluded project
files were present. Runtime versions include dbt Core 1.12.5, dbt-postgres 1.11.0
and Psycopg 3.3.6. Dependency ranges and the base tag remain mutable.

Container results: **450 passed / 83 skipped in 1.31s** by default; the targeted
timezone case passes; **533 passed in 275.40s** with integration enabled.
The existing 65 dbt behavior scenarios, three full-project schema checks and
15 ingestion cases are unchanged. Each full-project mode retains thirteen models,
80 documented columns and all 46 passing dbt tests.

Validation used an isolated internal Docker network and disposable PostgreSQL
17.11 with tmpfs storage, explicit connection settings and a generated in-memory
password. No live IGDB access, repository mounts, real-data ingestion or native
cluster writes occurred. Artifacts are external; disposable schemas, containers
and network were cleaned, and Colima/native PostgreSQL are stopped/unregistered.
Earlier work, `.env`, raw archives, tracked artifacts and the Git index remain
preserved. **Only 7.2 is newly complete; 7.3 and later remain unchecked.** See
[image operation](engineering/LOCAL_DEVELOPMENT.md#shared-pythondbt-image-task-72)
and [exact validation evidence](engineering/TESTING.md#task-72-shared-image-validation).

## Task 7.3 Compose runtime verification

`runtime` reuses the shared image behind the `tools` profile. Ordinary Compose
startup runs only PostgreSQL; explicit one-off commands wait for its health check.
The verified PostgreSQL image, TCP check, persistent database volume and default
loopback binding are unchanged. Runtime addressing is fixed to `postgres:5432`,
independently of the host-published port. Explicit environment wiring preserves
`POSTGRES_RAW_SCHEMA` → `POSTGRES_SCHEMA` → `raw` and independent `DBT_SCHEMA`.
No credentials are baked into images or passed through build arguments.

Named volumes preserve archives at `/app/data/raw` and direct dbt artifacts at
`/tmp/dbt`, including after `run --rm` and `down`. Initial image directory ownership
allows UID 10001 to write without a bootstrap/permission entrypoint or host mounts.
Synthetic persistence and external `docker cp` exports pass after replacement.

Six narrow Compose checks, three image/context checks, an eleven-layer audit,
version/help commands, `pip check`, four offline schema parses, authenticated
internal database access, required/incorrect credential rejection and automatic
health dependency selection pass. Container suites: **450 passed / 83 skipped in
1.33s**, **1 narrow regression in 6.18s**, **533 enabled in 276.61s**. All existing
scenarios and the optimized harness are unchanged; each full-project schema mode
retains thirteen models, 80 columns and all 46 passing dbt tests.

Validation uses synthetic fixtures, explicit task-owned projects, `/dev/null` env
files, generated passwords and none/internal networking with HTTP rejection
fixtures. No IGDB calls, live ingestion, migration or native database changes
occurred. Disposable schemas/resources and the task-built image are removed;
Colima/native PostgreSQL are stopped/unregistered. Prior work, `.env`, archives,
tracked artifacts, native cluster, original Docker config and Git index match the
saved baseline outside the task-only changes. Only **7.3** is newly complete;
**7.4–7.5 and later remain unchecked**. See [commands and caveats](engineering/LOCAL_DEVELOPMENT.md#on-demand-compose-runtime-task-73)
and [validation/preservation evidence](engineering/TESTING.md#task-73-compose-runtime-validation).

## Task 7.4 initialization/startup documentation

The [Compose first-use and subsequent-session workflow](engineering/LOCAL_DEVELOPMENT.md#compose-first-use-and-subsequent-sessions-task-74)
consolidates environment selection, build, readiness/authentication, on-demand
commands, persistence/export and shutdown/restart. It distinguishes PostgreSQL's
first-empty-volume database/user initialization, Python-owned raw tables/history
and dbt-owned transformations, retaining addressing and schema/credential semantics.
README and dbt navigation point to that workflow. No runtime behavior changed.

Offline checks pass: six Compose configuration checks, actual CLI help, dbt parsing
(13 models, five sources, 46 tests), 55 focused Python tests and 450 default tests
with 83 database cases skipped. Documentation links, Bash syntax, whitespace and
task-only preservation checks pass. Exact commands are in the
[verification record](engineering/TESTING.md#task-74-startup-documentation-verification).
Colima/native PostgreSQL remain stopped/unregistered; existing work, credentials,
archives, tracked artifacts, native data and Docker resources are preserved.
The live ingestion → dbt sequence is documentation only: **7.4 is complete;
7.5 and later remain unchecked**. No clean-volume pipeline or new integration
validation was run in this task.

## Task 7.5 clean-volume live workflow verification

The documented Compose workflow passed on October 2, 2026 using project
`data-platform-task75-20261002-a7c9`, unused loopback port `55475`, explicit
`task75_validation` database/user, a generated private password and three new
project-owned volumes. The current runtime was built using existing tooling.
PostgreSQL initialization, TCP readiness and authenticated `postgres:5432` access
passed; no application relations existed before ingestion. A documentation fix
uses `dbt debug --connection`: plain `dbt debug` authenticates but fails its Git
check because the slim image has no Git. No runtime/code/dependency fix was needed.

Two actual `--entity all --batch-size 5 --max-batches 1` CLI runs each loaded five
records per entity. Each raw table retains five distinct IDs, both archives and
successful 5/5 run records; all ten watermark starts/ends are NULL. The second
run refreshed all 25 fetch timestamps and retained earlier history. Source IDs
and payloads happened to be unchanged; validation compared the archive union and
latest payload per ID rather than assuming source stability.

The complete live-data build passed **13 models and 46 tests**. All staging
values, relationships and five marts reconciled to raw data. Model row counts:
five per staging view; genre/platform/company relationships 11/14/5; catalog 5,
release trends 4, genre/platform performance 4/9, company output 5. Annual counts
are 1998: 2 and 2000/2004/2014: 1 each, with zero undated games. Unloaded
references remain represented according to the existing contracts.

Database rows/history/models and archive/dbt hashes matched exactly after
`down` and recreation with the same volumes. A database SQL dump, ten JSONL
archives, dbt artifacts, snapshots, command logs and test artifacts were exported
outside the repository before scoped cleanup. New test evidence: five applicable
Compose checks, three image checks, 55 narrow offline tests, 450 default tests
with 83 skipped, 15 ingestion integration tests, and **533 enabled tests in 273.11s**.
Each of the three synthetic schema-mode builds also passed all 46 dbt tests.

Only task-specific documentation changed. All task containers/network/volumes and
the task image were removed; prior Docker inventory matches. Colima/native
PostgreSQL are stopped/unregistered, and prior work, `.env`, archives, generated
tracked files, native data, Docker configuration and Git index are preserved.
Only **7.5** is newly checked; **Phase 7 is complete** because its documented
clean-environment core-pipeline exit criterion is satisfied. Phase 8 and later
remain unchecked. This is bounded startup validation, not full source coverage,
a clean-clone/new-machine test, or an uncapped incremental bootstrap. See
[exact commands, evidence and limits](engineering/TESTING.md#task-75-clean-volume-live-workflow-verification).

## Known repository hygiene items

The root `.gitignore` now covers Python/pytest caches, local environments and secret variants (while preserving `.env.example`), dbt targets/logs/packages/user metadata, raw local data, IDE/OS artifacts, and `docs/portfolio/`.

Ignore rules do not untrack existing files. The following **26 already tracked artifacts** were reported and left untouched, per task 1.1:

- 23 Python bytecode files under `src/**/__pycache__/` and `tests/__pycache__/`;
- `data/raw/raw_games_20260421T045948Z.jsonl`;
- `dbt/logs/dbt.log`;
- `dbt/.user.yml` (generated local dbt user metadata).

List the exact tracked paths with `git ls-files -ci --exclude-standard`. Removing them from the index is a separate reviewed cleanup; no index or history changes were made. `.env`, `.venv/`, and `docs/portfolio/` have no tracked files in this audit.
