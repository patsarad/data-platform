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

- [ ] **5.1 Decide and implement final raw/dbt schema naming.** Update Python configuration and dbt profile consistently.
- [ ] **5.2 Declare raw tables as dbt sources.** Add descriptions and source-level tests where appropriate.
- [ ] **5.3 Build `stg_games`.** Extract/cast the fields required downstream.
- [ ] **5.4 Build `stg_genres`.**
- [ ] **5.5 Build `stg_platforms`.**
- [ ] **5.6 Build `stg_companies`.**
- [ ] **5.7 Build `stg_involved_companies`.**
- [ ] **5.8 Add dbt tests.** At minimum, test primary identifiers for uniqueness/not-null and relationship keys where valid.
- [ ] **5.9 Add model/column documentation and verify `dbt build`.**

**Exit criterion:** `dbt build` creates documented, tested staging models from raw tables.

## Phase 6 — Relationships and marts

Goal: create a small analytics model with obvious business value.

- [ ] **6.1 Build game ↔ genre relationship model.**
- [ ] **6.2 Build game ↔ platform relationship model.**
- [ ] **6.3 Build game ↔ company relationship model with developer/publisher roles.**
- [ ] **6.4 Build `mart_game_catalog`.** One stable game-centric surface for exploration.
- [ ] **6.5 Build release-trend mart.**
- [ ] **6.6 Build genre/platform performance mart(s).** Combine only if the resulting grain remains clear.
- [ ] **6.7 Build company-output mart if source coverage supports it cleanly.**
- [ ] **6.8 Add mart grain/metric documentation and dbt tests.**

**Exit criterion:** marts answer the project's documented use cases without Streamlit performing business transformations.

## Phase 7 — Docker Compose

Goal: make the platform reproducible on a new machine.

- [ ] **7.1 Add PostgreSQL service with health check and persistent volume.**
- [ ] **7.2 Containerize the Python/dbt runtime or create a shared project image.**
- [ ] **7.3 Add Compose configuration and environment wiring without baking secrets into images.**
- [ ] **7.4 Add initialization/startup documentation.**
- [ ] **7.5 Verify a clean-volume setup can ingest data and run `dbt build`.**

**Exit criterion:** the documented Docker workflow can create the database and run the core pipeline from a clean environment.

## Phase 8 — Airflow orchestration

Goal: demonstrate scheduled, observable pipeline execution.

- [ ] **8.1 Add Airflow services/configuration to the local Docker environment.**
- [ ] **8.2 Create a DAG that invokes the existing ingestion command(s).** Do not duplicate ingestion logic inside the DAG.
- [ ] **8.3 Add a dbt build task after successful ingestion.**
- [ ] **8.4 Configure dependencies, retries, and failure behavior.**
- [ ] **8.5 Make schedule/start-date/catchup behavior explicit and documented.**
- [ ] **8.6 Verify an end-to-end DAG run from ingestion through dbt tests.**

**Exit criterion:** Airflow can run the complete data pipeline with visible task-level status and logs.

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
