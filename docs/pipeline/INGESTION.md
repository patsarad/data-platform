# Ingestion

## Responsibility

The ingestion layer moves source records from IGDB into the raw boundary. It owns authentication, API interaction, pagination, incremental selection, retries, raw archival, and handoff to PostgreSQL storage.

It does not own analytics transformations.

## Current implementation

Current modules:

```text
src/entities.py
src/ingestion/auth.py
src/ingestion/client.py
src/ingestion/pagination.py
src/ingestion/windows.py
src/ingestion/fetch_games.py
src/ingestion/fetch_genres.py
src/ingestion/fetch_platforms.py
src/ingestion/fetch_companies.py
src/ingestion/fetch_involved_companies.py
src/ingestion/pipeline.py
src/ingestion/run_ingestion.py
```

The CLI authenticates through Twitch, fetches the selected entities in offset-based batches, writes separate JSONL archives, and upserts records into PostgreSQL. All five entities use their established callbacks through the shared runner. Two bounded `--entity all` CLI runs passed on September 26, 2026 (September 27 UTC).

The CLI retains argument parsing, output-path selection, and start/finish logging. It calls `pipeline.ingest_entity()` once per selected entity with its contract, configured schema/path, and established fetch/archive/table/upsert callbacks. The callback mapping is explicit and ordered inside `main()`. `functools.partial` binds `batch_size` and `max_batches` to the fetcher; no new query builder or loader is introduced. See [Raw storage](RAW_STORAGE.md) for the preserved schema and transaction boundaries.

The runner is callable without CLI parsing. `fetch_records(client)` returns the complete list; `archive_records(records, output_path)` writes it; `ensure_table(connection, schema_name)` and `upsert_records(connection, records, schema_name, fetched_at)` retain storage-owned commits. The runner owns client creation, the UTC load timestamp, connection contexts, and metadata transitions, and returns `(records_fetched, records_loaded)` only after success. It uses the connection factory still owned by `raw_games.py`. The caller supplies the logger, preserving existing CLI lifecycle log messages.

Lifecycle helpers live in `src/storage/ingestion_runs.py`. Before creating the source client, the runner creates the metadata table if needed and commits a `running` record for the supplied entity endpoint (the selected entity in the CLI). That connection closes before fetching. Fetching, JSONL archival, and the raw-load connection then run in their existing order. After the raw context exits, a fresh connection records `succeeded`. Empty results still write an empty archive and ensure that entity’s raw table exists, skip the upsert commit, and finish with zero counts. Existing CLI arguments/defaults are unchanged; `--entity` is additive.

## CLI entity selection (task 3.6)

```bash
# Existing invocation: games, batch size 500, no batch cap unless supplied.
python -m src.ingestion.run_ingestion --max-batches 1
# Override an archive for one entity.
python -m src.ingestion.run_ingestion --entity genres --batch-size 5 --max-batches 1 --output-path data/raw/genres_sample.jsonl
# Five independent bounded entity runs.
python -m src.ingestion.run_ingestion --entity all --batch-size 5 --max-batches 1
```

`--entity` accepts `games` (default), `genres`, `platforms`, `companies`, `involved_companies`, or `all`. `all` runs exactly once per entity, sequentially in this deterministic order: **games → genres → platforms → companies → involved_companies**. This is a code-owned configuration, with no dynamic discovery. The order is operational only; referenced rows need not exist in bounded samples. Involved-company record IDs remain distinct from company IDs.

Existing defaults remain `--batch-size 500`, `--max-batches None`, and `--output-path None`. Batch size and batch cap apply independently to each entity, starting at offset zero. A zero/non-positive batch cap retains the existing empty-run behavior. No filters or custom-field semantics change.

Every entity uses its existing writer with a separate `data/raw/raw_<entity>_YYYYMMDDTHHMMSSZ.jsonl` path generated when its run begins. The default games path and UTC second-resolution format are unchanged. As before, repeated runs of the same entity within one second can reuse a filename; different entities have distinct prefixes. An explicit path overrides the default for a single entity. `--entity all --output-path ...` fails with an argparse ambiguity error (exit 2) before API/database work; invalid entity names also fail at parsing.

