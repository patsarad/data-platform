# Implementation Roadmap

This is the authoritative implementation order. Tasks are intentionally small enough to hand to Codex one at a time and review before continuing.

Status legend: `[x]` implemented and verified, `[ ]` remaining.

## Phase 0 — Existing foundation

- [x] Create project/package scaffolding.
- [x] Initialize dbt project structure.
- [x] Add environment-backed configuration and shared logging.
- [x] Implement Twitch OAuth client-credentials authentication and token caching.
- [x] Implement reusable IGDB client with retry/backoff and 401 refresh.
- [x] Implement batched games extraction.
- [x] Preserve fetched games as timestamped JSONL.
- [x] Create/upsert `raw_games` in PostgreSQL.
- [x] Add unit tests for current auth/client/fetch/config/logging/load helpers.

## Phase 1 — Repository baseline and reproducibility

Goal: make the current codebase clean and predictable before adding features.

- [x] **1.1 Expand `.gitignore`.** Ignore Python caches, pytest caches, dbt targets/logs/packages, raw local data, IDE/OS artifacts, and `docs/portfolio/`. Do not remove tracked files automatically; report any already tracked generated files.
- [x] **1.2 Clean dependency/setup documentation.** Confirm supported Python version and document virtual environment + dependency installation.
- [x] **1.3 Add developer commands to README.** Document configuration, tests, a limited ingestion smoke run, and dbt commands that are valid at the current project state.
- [x] **1.4 Run and repair the existing test suite.** Do not change behavior unless a failing test reveals a real defect.

**Exit criterion:** a fresh local environment can install dependencies and run the existing unit tests from documented instructions.

Verified September 25, 2026 with a fresh Python 3.11.0 environment: installation and `pip check` succeeded; all 15 tests passed, including in a source copy without `.env`; CLI help and dbt parsing passed. No pipeline/test repairs were needed. Already tracked artifacts are listed in `CURRENT_STATE.md` and were not removed. Live ingestion/database checks were not part of this offline validation.

## Phase 2 — Generalize raw ingestion

Goal: turn the games proof-of-concept into a reusable multi-entity ingestion layer without over-engineering it.

- [x] **2.1 Introduce a reusable paginated fetch helper.** Preserve entity-specific query builders where they improve clarity.
- [x] **2.2 Move raw database DDL/loading out of the CLI entrypoint.** Create a storage module responsible for connections, table creation, and upserts.
- [x] **2.3 Define entity configuration/contracts.** Capture endpoint, fields, raw table name, primary key, and relevant update field in a simple structure.
- [x] **2.4 Add ingestion run metadata.** Create an `ingestion_runs` table and helpers for start/success/failure records.
- [x] **2.5 Refactor the CLI to use reusable ingestion/storage components.** Preserve current games behavior and tests.
- [x] **2.6 Add tests for the generalized path.** Cover pagination termination, empty results, upsert preparation, and run metadata state changes.

**Exit criterion:** games ingestion still works, but the core path can support another entity without copying the entire pipeline.

Task 2.1 verified September 25, 2026: games delegates to a reusable endpoint/query-callback pagination helper; the games query builder and public fetch behavior are preserved. All 16 focused pagination/games tests and all 28 Python tests passed, along with CLI help. Validation used fakes, with no live API/database calls.

Task 2.2 verified September 25, 2026: database connection creation, raw-games DDL, and upserts now live in `src/storage/raw_games.py`; the CLI imports these helpers with its flow unchanged. Schema, SQL, payload preparation, and separate DDL/load commits are preserved. All 30 focused storage/CLI/games/pagination tests and all 40 Python tests passed, along with CLI help. Validation used fakes, with no live API/database calls.

Task 2.3 verified September 25, 2026: `src/entities.py` defines an immutable entity contract and games configuration consumed by games fetching and storage. Source `id` and raw `igdb_id` are explicit; the existing fields, queries, SQL/schema, CLI flow, and commits are preserved. All 33 focused tests and all 43 Python tests passed, along with CLI help and `git diff --check`. Validation used fakes, with no live API/database calls. At that point, tasks 2.4–2.6 remained open.

Task 2.4 verified September 25, 2026: `src/storage/ingestion_runs.py` provides run-table DDL and committed start/success/failure helpers, integrated with games using separate metadata connections. Raw-games schema, SQL, DDL/load commit boundaries, and fetch/archive behavior remain unchanged. All 67 focused tests and all 77 Python tests passed, along with CLI help and `git diff --check`. Validation used fakes, with no live API/database calls. Transaction gaps, known counts, and best-effort failure reporting are documented. Watermarks remain unused; tasks 2.5–2.6 remain open.

Task 2.5 verified September 25, 2026: the CLI now composes existing games callbacks with `pipeline.ingest_entity()`, a reusable fetch/archive/load and lifecycle runner. Arguments/defaults, queries, archival, raw schema, commit/context ordering, and safe failure reporting are preserved. All 71 focused tests and all 81 unit tests passed on Python 3.11.0; CLI help and `git diff --check` passed. Validation used fakes without live API/database calls. No entities, CLI selection, or incremental behavior were added. Task 2.6 remains open.

Task 2.6 verified September 25, 2026: audited existing coverage and added five composed runner cases using real games/pagination/archive/storage/metadata helpers with fake API/database boundaries. Coverage connects pagination termination and empty results to archives, upsert preparation, and terminal metadata counts, including later-page, invalid-row, and raw context-exit failures. All six runner tests, 76 focused tests, and all 86 unit tests passed on Python 3.11.0. Production behavior and dependencies are unchanged; no live API/database calls were made. Only task 2.6 was newly completed; task 3.1 is next.

## Phase 3 — Expand IGDB source coverage

Goal: ingest the minimum related entities needed for useful relational analytics.

Implement one entity per task, including fetch logic, raw table/load logic, tests, and a small smoke run.

- [x] **3.1 Genres** → `raw_genres`.
- [x] **3.2 Platforms** → `raw_platforms`.
- [x] **3.3 Companies** → `raw_companies`.
- [x] **3.4 Involved companies** → `raw_involved_companies`.
- [x] **3.5 Expand games fields/relationships as required by the analytics model.** Add genre/platform references and other fields only after verifying the actual IGDB payload/query needs.
- [x] **3.6 Add a single CLI entrypoint that can ingest one entity or the configured entity set.**

Task 3.1 implementation/offline validation completed September 25–26, 2026: minimal genres contract, shared-pagination fetch, JSONL archive, and `raw_genres` DDL/upsert callbacks compose with the existing runner. All 30 narrow tests, 98 focused tests, and 108 unit tests passed on Python 3.11.0; games CLI help passed. The initial PostgreSQL blocker was resolved on September 26 with native Apple Silicon PostgreSQL 17.11 and the configured project login/database. Two live five-genre runs passed: archives matched JSONB, repeated loads retained five distinct rows and refreshed timestamps, metadata was succeeded with 5/5 counts, and watermarks remained NULL. The 30 narrow tests and all 108 unit tests passed again. **3.1 is complete.** See [Testing](engineering/TESTING.md#task-31-live-smoke-completion) and the [smoke invocation](pipeline/INGESTION.md#genres-task-31). No later task was started.

Task 3.2 verified September 26, 2026: minimal platforms contract, shared-pagination fetch, JSONL archive, and `raw_platforms` callbacks use the existing runner. All 36 focused tests and 130 unit tests passed on Python 3.11.0; CLI help passed. Two live five-record runs verified source/archive/JSONB fidelity, duplicate-free upserts, refreshed timestamps, durable starts, succeeded 5/5 metadata, and NULL watermarks. PostgreSQL was left stopped and unregistered. **3.2 is complete.** See [Testing](engineering/TESTING.md#task-32-verification). No later task was implemented.

Task 3.3 verified September 26, 2026: minimal companies contract, shared-pagination fetch, JSONL archive, and `raw_companies` callbacks compose with the existing runner. All 42 affected tests and 152 unit tests passed on Python 3.11.0; CLI help passed. Two live five-record runs verified source/archive/JSONB equality, duplicate-free upserts, refreshed timestamp instants, durable starts, succeeded 5/5 metadata, and NULL watermarks. Existing rows were accounted for without clearing tables. PostgreSQL was left stopped and unregistered. **3.3 is complete.** See [Testing](engineering/TESTING.md#task-33-verification). No later task was implemented.

Task 3.4 verified September 26, 2026 (September 27 UTC): involved-companies contract, shared-pagination fetch/archive, and minimal `raw_involved_companies` callbacks preserve the relationship ID, full JSONB, and fetch timestamp. All 48 affected tests and 174 unit tests passed; CLI help passed. Two five-record live runs verified references/roles, source/archive/JSONB fidelity, duplicate-free upserts, timestamp refresh, durable starts, succeeded metadata, and NULL watermarks. PostgreSQL was left stopped and unregistered. **3.4 is complete.** See [Testing](engineering/TESTING.md#task-34-verification). At that point, tasks 3.5 onward remained unimplemented.

Task 3.5 verified September 26, 2026 (September 27 UTC): appended only genre/platform/involved-company record IDs to games, retaining all nine existing fields and the five-column raw schema. All 55 affected tests and 179 offline tests passed; CLI help passed. Two live five-game runs exercised all three relationships and verified source/archive/JSONB fidelity, duplicate-free upserts, timestamp refresh, durable starts, succeeded 5/5 metadata, and NULL watermarks. PostgreSQL was left stopped and unregistered. **3.5 is complete.** See [Testing](engineering/TESTING.md#task-35-verification). At that point, task 3.6 and later work remained unimplemented.

Task 3.6 verified September 26, 2026 (September 27 UTC): the CLI selects one or all five entities with explicit sequential ordering, per-entity fetch limits and archives, and fail-fast behavior retaining earlier commits. Games defaults and established runner/storage semantics are preserved. All 88 focused tests and 196 offline tests passed; CLI help passed. Two actual bounded all-entity CLI runs verified ten archives, complete archive/JSONB fidelity, duplicate-free repeated upserts, refreshed timestamp instants, all three games arrays, succeeded 5/5 metadata per entity, and NULL watermarks. Existing rows were retained; PostgreSQL was stopped and unregistered. **3.6 and Phase 3 are complete.** See [Testing](engineering/TESTING.md#task-36-verification). No later roadmap task was implemented.

**Exit criterion:** PostgreSQL contains the source entities and relationship data required to model games, genres, platforms, and companies.

## Phase 4 — Incremental and idempotent ingestion

Goal: make scheduled reruns efficient and safe.

- [x] **4.1 Define high-water-mark semantics.** Use source `updated_at` where supported; document fallback behavior for small reference entities.
- [x] **4.2 Add persisted watermark lookup from successful ingestion runs.**
- [x] **4.3 Add incremental filters to supported IGDB queries with a small overlap/lookback.**
- [x] **4.4 Ensure overlapping windows are safe through primary-key upserts.**
- [x] **4.5 Advance watermarks only after successful database commits.**
- [x] **4.6 Add tests for first run, incremental run, overlap, no-change run, and failed-run watermark behavior.**
- [x] **4.7 Provide an explicit full-refresh/backfill option.**

Task 4.1 verified September 26, 2026: [accepted watermark semantics](pipeline/WATERMARKS.md) specify timestamp windows for games/companies/involved companies, full reads for genres/platforms, a 24-hour overlap, exclusive committed cutoffs, uncapped eligibility, empty/null/tied timestamp handling, independent entity progress, failure/ambiguous-commit behavior, and future refresh/backfill interaction. Official IGDB references and source-consistency limitations are explicit. Documentation links/examples and whitespace checks passed; unchanged Python 3.11.0 regressions passed (88 focused, 196 total). No runtime/test/dependency/schema change, live ingestion, or database write occurred; PostgreSQL remains stopped/unregistered. **At that point only 4.1 was complete; tasks 4.2–4.7 remained unimplemented.** Current extraction is still unfiltered from offset zero and watermarks remain NULL. See [verification](engineering/TESTING.md#task-41-design-verification).

Task 4.2 verified September 27, 2026: added only a reusable read-only metadata lookup, focused offline tests, and documentation. `get_source_watermark()` returns the greatest successful non-NULL end for the requested schema/entity, ignores completion order, and propagates all lookup failures. All 41 metadata tests and 217 offline tests passed on Python 3.11.0. PostgreSQL remained stopped/unregistered. **At that point only 4.2 was newly complete; tasks 4.3–4.7 remained unchecked.** Ingestion does not call the helper: extraction stays unfiltered from offset zero and watermarks remain NULL. See [verification](engineering/TESTING.md#task-42-lookup-verification).

Task 4.3 verified September 27, 2026: added pure explicit-time window calculation, frozen bounds, and optional timestamp filters for games/companies/involved companies. Bootstrap and reference reads remain unfiltered; custom projections, payloads, ID sorting, pagination, counts, schemas, and transactions are preserved. All 144 affected tests and 315 offline tests passed on Python 3.11.0. PostgreSQL remained stopped/unregistered; no live ingestion or database validation occurred. **At that point only 4.3 was newly complete; tasks 4.4–4.7 remained unchecked.** CLI/shared-runner ingestion performs no lookup or window calculation/application, default extraction remains unfiltered from offset zero, and watermarks remain NULL. See [verification](engineering/TESTING.md#task-43-window-verification).

Task 4.4 verified September 27, 2026: existing games/companies/involved-companies loaders already prepare primary-key upserts for overlapping extractions. Added 18 offline cases covering replay identity, timestamp ties, changed/stale responses, input-order payload fidelity, acknowledged counts, and commit calls; no production change was needed. All 138 affected tests and 333 offline tests passed on Python 3.11.0. PostgreSQL remained stopped/unregistered. Assertions cover SQL/parameters, not live constraint enforcement, rollback, durability, or source completeness. Later stale responses can overwrite newer payloads. **Only 4.4 is newly complete; tasks 4.5–4.7 remain unchecked.** Runtime incremental ingestion remains inactive with NULL watermarks. See [verification](engineering/TESTING.md#task-44-overlap-upsert-verification).

Task 4.5 verified September 28, 2026: the normal CLI path now reads each incremental entity's durable end, captures one fixed cutoff, applies an unfiltered bootstrap or frozen overlap window, records the actual lower bound, and commits an eligible end atomically with guarded success after raw context exit. Explicit selection/default-field/cap context prevents arbitrary callbacks, custom projections, and every supplied cap from publishing progress. Returned timestamp/count gates preserve payloads and may leave a successful run with NULL end. Empty uncapped success may advance without an empty-upsert commit. Focused affected tests: 147 passed; full offline suite: 371 passed on Python 3.11.0. PostgreSQL remained stopped/unregistered; no live validation occurred. **Only 4.5 is newly complete; tasks 4.6–4.7 remain unchecked.** See [verification](engineering/TESTING.md#task-45-runtime-checkpoint-verification).

Task 4.6 verified September 28, 2026: an audit found most gates already covered by task 4.5 and earlier tests. Nine focused offline cases add a consecutive bootstrap/overlap/no-change sequence, runtime UTC conversion and epoch clamp, source/archive/raw failure counts and safe reporting, all-mode eligible-success retention on a later failure, and retry from prior progress after raw context failure. The affected suite passed 254 tests and the full offline suite passed 380 on Python 3.11.0. No production code changed; PostgreSQL remained stopped/unregistered. **Only 4.6 is newly complete; task 4.7 remains unchecked.** See [verification](engineering/TESTING.md#task-46-incremental-test-verification).

Task 4.7 verified September 28, 2026: explicit `--full-refresh` reads unfiltered and can publish a newer eligible cutoff for incremental entities; paired whole-second UTC `--backfill-start`/`--backfill-end` select a frozen interval for every entity and never publish progress. Parsing rejects invalid combinations before source/database work. Normal reruns retain prior eligible progress, raw upserts do not delete rows, and all mode applies the chosen policy independently. The affected suite passed 189 tests and the full offline suite passed 410 on Python 3.11.0. PostgreSQL remained stopped/unregistered; verification was offline only. **Only 4.7 is newly complete.** See [verification](engineering/TESTING.md#task-47-refresh-and-backfill-verification).

**Exit criterion:** normal reruns fetch changed records where supported, do not duplicate rows, and retain auditable run state.

## Phase 5 — dbt sources and staging

Goal: establish the analytics transformation contract.

- [x] **5.1 Decide and implement final raw/dbt schema naming.** Update Python configuration and dbt profile consistently.
- [x] **5.2 Declare raw tables as dbt sources.** Add descriptions and source-level tests where appropriate.
- [x] **5.3 Build `stg_games`.** Extract/cast the fields required downstream.
- [x] **5.4 Build `stg_genres`.**
- [x] **5.5 Build `stg_platforms`.**
- [x] **5.6 Build `stg_companies`.**
- [x] **5.7 Build `stg_involved_companies`.**
- [x] **5.8 Add dbt tests.** At minimum, test primary identifiers for uniqueness/not-null and relationship keys where valid.
- [x] **5.9 Add model/column documentation and verify `dbt build`.**

**Exit criterion:** `dbt build` creates documented, tested staging models from raw tables.

Task 5.1 verified September 28, 2026: new installations default Python-owned raw tables and `ingestion_runs` to `raw` via `POSTGRES_RAW_SCHEMA`, while dbt output defaults to `analytics` via independent `DBT_SCHEMA`. Python retains `POSTGRES_SCHEMA` only as a fallback for existing installations. Focused and full offline tests passed (103 and 412); dbt parsing passed without a database connection. No data was moved, and existing `analytics` installations require an explicit transition to adopt `raw`. Only 5.1 is newly complete; sources and models remain future tasks. See [schema transition](engineering/LOCAL_DEVELOPMENT.md#schema-names-and-existing-analytics-installations) and [verification](engineering/TESTING.md#task-51-schema-naming-verification).

Task 5.2 verified September 28, 2026: all five raw entity tables are declared as `igdb` sources in `POSTGRES_RAW_SCHEMA`, with descriptions and `unique`/`not_null` source tests on each raw `igdb_id`. Offline focused/full tests passed (7 and 413); dbt discovered five sources and ten tests, and parsed both `raw` and `analytics` source-schema configurations without PostgreSQL. No freshness threshold, `ingestion_runs` source, model, migration, or data movement was added. Existing `analytics` installations must export `POSTGRES_RAW_SCHEMA=analytics` for dbt until deliberately migrated. Only 5.2 is newly complete; source tests have not run against the database. See [verification](engineering/TESTING.md#task-52-dbt-source-verification).

Task 5.3 verified September 28, 2026: `stg_games` selects `igdb.raw_games` at one game per raw key, types release/update timestamps, ratings and counts, and carries relationship ID arrays as JSONB. The focused/full offline suites passed (19 and 415), and dbt parsed/discovered the sole staging view without PostgreSQL. Only 5.3 is newly complete; the view and dbt tests have not run against a database. See the [column contract](pipeline/DBT_TRANSFORMATIONS.md#stg_games-task-53) and [verification](engineering/TESTING.md#task-53-games-staging-verification).

**September 29 reassessment follow-up (4.5–5.3):** retained the implementation, aligned dbt source-schema fallback with Python, corrected the view-cast validation claim, and added 21 opt-in PostgreSQL/dbt integration cases. The full default suite passed 419 with 21 skipped; the enabled suite passed 440. The existing local configuration now builds `analytics.stg_games`, passes ten source tests, and returns five verified game rows without changing raw data or run history. See [verification](engineering/TESTING.md#tasks-45-through-53-reassessment-fixes). Earlier dated entries describe their original validation. No checkbox changed in that reassessment; task 5.4 followed, and broader model tests/documentation under 5.8–5.9 remain open.

Task 5.4 verified September 29, 2026: added the single-source `stg_genres` view with raw ID/name/slug/fetch time and nullable Unix-seconds source update conversion. Narrow offline tests passed 17; the default suite passed 420 with 27 database cases skipped. The focused dbt/PostgreSQL suite passed 12 and the full enabled suite passed 447, retaining games checks and exercising genre types/values/nulls/grain and invalid reads under three schema configurations. The unchanged local configuration built both views and passed ten source tests; all five stored genres and five games were queried against raw records. No new ingestion was needed. Raw/history hashes matched, temporary schemas were removed, and PostgreSQL was stopped/unregistered. **Only 5.4 is newly complete; 5.5 is next.** See [verification](engineering/TESTING.md#task-54-genres-staging-verification).

Task 5.5 verified September 29, 2026: added the single-source `stg_platforms` view with raw ID/name/slug/fetch time and nullable Unix-seconds source update conversion. Narrow offline checks passed 18; the default suite passed 421 with 33 database cases skipped. Focused dbt/PostgreSQL checks passed 18 and the full enabled suite passed 454, retaining games/genres regressions. The unchanged local configuration built three views, passed ten source tests, and returned five verified platform rows (IDs 3–7) alongside games/genres comparisons. No ingestion was needed; raw/history hashes matched, synthetic schemas were removed, and PostgreSQL was restored to stopped/unregistered. **Only 5.5 is newly complete; 5.6 is next.** See [verification](engineering/TESTING.md#task-55-platforms-staging-verification).

Task 5.6 verified September 29, 2026: added the single-source `stg_companies` view with raw ID/name/slug/fetch time and nullable Unix-seconds source update conversion. Narrow offline checks passed 19; the default suite passed 422 with 39 database cases skipped. Focused dbt/PostgreSQL checks passed 24 and the full enabled suite passed 461, retaining all earlier staging regressions. The unchanged local configuration built four views and passed ten source tests. Five existing companies (IDs 1–5) and all existing game/genre/platform rows matched raw records; no ingestion was needed. Raw/history hashes matched, synthetic schemas were removed, and PostgreSQL was restored to stopped/unregistered. **Only 5.6 is newly complete; 5.7 is next.** See [verification](engineering/TESTING.md#task-56-companies-staging-verification).

Task 5.7 verified September 30, 2026: added the single-source `stg_involved_companies` view at relationship-record grain, with nullable BIGINT references, nullable BOOLEAN roles, source-update TIMESTAMPTZ, and unchanged fetch time. Missing/null values, false roles, and repeated game/company pairs are preserved. Narrow offline checks passed 20; the default suite passed 423 with 45 skipped. Focused dbt/PostgreSQL checks passed 30 and the full enabled suite passed 468, retaining all regressions. The local build created five views and passed ten source tests; every output field for five existing relationships (IDs 2, 6, 7, 8, 9) and the earlier views matched raw records. No ingestion was needed. Raw/history hashes matched, synthetic schemas were removed, and PostgreSQL was restored to stopped/unregistered. **Only 5.7 is newly complete; 5.8 is next.** See [verification](engineering/TESTING.md#task-57-involved-companies-staging-verification).

Task 5.8 verified September 30, 2026: added ten staging identifier `unique`/`not_null` tests, retaining ten source tests. Strict relationship checks are deferred with per-key reasons because independent bounded ingestion does not guarantee referenced entities; nullable references and repeated game/company pairs remain valid. Narrow offline checks passed 12; the default suite passed 424 with 51 skipped. Focused dbt/PostgreSQL checks passed 36 and the full enabled suite passed 475, including deliberate duplicate/NULL staging-output failures and recovery across all three schema configurations. The local build created five views and passed twenty tests; all existing staging values matched raw rows. No ingestion was needed; raw/history hashes matched, synthetic schemas were removed, and PostgreSQL was restored to stopped/unregistered. **Only 5.8 is newly complete; 5.9 remains open.** See [verification](engineering/TESTING.md#task-58-dbt-tests-verification).

Task 5.9 verified September 30, 2026: documented all five staging models and 35 columns from verified contracts, preserving nullable/reference semantics and relationship-test deferrals. Narrow offline checks passed 17; the default suite passed 429 with 51 skipped. Focused PostgreSQL checks passed 36 and the full enabled suite passed 480. Manifest documentation matches actual view columns under all schema modes. The local build created five views and passed twenty tests; all stored staging values matched raw rows. No ingestion was needed; raw/history hashes matched, disposable schemas were removed, and PostgreSQL was restored to stopped/unregistered. **Only 5.9 is newly complete; Phase 5 is complete.** Phase 6 remains unimplemented. See [verification](engineering/TESTING.md#task-59-model-documentation-and-build-verification).

## Phase 6 — Relationships and marts

Goal: create a small analytics model with obvious business value.

- [x] **6.1 Build game ↔ genre relationship model.**
- [x] **6.2 Build game ↔ platform relationship model.**
- [x] **6.3 Build game ↔ company relationship model with developer/publisher roles.**
- [x] **6.4 Build `mart_game_catalog`.** One stable game-centric surface for exploration.
- [x] **6.5 Build release-trend mart.**
- [x] **6.6 Build genre/platform performance mart(s).** Combine only if the resulting grain remains clear.
- [x] **6.7 Build company-output mart if source coverage supports it cleanly.**
- [x] **6.8 Add mart grain/metric documentation and dbt tests.**

**Exit criterion:** marts answer the project's documented use cases without Streamlit performing business transformations.

Task 6.1 verified September 30, 2026: added documented `int_game_genres` at distinct game/genre-pair grain, with absent/null/empty arrays producing no rows and unmatched genre IDs retained. Two required-key tests and a composite-uniqueness test protect the bridge. Narrow offline/new database/staging regression checks passed 15/15/6; the default suite passed 431 with 66 skipped and the enabled suite passed 497. The existing-data build created six views, passed 23 dbt tests, and matched all 11 source-array pairs, including eight unmatched references. No ingestion was needed; raw/history hashes and unrelated files were preserved, disposable schemas were removed, and PostgreSQL was stopped/unregistered. **At that point only 6.1 was newly complete; 6.2 verification follows below.** See [verification](engineering/TESTING.md#task-61-game-genre-relationship-verification).

Task 6.2 verified September 30, 2026: added documented `int_game_platforms` at distinct game/platform-pair grain, following the genre bridge's expansion, duplicate, null, and malformed-input policy. Unmatched IDs are retained without reference-existence tests. Narrow offline/new PostgreSQL checks passed 17/15; the default suite passed 433 with 81 skipped and the full enabled suite passed 514. The existing-data build created seven views, passed 26 dbt tests, and matched all 14 platform pairs, including eight unmatched references. Existing genre/staging coverage, schema precedence, and independent output schemas are preserved. No ingestion was needed; raw/history hashes matched, disposable schemas were removed, and PostgreSQL was stopped/unregistered. **At that point only 6.2 was newly complete; 6.3 verification follows below.** See [verification](engineering/TESTING.md#task-62-game-platform-relationship-verification).

Task 6.3 verified September 30, 2026: added documented `int_game_companies` at involved-company record grain, preserving repeated game/company pairs, nullable/unmatched references, and independent nullable developer/publisher flags. Only the record ID is required and unique. Narrow offline/new PostgreSQL checks passed 18/12; the default suite passed 435 with 93 skipped, and the enabled suite passed 528. The existing-data build created eight views and passed 28 tests; all five company relationships matched raw and staged records, including three with unmatched references. All eight models and 44 columns are documented. No ingestion was needed; raw/history hashes matched, disposable schemas were removed, and PostgreSQL was stopped/unregistered. **At that point only 6.3 was newly complete; 6.4 verification follows below.** See [verification](engineering/TESTING.md#task-63-game-company-relationship-verification).

Task 6.4 verified September 30, 2026: added the eleven-column `mart_game_catalog` table at exactly one row per staged game, with nullable scalar pass-through and independently aggregated, ordered observed relationship objects. Missing references and company record/role semantics are preserved. Narrow offline/database checks passed 22/33; the default suite passed 438 with 120 skipped, and the enabled suite passed 558. The existing-data build created eight views plus the catalog table and passed 31 dbt tests; all five catalog games and every projected value matched source models. Nine models and 55 columns are documented. No ingestion was needed; raw/history hashes and earlier work were preserved, disposable schemas were removed, and PostgreSQL was stopped/unregistered. **At that point only 6.4 was newly complete; task 6.5 verification follows below.** See [verification](engineering/TESTING.md#task-64-game-catalog-verification).

Task 6.5 verified September 30, 2026: added the two-column `mart_release_trends`
table at observed UTC release-year grain directly over staged games. Counts
exclude NULL dates, omit unobserved years, preserve zero/negative epochs, and
reconcile to all staged games after adding undated games. No relationship fanout,
date cutoff, or later-mart metric was introduced. Narrow offline/database checks
passed 19/45; the default suite passed 441 with 159 skipped, and the full enabled
suite passed 600. Existing-data build: eight views, two tables, 36 dbt tests,
ten models/57 documented columns. Annual counts match staging/catalog exactly:
1998: 2; 2000/2004/2014: 1 each; five dated plus zero undated equals five games.
No ingestion was needed; raw/history hashes and prior work were preserved,
disposable schemas removed, and PostgreSQL stopped/unregistered. **At that point only 6.5 was
newly complete; task 6.6 verification follows below.** See [verification](engineering/TESTING.md#task-65-annual-release-trends-verification).

Task 6.6 verified October 1, 2026: two seven-column performance tables group by
observed genre/platform ID, independently deduplicate pairs, retain unmatched labels,
and report five descriptive metrics with explicit non-NULL contributor counts.
No thresholds, weighting, ranking, forecasting, or company work was added. Narrow
offline/database checks passed 16/27; default suite: 447 passed, 180 skipped;
full enabled: 627 passed. Existing-data build: eight views, four tables, 42 dbt
tests, twelve models/71 documented columns. All four genre/nine platform rows and
every metric match independently derived sources. Deliberate invariant failures,
bridge multiplicities, malformed input and recovery are tested. No ingestion was
needed; earlier work/raw/history were preserved, disposable schemas removed,
and PostgreSQL stopped/unregistered. **At that point only 6.6 was newly complete; task 6.7 verification follows.** See [verification](engineering/TESTING.md#task-66-genreplatform-performance-verification).

Task 6.7 verified October 1, 2026: source contracts and five stored relationships
support a nine-column observed company-output table without ingestion. One row
per observed non-NULL company ID retains unloaded references, nullable labels,
record/game count distinctions, and independent explicit role evidence. Role
counts may overlap; unknown is not false. Narrow offline/PostgreSQL: 14/45 passed;
full default: 450 passed, 207 skipped; full enabled: 657 passed. Existing-data
build: eight views, five tables, 45 dbt tests, thirteen models/80 columns. All five
company rows and every metric match independent sources. Deliberate invariant
failures and recovery, repeated records/lookups, nullable roles and missing
references are covered. Earlier work and raw/history are preserved; disposable
schemas are removed and PostgreSQL is stopped/unregistered. **Only 6.7 is newly
complete; 6.8 and later remain unchecked.** See [verification](engineering/TESTING.md#task-67-company-output-verification).

Task 6.8 verified October 2, 2026: audited all five mart contracts, documented
shared refresh/denominator semantics and a concise documentation-to-test matrix.
Existing release/performance/company reconciliations and catalog value coverage
were sufficient; one catalog array-container invariant closes the remaining dbt
guard gap, with exact deliberate failures and rebuild recovery. No model SQL or
architecture change. Narrow offline/PostgreSQL: 15/15 passed; full default:
450 passed, 83 skipped; full enabled: 533 passed in 373.86s. Existing-data build:
eight views, five tables, 46 dbt tests; all mart values independently reconciled.
The optimized harness, earlier work, raw/history and private files are preserved;
no ingestion, disposable schemas cleaned, PostgreSQL stopped/unregistered.
**Only 6.8 is newly complete; Phase 6 is complete. Phase 7 and later remain unchecked.**
See [audit and verification](engineering/TESTING.md#task-68-mart-contract-audit-verification).

## Phase 7 — Docker Compose

Goal: make the platform reproducible on a new machine.

- [x] **7.1 Add PostgreSQL service with health check and persistent volume.**
- [x] **7.2 Containerize the Python/dbt runtime or create a shared project image.**
- [x] **7.3 Add Compose configuration and environment wiring without baking secrets into images.**
- [x] **7.4 Add initialization/startup documentation.**
- [x] **7.5 Verify a clean-volume setup can ingest data and run `dbt build`.**

**Exit criterion:** the documented Docker workflow can create the database and run the core pipeline from a clean environment.

Task 7.1 verified October 2, 2026: `compose.yaml` defines only
PostgreSQL 17.11 Bookworm with an external password, TCP health check, loopback
port, and project-scoped named volume. Colima resolved the initial missing-engine
blocker. Health, authenticated SQL, incorrect-password rejection, marker persistence
across container removal/recreation, and stop/start passed. A test-only correction
supplies the password omitted from Psycopg's reconnect DSN. Narrow/default/enabled
results: 1 passed; 450 passed with 83 skipped; 533 passed in 374.61s. All 46 dbt
tests pass under each of the three full-project schema modes. Disposable resources
were removed; native PostgreSQL and Colima are stopped, with prior work/data preserved.
**Only 7.1 is newly complete; 7.2 and later remain unchecked.** See [validation
and procedure](engineering/TESTING.md#task-71-docker-postgresql-validation).

Task 7.2 verified October 2, 2026: `docker/Dockerfile` builds a shared non-root
Python 3.11.16/dbt image from unchanged requirements, with direct command overrides
and external credentials/artifacts. `.dockerignore` and three executable image
checks protect the build context; all eleven layers pass the privacy audit.
Python/dbt versions, CLI help, parsing and `pip check` pass. Container suites:
450 passed / 83 skipped by default; one targeted PostgreSQL case; all 533 enabled
tests in 275.40s, retaining all scenarios and three complete schema modes.
Disposable internal-network PostgreSQL used synthetic fixtures and tmpfs storage;
no IGDB access or real-data pipeline run occurred. Resources were cleaned and
Colima/native PostgreSQL are stopped/unregistered; existing work/data are preserved.
**Only 7.2 is newly complete; 7.3–7.5 and later remain unchecked.** See
[image validation](engineering/TESTING.md#task-72-shared-image-validation).

Task 7.3 verified October 2, 2026: profiled `runtime` reuses the shared image for
on-demand Python/dbt commands, with a health dependency, fixed `postgres:5432`,
an external environment allowlist and unchanged source/output schema semantics.
Ordinary startup runs only PostgreSQL. Named archives/dbt artifacts survive
container replacement and `down`, writable as UID 10001 without host mounts.
Six configuration and three image checks pass, as do versions/help, four offline
schema parses, authentication failures, dependency startup and synthetic storage
export. Default/narrow/enabled suites: 450 passed / 83 skipped; 1 passed;
533 passed in 276.61s. All existing scenarios and three complete schema modes
remain. No IGDB access, live pipeline, bootstrap or native data changes occurred.
Disposable resources are cleaned; Colima/native PostgreSQL are stopped/unregistered
and prior work/data are preserved. **Only 7.3 is newly complete; 7.4–7.5 and later
remain unchecked.** See [Compose validation](engineering/TESTING.md#task-73-compose-runtime-validation).

Task 7.4 verified October 2, 2026: consolidated first-use and subsequent-session
instructions in Local Development, with README/dbt navigation and explicit
initialization ownership, isolated settings, addressing, persistence/export and
restart behavior. CLI help, six offline Compose checks, dbt parsing (13 models,
five sources, 46 tests), 55 narrow tests and 450 default tests with 83 skipped pass;
links, shell syntax, whitespace and preservation checks pass. No service startup,
image build, IGDB access, ingestion or database changes occurred. Existing work,
data and resources are retained; Colima/native PostgreSQL remain stopped/unregistered.
**Only 7.4 is newly complete; the documented clean-volume live sequence remains
task 7.5, which is unchecked.** See [commands and validation limits](engineering/TESTING.md#task-74-startup-documentation-verification).

Task 7.5 verified October 2, 2026: the current image built and new isolated volumes
initialized PostgreSQL, with authenticated runtime access and no application
relations before ingestion. Two bounded all-entity live CLI runs retained five
raw rows per entity, ten archives and ten successful runs with NULL watermark
ends. All thirteen models and 46 dbt tests passed and reconciled to raw data;
rows/history/models and artifacts survived container removal/recreation. Evidence
was exported before task-only cleanup. New checks: five applicable Compose checks,
three image checks, 55 narrow offline, 450 default / 83 skipped, 15 ingestion
integration and 533 enabled tests (273.11s); three synthetic schema modes each
retain all 46 dbt tests. The startup docs now use `dbt debug --connection` to avoid
the slim image's unrelated missing-Git check. Prior work/resources are preserved;
Colima/native PostgreSQL are stopped/unregistered. **Only 7.5 is newly complete;
Phase 7 is complete: its documented clean-environment core-pipeline exit criterion
is satisfied. Phase 8 and later remain unchecked.** The validation is bounded;
full source coverage, uncapped bootstrap and task 10.7's clean-clone run remain
unverified. See [commands and evidence](engineering/TESTING.md#task-75-clean-volume-live-workflow-verification).

## Phase 8 — Airflow orchestration

Goal: demonstrate scheduled, observable pipeline execution.

- [x] **8.1 Add Airflow services/configuration to the local Docker environment.**
- [x] **8.2 Create a DAG that invokes the existing ingestion command(s).** Do not duplicate ingestion logic inside the DAG.
- [x] **8.3 Add a dbt build task after successful ingestion.**
- [x] **8.4 Configure dependencies, retries, and failure behavior.**
- [ ] **8.5 Make schedule/start-date/catchup behavior explicit and documented.**
- [ ] **8.6 Verify an end-to-end DAG run from ingestion through dbt tests.**

**Exit criterion:** Airflow can run the complete data pipeline with visible task-level status and logs.

Task 8.1 verified October 3, 2026: opt-in Airflow 3.3.2/Python 3.11 infrastructure
uses LocalExecutor, separate persistent PostgreSQL metadata, explicit repeatable
initialization, local authentication, loopback API/UI and service health checks.
Credentials/keys and a synthetic metadata marker survive container replacement.
PostgreSQL-only startup and existing tools commands still work without Airflow
credentials. New checks: nine initialization tests, eight Compose checks, three
image checks, 459 host tests / 83 skipped, 15 synthetic ingestion integration tests
and 533 enabled application tests. No source access, DAG or pipeline execution.
The unchanged 2 GiB Colima VM passed idle checks; at least 4 GB remains Airflow's
recommended baseline and future workload capacity is unverified. Evidence exported,
task resources removed, existing work/data/resources/index preserved, Colima/native
PostgreSQL stopped/unregistered. **Only 8.1 is newly complete; 8.2–8.6 and this
phase's exit criterion remain incomplete.** See [validation](engineering/TESTING.md#task-81-local-airflow-infrastructure-verification).

Task 8.2 verified October 3, 2026: one manual `igdb_ingestion` DAG invokes
`--entity all` with the isolated application interpreter inside LocalExecutor.
Only the scheduler receives ingestion settings and a separate persistent archive
volume. Synthetic success/failure runs, actual DAG import, dependency isolation,
non-root permissions, authentication/health/persistence and standalone tools checks
pass. New suites: 11 narrow tests, nine Compose checks, two Airflow image checks,
three tools image checks, 461 default tests / 83 skipped, 15 ingestion integration
tests and 533 enabled application tests. No live source access. Evidence exported,
task resources removed, prior work/data/index/resources preserved, services stopped.
**Only 8.2 is newly complete; 8.3–8.6 and the Phase 8 exit criterion remain incomplete.**
See [validation](engineering/TESTING.md#task-82-ingestion-dag-verification).

Task 8.3 verified October 3, 2026: the manual DAG now runs `ingest_all` →
`dbt_build` using the existing project and isolated application executables.
Only the scheduler receives dbt settings and a separate UID-50000 artifact volume.
Synthetic LocalExecutor success, upstream ingestion failure, dbt test failure and
recovery pass; successful builds retain 13 models/46 tests. Three source-schema
modes, independent outputs, artifact/data persistence, initialization/auth/health
and tools regressions pass. New checks: 11 narrow, nine Compose, three Airflow
image, three tools image, 461 host / 83 skipped, 15 ingestion integration and
533 enabled application tests. No live source access; real workload capacity is
unverified. Evidence exported, task resources removed, prior work/data/index and
Docker inventories preserved; Colima/native PostgreSQL stopped/unregistered.
**Only 8.3 is newly complete; 8.4–8.6 and Phase 8's exit criterion remain incomplete.**
See [synthetic validation](engineering/TESTING.md#task-83-dbt-task-verification).

Task 8.4 verified October 3, 2026: both existing command tasks explicitly use
`all_success` and one whole-command retry after a fixed one-minute delay. Actual
LocalExecutor automatic recovery/exhaustion passed for ingestion and dbt, with
correct attempt counts, 60-second minimum waits, downstream blocking, final DAG
states and visible per-attempt logs. Repeated ingestion retained earlier commits,
idempotent raw keys and per-entity history/checkpoints; successful dbt builds
retained 13 models/46 tests and expected synthetic values. New results: 11 narrow,
461 host / 83 skipped, nine Compose, three Airflow image, three tools image,
15 ingestion integration and 533 enabled application passes. Isolation, auth,
health, persistence and tools regressions passed. Evidence exported, task resources
removed, baseline preserved and services stopped/unregistered. No live-source
validation or real workload capacity claim. **Only 8.4 is newly complete;
8.5–8.6 and Phase 8's exit criterion remain incomplete.** See
[synthetic retry validation](engineering/TESTING.md#task-84-dependency-retry-and-failure-verification).

## Phase 9 — Streamlit consumption layer

Goal: prove the marts are usable without turning the project into a frontend project.

- [ ] **9.1 Add a shared read-only database/query helper for the app.**
- [ ] **9.2 Add release-trend view.**
- [ ] **9.3 Add genre/platform comparison view.**
- [ ] **9.4 Add company-output view if that mart was retained.**
- [ ] **9.5 Add game explorer/filter view.**
- [ ] **9.6 Add Streamlit to the documented local/Docker workflow.**

**Exit criterion:** the app reads only curated dbt outputs and demonstrates several meaningful questions supported by the pipeline.

## Phase 10 — CI, data quality, and final polish

- [ ] **10.1 Add CI for Python tests.**
- [ ] **10.2 Add lint/format tooling only if it can be kept simple and deterministic.**
- [ ] **10.3 Add a dbt validation job where a suitable test database strategy is available.**
- [ ] **10.4 Add/verify operational data-quality checks described in `engineering/DATA_QUALITY.md`.**
- [ ] **10.5 Add a public architecture diagram and representative screenshots to README.**
- [ ] **10.6 Verify no secrets, local data, caches, private portfolio notes, or generated artifacts are tracked.**
- [ ] **10.7 Perform a clean-clone run using only README instructions.**
- [ ] **10.8 Update `CURRENT_STATE.md` to mark the completed architecture accurately.**

**Exit criterion:** repository is clean, reproducible, documented, tested, and ready to share.

## Phase 11 — Optional extensions

Only consider these after Phase 10.

- [ ] LLM summaries over curated query results.
- [ ] dbt source freshness checks if source semantics support meaningful thresholds.
- [ ] richer observability/metrics.
- [ ] cloud deployment.

These are enhancements, not requirements for the core project.

## How to work through this roadmap with Codex

For each task:

1. ask Codex to read `AGENTS.md`, `docs/CURRENT_STATE.md`, `docs/ARCHITECTURE.md`, and this roadmap;
2. specify exactly one unchecked task ID;
3. require tests/documentation relevant to that task;
4. review the diff and run the stated verification commands;
5. update the task checkbox and `CURRENT_STATE.md` only after the implementation is actually verified.

Do not ask Codex to implement an entire phase in one prompt.