Each call to the unchanged runner commits its own durable start, fetches/archives/loads, exits its raw context, and then records success. Counts are acknowledged fetched/loaded counts for that entity, not a cumulative total. **All mode is fail-fast:** any exception propagates immediately, including a completion-metadata failure. Later entities are not started; earlier completed loads, archives, and successful metadata remain intact. There is no all-entity transaction. Best-effort failure reporting and the transaction/count limitations in [Raw storage](RAW_STORAGE.md#transactions) still apply. Watermarks remain NULL.

Two actual bounded CLI runs verified ten separate archives, complete archive/JSONB equality, duplicate-free repeated upserts, refreshed timezone-aware timestamp instants, all three games relationship arrays, and ten successful metadata records with matching 5/5 counts and NULL watermarks. See [Testing](../engineering/TESTING.md#task-36-verification) for commands and coverage limits.

## Authentication

`TwitchTokenManager` uses the client-credentials grant. It caches the access token in memory and refreshes before expiration. A 401 response causes the IGDB client to discard the cached token and retry with a fresh token.

Credentials must come from environment variables and must never be committed.

## Request behavior

`IGDBClient` sends APIcalypse queries as POST bodies and includes:

- `Client-ID`
- `Authorization: Bearer <token>`
- JSON accept header
- text/plain request content type

Transient statuses currently retried include 429 and common 5xx responses. Request exceptions are also retried up to the configured attempt limit.

## Pagination

`pagination.fetch_paginated()` owns the reusable limit/offset loop. It accepts an IGDB client, an endpoint, and a query-building callback that receives `(limit, offset)` as positional arguments. The callback owns fields, filters, and deterministic sorting; the helper does not construct entity-specific queries.

`fetch_games_batches()` delegates to this helper while retaining `build_games_query()` and its existing fields and deterministic `sort id asc`. Existing defaults remain `batch_size=500`, `max_batches=None`, and `DEFAULT_GAME_FIELDS`; task 4.3 adds optional `window=None`. All fetchers materialize iterable field overrides once so projections survive every page.

The helper starts at offset zero, advances by the requested batch size after full pages, and returns all fetched records in page order as a list. Fetching stops after an empty or partial page, or when `max_batches` is reached. A non-positive batch cap returns an empty list without requests, preserving existing games behavior. Client errors propagate; retry/authentication behavior remains in `IGDBClient`. Pagination logs include the endpoint, page number, record count, and offset under the `src.ingestion.pagination` logger.

This extraction keeps the existing in-memory accumulation and does not introduce new argument validation. Callers should supply a positive batch size. Games storage was extracted in task 2.2, the games contract was added in task 2.3, and run metadata was added in task 2.4. Task 2.5 extracts reusable lifecycle orchestration. Task 2.6 adds composed-path tests; tasks 3.1–3.4 add genres, platforms, companies, and involved companies using the same paginator. Task 3.5 appends games relationship IDs through the existing contract; task 3.6 adds CLI entity selection.

## Implemented entity contract

`src/entities.py` provides a frozen `EntityConfig` dataclass and the `GAMES`, `GENRES`, `PLATFORMS`, `COMPANIES`, and `INVOLVED_COMPANIES` configurations. It has no client, database, or environment dependencies.

| Attribute | Games value | Meaning |
|---|---|---|
| `endpoint` | `games` | IGDB endpoint passed to pagination |
| `fields` | Existing nine fields plus `genres`, `platforms`, `involved_companies` | Ordered tuple used for default requests |
| `raw_table` | `raw_games` | Table name without the configured PostgreSQL schema |
| `source_primary_key` | `id` | Payload identifier and deterministic query sort key |
| `raw_primary_key` | `igdb_id` | Destination primary-key column and upsert conflict key |
| `update_field` | `updated_at` | Source update field; may be `None` when not applicable |

`DEFAULT_GAME_FIELDS` remains available from `fetch_games.py` as an alias of `GAMES.fields`. Custom per-call fields remain supported and do not change the shared configuration. Task 3.5 expands only the default requested fields; task 4.3 adds optional `window=` to games/companies/involved-companies query/fetch signatures, preserving pagination defaults/behavior. Custom fields replace the default tuple for that call, with no automatic additions. Raw storage consumes the same table/key contract while retaining games-specific SQL and row preparation.

The update field is descriptive only: it adds no filtering, validation of payload timestamps, raw column, or watermark state. There is no entity registry, generic loader, or CLI entity selector in task 2.3.

## Games relationships (task 3.5)

The [project use cases](../PROJECT_OVERVIEW.md#core-use-cases) and [dbt relationship/mart requirements](DBT_TRANSFORMATIONS.md) require game/genre, game/platform, and developer/publisher company relationships. Existing `first_release_date`, ratings/counts, ID/name/slug, and `updated_at` already support release trends, rating comparisons, catalog identity, and source metadata. Only these three fields are added:

| Field | Official type / target | Analytics need |
|---|---|---|
| `genres` | Array of Genre IDs | Game/genre relationship and genre rating comparisons |
| `platforms` | Array of Platform IDs | Game/platform relationship and platform rating comparisons |
| `involved_companies` | Array of Involved Company record IDs | Link games to relationship records carrying company references and developer/publisher roles |

Verified September 26, 2026 against the official [Game fields](https://api-docs.igdb.com/#game), [Involved Company fields](https://api-docs.igdb.com/#involved-company), and [expander behavior](https://api-docs.igdb.com/#expander). Involved-company IDs are **not company IDs**: the intended future path is `games.involved_companies[] → involved_companies.id → involved_companies.company → companies.id`; `involved_companies.game` references the game, and `developer`/`publisher` are booleans on that relationship record.

The complete default query at the production page size is:

```text
fields id, name, slug, first_release_date, rating, rating_count, total_rating, total_rating_count, updated_at, genres, platforms, involved_companies; sort id asc; limit 500; offset 0;
```

Plain relationship fields request numeric IDs, with no dotted expansions or wildcard fields. No other additions are justified by the documented model: summaries/artwork are not required, and platform-specific release dates or game-type classifications would introduce requirements/endpoints beyond this task. Existing `first_release_date` supports game-level release trends; it does not describe each platform/region release.

`GAMES.fields` supplies the existing `DEFAULT_GAME_FIELDS` alias, query builder, shared paginator, and CLI-to-runner path. Custom field overrides remain exact replacements. Complete fetched objects pass through JSONL and JSONB unchanged, including extra values, source array order, missing keys, empty arrays, and explicit nulls. Python neither fills relationship defaults nor resolves, deduplicates, explodes, or joins IDs. The five-column `raw_games` shape and existing lifecycle/transactions are unchanged. Bounded samples need not contain referenced records.

Two live five-game runs using default fields passed; all five games contained each relationship, so no filtered sample was needed. See [exact verification and bounded fallback query](../engineering/TESTING.md#task-35-verification). No new endpoints, relationship tables, dbt models, CLI options, or watermark behavior were introduced.

## Genres (task 3.1)

Verified against the [official Genre endpoint documentation](https://api-docs.igdb.com/#genre) on September 25, 2026: requests use POST to `https://api.igdb.com/v4/genres`; `name` and `slug` are strings and `updated_at` is the source update datetime. The official [expander examples](https://api-docs.igdb.com/#expander) show the genre `id` alongside those attributes. The minimal requested contract is `("id", "name", "slug", "updated_at")`. Other available fields are not needed for this task.

`build_genres_query()` sorts by `id asc`; `fetch_genres_batches()` delegates to `fetch_paginated()` with defaults `batch_size=500`, `max_batches=None`. Custom field iterables are materialized once for reuse across pages. The fetcher accumulates records in memory. `save_genres_to_jsonl()` creates parent directories and writes every fetched object unchanged as JSONL, including an empty file for no records. Storage requires `id`; missing name/slug become SQL NULL and missing `updated_at` is tolerated. The update field remains in the payload and is not a watermark.

With Python 3.11 activated, valid IGDB credentials, and PostgreSQL ready, request at most five genres through the CLI:

```bash
python -m src.ingestion.run_ingestion --entity genres --batch-size 5 --max-batches 1
```

Inspect the archive and matching database rows for IDs, name/slug, full JSONB, and UTC `fetched_at`; verify the new `genres` metadata row is `succeeded`, counts match, and both watermarks are NULL. Rerun the bounded invocation and check the same source IDs update without duplicate rows. A cap is only a smoke sample, not a claim of full endpoint coverage.

Live smoke validation passed on September 26, 2026 after the local PostgreSQL setup was completed. Two five-record invocations fetched the same IDs, archived matching payloads, and upserted five distinct raw rows with refreshed timestamps. Both metadata rows succeeded with 5/5 counts and NULL watermarks. Task 3.1 is complete; [exact validation details](../engineering/TESTING.md#task-31-live-smoke-completion) retain the initial failed connectivity checks as history.

## Platforms (task 3.2)

Verified September 26, 2026 against the [official Platform endpoint](https://api-docs.igdb.com/#platform) and [ID response behavior](https://api-docs.igdb.com/#technical-related-faq): POST `https://api.igdb.com/v4/platforms` supports the minimal requested contract `("id", "name", "slug", "updated_at")`. Name/slug are strings; `updated_at` describes the source update datetime. Additional platform attributes are outside this task's lookup needs.

`build_platforms_query()` orders by `id asc`. `fetch_platforms_batches()` uses the shared paginator with `batch_size=500`, `max_batches=None`, and offset zero; iterable field overrides are materialized once. `save_platforms_to_jsonl()` preserves complete fetched objects, creates parent directories, and writes an empty archive for no records. Storage requires `id`, tolerates absent name/slug/update time, and retains `updated_at` in JSONB only. Watermarks remain NULL.

With Python 3.11 activated and PostgreSQL ready, use the CLI for a bounded five-record invocation:

```bash
python -m src.ingestion.run_ingestion --entity platforms --batch-size 5 --max-batches 1
```

Repeat and compare source IDs, complete archives/JSONB, extracted fields, refreshed `fetched_at`, and run metadata. Two five-record runs passed on September 26, 2026; the [verification harness and results](../engineering/TESTING.md#task-32-verification) include assertions and service cleanup. Stop PostgreSQL when finished as documented in [Local development](../engineering/LOCAL_DEVELOPMENT.md#local-postgresql-on-apple-silicon). This sample does not imply full endpoint coverage. Task 3.2 is complete.

## Companies (task 3.3)

Verified September 26, 2026 against the [official Company endpoint](https://api-docs.igdb.com/#company) and [ID response behavior](https://api-docs.igdb.com/#technical-related-faq): POST `https://api.igdb.com/v4/companies` supports the minimal requested contract `("id", "name", "slug", "updated_at")`. Name/slug are strings; `updated_at` is the source update datetime. Only `id` is required by the loader; missing optional fields are tolerated. No developed/published game arrays or involved-company relationships are requested.

`build_companies_query()` sorts by `id asc`; `fetch_companies_batches()` delegates to the shared paginator with defaults `batch_size=500`, `max_batches=None`, starting at offset zero. Iterable field overrides are materialized once. `save_companies_to_jsonl()` preserves every fetched object, creates parent directories, and writes an empty archive for no records. Update time stays in JSONB; watermarks remain NULL.

With Python 3.11 activated, credentials configured, and PostgreSQL ready, this CLI command requests at most five companies:

```bash
python -m src.ingestion.run_ingestion --entity companies --batch-size 5 --max-batches 1
```

Two bounded live runs passed: IDs `[1, 2, 3, 4, 5]` matched source/archive/JSONB, repeated upserts retained five distinct rows and refreshed timestamps, and both metadata records succeeded with 5/5 counts and NULL watermarks. The [verification harness](../engineering/TESTING.md#task-33-verification) accounts for existing rows and verifies durable starts before source fetching. PostgreSQL was stopped and unregistered afterward; follow [local service instructions](../engineering/LOCAL_DEVELOPMENT.md#local-postgresql-on-apple-silicon). Task 3.3 is complete; full endpoint coverage and failure rollback remain outside this smoke sample.

## Involved companies (task 3.4)

Verified September 26, 2026 against the [official Involved Company endpoint](https://api-docs.igdb.com/#involved-company): POST `https://api.igdb.com/v4/involved_companies` supports game/company reference IDs, developer/publisher booleans, and `updated_at` as a source update datetime. The minimal requested contract is `("id", "game", "company", "developer", "publisher", "updated_at")`. The record ID is distinct from either reference and is the upsert key. No name/slug or expanded references are requested. Porting/supporting roles are outside the default field set; any extra fetched attributes are still retained unchanged.

`INVOLVED_COMPANIES.update_field="updated_at"` is descriptive only. `build_involved_companies_query()` sorts by `id asc`; `fetch_involved_companies_batches()` uses shared pagination with `batch_size=500`, `max_batches=None`, offset zero, and iterable field overrides materialized once. `save_involved_companies_to_jsonl()` writes complete objects and handles empty results like the existing entities. Storage requires only `id`: absent fields, explicit nulls, and false role values are preserved without defaulting or coercion. References, roles, and source update time remain inside JSONB for later dbt extraction. No foreign keys or checks against bounded games/companies samples are imposed.

Use the CLI for a five-record smoke sample with Python 3.11, configured credentials, and PostgreSQL ready:

```bash
python -m src.ingestion.run_ingestion --entity involved_companies --batch-size 5 --max-batches 1
```

Two bounded live runs passed for IDs `[2, 6, 7, 8, 9]`, verifying source/archive/JSONB fidelity, reference IDs, role values, duplicate-free upserts, timestamp refresh, durable starts, succeeded 5/5 metadata, and NULL watermarks. See the [repeatable harness and exact results](../engineering/TESTING.md#task-34-verification). PostgreSQL was stopped and unregistered afterward. Task 3.4 is complete; games expansion is documented above and task 3.6 adds CLI entity selection.

## Entity scope

Target source entities:

| Entity | Purpose |
|---|---|
| games | Core facts, ratings, release/update timestamps, relationship IDs |
| genres | Genre lookup attributes |
| platforms | Platform lookup attributes |
| companies | Company lookup attributes |
| involved_companies | Game/company relationships and developer/publisher roles |

Do not add more endpoints until a concrete mart/use case requires them.

## Incremental behavior

**Task 4.5 activates normal CLI incremental extraction.** The [watermark contract](WATERMARKS.md) defines source evidence, bounds, eligibility, failures, and remaining responsibilities. `calculate_source_window(watermark, *, run_started_at)` takes explicit aware datetimes and returns a frozen `SourceWindow(lower_bound, upper_bound)`. The CLI supplies explicit run selection; the runner looks up each incremental entity's greatest eligible end after metadata DDL and captures one run-start cutoff before source requests. With W, it computes `L=max(0, W-86400)` and rejects `U <= W`. Every page emits `updated_at >= L & updated_at < U`, with unchanged `sort id asc` and offset-zero pagination. Without W, bootstrap emits no filter, including no upper-only filter.

Omitted windows preserve exact query output. Custom fields remain exact replacements across pages, including iterators; `updated_at` is never appended. Fetchers return every supplied record unchanged, even when timestamps are tied, missing, null, malformed, or outside the requested window. The runner checks returned timestamps only for checkpoint eligibility, without changing payloads. Genres/platforms remain unfiltered with NULL bounds on normal and full-refresh runs; their optional `window=` is used for explicit backfills. See the [API example and input validation](WATERMARKS.md#optional-window-api-task-43).

The CLI's `RunSelection` declares page size, cap, and default-field use. The runner additionally verifies the canonical fetcher and exact bound options before publishing progress. A direct arbitrary callback without selection context still archives/loads but cannot checkpoint. Explicit custom fields cannot checkpoint, including an override equal to the defaults. Every supplied `--max-batches` value, even zero, negative, or apparently exhausted, withholds progress. A bounded run with prior W still uses its frozen window; its end remains NULL. Task 4.4 verified [existing upsert preparation for overlap replay](RAW_STORAGE.md#overlapping-window-preparation-task-44) offline. No flags, metadata/raw schemas, count meaning, archival/loading order, or transaction boundaries changed.

Eligible uncapped normal and full-refresh runs require a page size of 1–500, normal pagination return, archive and acknowledged load counts equal to fetched rows, and every returned `updated_at` to be a nonnegative JSON integer (not a boolean), UTC-convertible, and no later than fetch completion. Windowed normal responses must also satisfy `L <= updated_at < U`. Empty uncapped runs may advance after the empty archive and raw DDL/context lifecycle; no empty-upsert commit is added. Missing/null/invalid timestamps leave a successful run with NULL end and a fixed safe warning while preserving every payload. Explicit backfills always leave end NULL.

## Explicit refresh and backfill (task 4.7)

```bash
python -m src.ingestion.run_ingestion --entity companies --full-refresh
python -m src.ingestion.run_ingestion --entity companies --backfill-start 2026-09-01T00:00:00Z --backfill-end 2026-09-02T00:00:00Z
python -m src.ingestion.run_ingestion --entity all --backfill-start 2026-09-01T00:00:00Z --backfill-end 2026-09-02T00:00:00Z
```

`--full-refresh` reads the selected endpoint(s) unfiltered from offset zero and upserts returned rows without removing existing raw rows. Incremental entities record a NULL start and may publish their fixed cutoff only after the normal eligibility gates and a cutoff beyond any prior watermark. Reference entities keep both bounds NULL. `--backfill-start` and `--backfill-end` require exact whole-second UTC `YYYY-MM-DDTHH:MM:SSZ` values with start before end. They filter every page of each selected entity to the inclusive/exclusive interval, record the start, and never publish an end. Normal progress remains the greatest earlier eligible end, or bootstrap if none exists. All mode applies the selected mode per entity in its usual order. Caps retain their per-entity behavior. The flags are mutually exclusive, and malformed/incomplete intervals fail during parsing before settings, source, or database work. See [watermark semantics](WATERMARKS.md#full-refresh-and-backfill-task-47) for failure and completeness limits.

## Raw archival

JSONL files are useful for debugging and demonstrating the exact fetched payload, but they are local artifacts rather than repository content. Store them under an ignored `data/raw/` path.

## Error handling

- A metadata setup/start failure propagates before source work; a run row is not guaranteed in that case.
- Once the start is committed, ordinary exceptions from client creation/fetching, archival, raw loading, or success recording trigger a failed-run update on a fresh connection. Any failed database context exits before failure reporting begins.
- Failure reporting is best-effort: its own error is logged and the original exception is re-raised. New metadata/log messages use fixed stage summaries, not raw exception text, connection details, or source payloads.
- Success-record failure also fails the command, even when raw data already committed; failure reporting retains the known loaded count. Abrupt interruption/process death can leave the run `running`.
- Authentication failures should raise a domain-specific error.
- Transient HTTP errors should retry with bounded backoff.
- Permanent failures should surface clearly and fail the pipeline.
- Database failures should not be swallowed.
- Error logs must not include client secrets or bearer tokens.

## Verification expectations

`tests/test_pipeline.py` composes the real games, genres, platforms, companies, and involved-companies fetchers/pagination, JSONL writers, raw loaders, and metadata helpers with fake API/database boundaries. It checks empty/full-page termination through archive and load, repeated-ID processed-row counts, a later-page failure with zero acknowledged counts, invalid-row preparation with a retained archive, and raw context-exit failure with an acknowledged loaded count. Existing helper and CLI tests retain detailed stopping-rule, SQL, and lifecycle coverage. See [Testing](../engineering/TESTING.md) for the audits and commands. These checks do not establish live PostgreSQL transaction behavior.

Each entity implementation should include unit tests for query construction/fetch behavior and storage preparation. Live API smoke tests should remain manual or explicitly separated from unit tests so normal test runs do not require credentials or network access.
