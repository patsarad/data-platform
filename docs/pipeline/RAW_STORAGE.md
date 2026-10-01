# Raw Storage

## Purpose

The raw PostgreSQL layer is the durable boundary between source ingestion and analytics transformation. It should preserve source fidelity while giving the pipeline stable identifiers and ingestion metadata.

## Current state

`src/storage/raw_games.py` owns PostgreSQL connection creation, raw-games DDL, and upserts. `run_ingestion.py` supplies its table/upsert helpers to `pipeline.ingest_entity()`, which imports the connection factory and coordinates connection contexts. The table is `<POSTGRES_RAW_SCHEMA>.raw_games`, defaulting to `raw.raw_games`. Its columns are:

```text
igdb_id BIGINT PRIMARY KEY
name TEXT
slug TEXT
payload JSONB NOT NULL
fetched_at TIMESTAMPTZ NOT NULL
```

Writes use `ON CONFLICT (igdb_id) DO UPDATE`, so repeated game loads update the existing source record instead of inserting duplicates.

The module exposes:

- `create_connection()` — passes the existing environment-backed host, port, database, user, and password to psycopg, retaining driver defaults;
- `ensure_raw_games_table(connection, schema_name)` — creates the configured schema and the unchanged `raw_games` table if absent, then commits;
- `upsert_raw_games(connection, games, schema_name, fetched_at)` — accepts an iterable, prepares rows with the required source `id`, optional name/slug, complete `Jsonb` payload, and caller-supplied timestamp, then executes the upsert and commits. It returns the prepared row count; empty input returns zero without opening a cursor or committing.

Task 2.3 adds the shared `GAMES` contract from `src/entities.py`. The games helpers use its `raw_table`, `source_primary_key`, and `raw_primary_key` for table references, payload lookup, DDL, and conflict SQL. These are code-owned names; the schema still comes from the existing settings. The mapping remains source `id` → raw `igdb_id`, with no changes to SQL output, helper signatures, row preparation, or commit boundaries.

The contract's `update_field="updated_at"` only describes the source field. It remains inside `payload`, is not required on each fetched object, and adds no extracted column or incremental behavior. Task 2.4 adds operational metadata in `src/storage/ingestion_runs.py`, described below. Tasks 3.1–3.4 add genres, platforms, companies, and involved companies. No generic loader or raw-games schema migration was introduced.

### Games relationships (task 3.5)

Games now request `genres`, `platforms`, and `involved_companies` IDs in addition to the existing fields. They live only in complete JSONB `payload` and the JSONL archive; no columns or tables were added. Involved-company references identify relationship records, whose payloads carry company IDs and role flags. Missing keys, empty arrays, explicit nulls, source order, and extra fetched fields are retained unchanged. No foreign keys or reference-existence checks are imposed on bounded samples. dbt will own extraction and joins.

Two bounded games runs verified all three arrays, source/archive/JSONB fidelity, the unchanged five-column schema, duplicate-free repeated upserts, refreshed timestamp instants, succeeded metadata, and NULL watermarks. See [validation](../engineering/TESTING.md#task-35-verification). Existing transaction boundaries and failure semantics below remain unchanged.

### Genres (task 3.1)

`src/storage/raw_genres.py` provides `ensure_raw_genres_table(connection, schema_name)` and `upsert_raw_genres(connection, genres, schema_name, fetched_at)`. The destination is `<POSTGRES_RAW_SCHEMA>.raw_genres` (default `raw.raw_genres`), with the same five-column shape shown above. It uses the `GENRES` contract's source `id` → raw `igdb_id` mapping. Only name/slug are extracted alongside the key; the entire fetched object, including `updated_at` when present, is stored in JSONB.

DDL commits separately. Non-empty upserts replace name, slug, payload, and `fetched_at` on primary-key conflict, then commit and return processed input-row count. Empty inputs open no cursor and make no helper commit. All rows are prepared before writes, so a missing ID fails without a partial upsert; name and slug are nullable. Identifiers use `psycopg.sql.Identifier` and values are parameterized. Database errors propagate for the runner's connection context to handle. These semantics match games, whose code and emitted SQL remain unchanged.

Direct composition with `pipeline.ingest_entity()` uses the existing connection factory and separate metadata connections, recording `entity='genres'`. Durable start, success after raw context exit, best-effort failure reporting, and NULL watermarks apply unchanged. The [manual smoke invocation](INGESTION.md#genres-task-31) documents this path. Offline tests verify SQL preparation and lifecycle ordering; two live five-genre runs on PostgreSQL 17.11 verified DDL, JSONB fidelity, persisted success metadata, and duplicate-free repeated upserts on September 26, 2026.

### Platforms (task 3.2)

`src/storage/raw_platforms.py` provides `ensure_raw_platforms_table(connection, schema_name)` and `upsert_raw_platforms(connection, platforms, schema_name, fetched_at)`. `<POSTGRES_RAW_SCHEMA>.raw_platforms` uses the same five-column raw shape and source `id` → `igdb_id` mapping via `PLATFORMS`. Name/slug are nullable; the complete fetched object, including `updated_at` if present, remains JSONB.

As with genres, identifiers are quoted, values parameterized, all rows prepared before writes, DDL committed separately, and non-empty upserts committed after execution. Conflicts replace name/slug/payload/fetch time. Empty input returns zero without a cursor or helper commit; database errors propagate. The unchanged runner records `entity='platforms'` using separate metadata connections, a durable start, success after raw context exit, best-effort failure reporting, and NULL watermarks.

Two bounded live runs verified five distinct rows, source/archive/JSONB fidelity, timestamp refresh, and persisted success metadata. See the [invocation](INGESTION.md#platforms-task-32) and [verification details](../engineering/TESTING.md#task-32-verification).

### Companies (task 3.3)

`src/storage/raw_companies.py` provides `ensure_raw_companies_table(connection, schema_name)` and `upsert_raw_companies(connection, companies, schema_name, fetched_at)`. `<POSTGRES_RAW_SCHEMA>.raw_companies` has the same five-column shape, using `COMPANIES` to map source `id` to raw `igdb_id`. Name/slug are nullable; the complete fetched object, including source update time when present, is retained in JSONB.

Identifiers are quoted and values parameterized. Rows are prepared before writes; missing IDs prevent any upsert. DDL and non-empty loads commit separately. Conflicts replace name, slug, payload, and fetch time; empty input returns zero without a cursor or helper commit. Errors propagate to the existing runner's context. The runner records `entity='companies'` with the unchanged durable start, success after raw context exit, best-effort failure reporting, and NULL watermarks.

Two bounded live runs verified source/archive/JSONB equality, repeated upserts, timestamp refresh, and persisted metadata. See the [invocation](INGESTION.md#companies-task-33) and [verification](../engineering/TESTING.md#task-33-verification). No existing table definitions or schema settings changed.

### Involved companies (task 3.4)

`src/storage/raw_involved_companies.py` provides `ensure_raw_involved_companies_table()` and `upsert_raw_involved_companies()` with the established callback signatures. `<POSTGRES_RAW_SCHEMA>.raw_involved_companies` contains only:

```text
igdb_id BIGINT PRIMARY KEY
payload JSONB NOT NULL
fetched_at TIMESTAMPTZ NOT NULL
```

The relationship record's own source `id` maps to `igdb_id`, never the game ID, company ID, or a composite pair. The complete fetched JSONB retains `game`, `company`, `developer`, `publisher`, and supported `updated_at`, plus any other returned attributes. This minimal schema avoids invented name/slug fields and premature relational extraction; dbt will own analytics typing and relationship modeling. Missing optional fields, explicit nulls, and false booleans stay unchanged. There are no foreign keys requiring referenced entities to exist in bounded raw samples.

Identifiers are quoted and values parameterized. All rows are prepared before writes; missing IDs prevent any upsert. DDL commits separately, and non-empty upserts replace payload/fetch time on `igdb_id` conflict and commit. Empty loads open no cursor and make no helper commit. Exceptions propagate. The unchanged runner records `entity='involved_companies'`, retaining durable start, success after raw context exit, best-effort failure reporting, and NULL watermarks.

Offline and two bounded live runs verified this path; see [ingestion](INGESTION.md#involved-companies-task-34) and [validation](../engineering/TESTING.md#task-34-verification). Existing schemas and connection settings are unchanged.

## Target raw tables

```text
raw_games
raw_genres
raw_platforms
raw_companies
raw_involved_companies
ingestion_runs
```

The final Python-owned schema is `raw` by default; `POSTGRES_RAW_SCHEMA` can select another schema. The same setting controls all five raw tables and `ingestion_runs`. The legacy `POSTGRES_SCHEMA` setting is used only when the new variable is absent. Existing `analytics` data and run history are not moved by changing the default. See [schema transition](../engineering/LOCAL_DEVELOPMENT.md#schema-names-and-existing-analytics-installations).

dbt declares only the five raw entity tables as `igdb` sources, using the same `POSTGRES_RAW_SCHEMA` → legacy `POSTGRES_SCHEMA` → `raw` precedence as Python. The declaration does not create or move raw tables; see [dbt sources](DBT_TRANSFORMATIONS.md#source-layer).

## Raw-table contract

Each source table should have:

- the stable IGDB ID as primary key;
- full source payload in JSONB;
- `fetched_at` in UTC;
- source `updated_at` when useful for operations/incremental logic;
- only a small number of extracted columns needed for operational readability or indexing.

Do not flatten the entire source in Python. dbt should perform analytics-oriented extraction and typing.

## Upsert semantics

Raw loading must be idempotent at the source-record level.

For a record with an existing IGDB ID:

- replace/update the retained source payload;
- update `fetched_at`;
- update extracted operational columns;
- do not create a second logical source record.

### Overlapping-window preparation (task 4.4)

The existing games, companies, and involved-companies loaders already satisfy the replay contract; no production changes were needed. Source `id` maps to raw `igdb_id`, the declared primary key and sole `ON CONFLICT` target. Involved companies uses its own record ID even when two records share game/company references; changing those references does not change identity. Source `updated_at` is retained inside JSONB and never selects the conflict key or deduplicates rows. Distinct IDs sharing a timestamp are prepared as distinct rows.

Every input occurrence is prepared in input order for `executemany()`, including repeated IDs and changed payloads. Conflicts unconditionally replace complete payloads and `fetched_at`, plus name/slug for games and companies (including replacement with NULL). Missing/null timestamps, nested values, relationship arrays and false roles remain unchanged. This requests last-upsert behavior, **not source-version ordering**: a later stale response can overwrite a newer payload. The raw layer is not version history, and upserts cannot recover unseen source records or propagate deletions.

Returned counts are acknowledged input rows after the helper commit, including replays; they are neither net-new rows nor distinct IDs and do not use cursor `rowcount`. Empty loads, preparation-before-write errors, exception propagation, separate DDL/load commits, and caller-owned connection contexts are unchanged.

The [task 4.4 tests](../engineering/TESTING.md#task-44-overlap-upsert-verification) compose explicit optional windows and real fetch/load helpers with queued clients and mocked cursors. They assert SQL, ordered parameters, payloads, counts, and commit calls; they do not execute PostgreSQL constraints or establish live idempotency, rollback, durability, or source completeness. Task 4.5 now applies windows in normal CLI runs without changing upsert SQL or transaction boundaries.

## Ingestion run metadata

Implemented table: `<POSTGRES_RAW_SCHEMA>.ingestion_runs`, defaulting to `raw.ingestion_runs`. It is created if absent; this configuration change does not migrate an existing table or its watermark history.

```text
ingestion_runs
- run_id UUID PRIMARY KEY
- entity TEXT NOT NULL
- started_at TIMESTAMPTZ NOT NULL
- completed_at TIMESTAMPTZ nullable
- status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed'))
- records_fetched INTEGER NOT NULL DEFAULT 0 CHECK (records_fetched >= 0)
- records_loaded INTEGER NOT NULL DEFAULT 0 CHECK (records_loaded >= 0)
- source_watermark_start TIMESTAMPTZ nullable
- source_watermark_end TIMESTAMPTZ nullable
- error_message TEXT nullable
```

This table is operational metadata, not an analytics mart. Each entity invocation gets a Python-generated UUID, even when it reloads the same source records. Times are generated in UTC. For normal games/companies/involved-companies CLI runs, `source_watermark_start` records the actual inclusive lower bound when filtered, and eligible success records the run-start exclusive cutoff in `source_watermark_end`. Unfiltered/reference starts and ineligible/failed ends remain NULL. The runner uses the task 4.2 read-only lookup before source work.

`src/storage/ingestion_runs.py` exposes:

- `ensure_ingestion_runs_table(connection, schema_name)` — creates the schema/table and commits DDL;
- `get_source_watermark(connection, schema_name, entity)` — returns the greatest successful non-NULL end or `None`; reads only metadata using the caller's connection, with no DDL, writes, commit, rollback, or connection lifecycle management;
- `start_ingestion_run(connection, schema_name, entity, *, started_at=None, source_watermark_start=None)` — inserts/commits a `running` row with zero counts and optional explicit run start/lower bound, then returns its UUID;
- `succeed_ingestion_run(connection, schema_name, run_id, records_fetched, records_loaded, *, source_watermark_end=None)` — sets/commits `succeeded`, completion time, counts, NULL error, and optional eligible end in one guarded update;
- `fail_ingestion_run(connection, schema_name, run_id, records_fetched, records_loaded, error_message)` — sets/commits `failed`, completion time, counts, and a caller-supplied safe summary.

Both terminal helpers update only a matching `running` row; missing/already-completed runs raise `ValueError` without committing. SQL identifiers are quoted and values parameterized. Helpers propagate errors and leave rollback/connection closure to their caller's context. Call the DDL/lifecycle write helpers on dedicated connections with no unrelated pending writes because those helpers commit their transactions.

The lookup issues one schema-qualified aggregate with an exact entity parameter, `status = 'succeeded'`, and a non-NULL end predicate. Later NULL-ended/older-ended successes cannot hide greater progress. No qualifying end, including legacy NULL-only histories, returns `None`; missing tables and all other lookup errors propagate. The supplied connection chooses the database and transaction visibility; the caller must supply committed history without pending metadata writes. Only the cursor is managed by the helper, and a SELECT may implicitly start a driver transaction. See the [lookup contract and example](WATERMARKS.md#persisted-lookup-helper-task-42).

Counts reflect completed operations: `records_fetched` becomes the list length only when fetching returns successfully, so a later-page fetch failure records zero even if earlier requests returned rows. `records_loaded` is the upsert helper's returned row count after its commit succeeds; it counts processed input rows (inserts and updates), not net-new or distinct games. A load error records zero unless the helper already returned successfully. Running rows retain their initial zero counts until a terminal update; there is no progress checkpointing.

The reusable ingestion runner supplies only fixed stage summaries (`source fetch failed.`, `JSONL archive failed.`, `raw load failed.`, or `run completion failed.`). It emits fixed safe warnings when a successful incremental run cannot publish progress, without persisting raw exception text, connection strings, or payload values.

## CLI composition (task 3.6)

The CLI selects one entity (games by default) or all five in games → genres → platforms → companies → involved_companies order. Each invokes the existing runner independently with its own archive, durable start, raw-load context, and terminal metadata. No storage helper, schema, source query, or payload handling changed.

All mode stops at the first failure. Earlier successful entities remain committed, with their archives and succeeded metadata retained; later entities have no new runs. Failure in terminal metadata can still occur after that entity’s raw commit. There is no transaction spanning entities and no cumulative/group metadata row. Per-entity counts retain the acknowledged-operation meaning described above. Watermarks stay NULL, and bounded samples impose no reference-existence checks.

Two actual CLI runs verified complete archives against JSONB and repeated upserts against preexisting rows; see [task 3.6 validation](../engineering/TESTING.md#task-36-verification).

## Transactions

The raw-games transaction behavior is unchanged, and genres/platforms/companies/involved companies follow the same boundaries: schema/table DDL commits before loading. A non-empty load commits after `executemany()` succeeds. Database errors propagate; helpers do not add explicit rollback or retry handling. The runner retains the existing psycopg connection context, which handles rollback on exceptional exit and closes the connection. A failed load therefore does not undo already committed DDL. Empty loads add no helper commit; the outer context retains its normal driver exit behavior.

Run metadata uses separate connections and transactions:

1. Before source client creation/fetching, a metadata connection commits metadata DDL, then commits a `running` row, then closes. Setup/start failures abort the command before source work; a row is not guaranteed if the start cannot be committed.
2. The existing fetch → JSONL archive → raw connection flow executes. Raw DDL and non-empty upserts still commit separately. No database connection is held during the source fetch/archive.
3. After the raw context exits successfully, a fresh metadata connection commits `succeeded`. Failure to connect/write/commit here fails the command; any committed raw data remains loaded.
4. An ordinary exception after start triggers a best-effort `failed` update on a fresh connection, after the failed raw/success context has exited. Known counts are retained, including a nonzero loaded count if the raw helper already returned. A secondary failure to record failure is logged without exception details and never replaces the original exception.

These boundaries deliberately do not make raw data and terminal metadata atomic. Connection loss around a commit can leave the database outcome uncertain; counts describe acknowledged operations, not reconciliation of ambiguous commits. If a success commit took effect but its acknowledgment was lost, the guarded failure update cannot overwrite that terminal success. An unavailable metadata database, process death, or `KeyboardInterrupt`/`SystemExit` can leave a `running` row. There is no automatic retry, stale-run recovery, or reconciliation through task 2.5. The JSONL archive is also outside PostgreSQL transactions and can remain after a load failure (or be partial after an archive failure).

Unit tests verify helper commit calls, SQL preparation, transitions, and exception/context ordering with fakes. Bounded live genres, platforms, companies, and involved-companies smoke runs verified successful commits and duplicate-free repeated upserts. The [PostgreSQL integration suite](../engineering/TESTING.md#postgresql-integration-tests) additionally verifies raw batch rollback, terminal SQL failure after a committed load, retry, and guarded failure reporting after a simulated acknowledgment error following a real success commit. Actual network-loss and server-crash outcomes remain untested.

### Accepted watermark design (task 4.1)

The [watermark contract](WATERMARKS.md#window-and-metadata-contract) governs normal and explicit CLI runs: start is the actual inclusive query lower bound (NULL for unfiltered reads); end is the exclusive progress cutoff, published only with eligible terminal success. End remains NULL for capped, custom-projection, reference-refresh, backfill, failed, and running records. Successful empty uncapped normal/full-refresh runs may publish their cutoff. The runner uses greatest successful non-NULL-end lookup per entity; it never uses raw payload maxima or counts. Tasks 4.5 and 4.7 change no metadata/raw schema, payload, count meaning, load order, or transaction boundary.

The [failure policy](WATERMARKS.md#failure-and-transaction-contract) preserves all transactions and acknowledged counts above. Success/end must share the existing terminal metadata commit after raw context exit. A committed raw load followed by failed metadata is replayed from the prior checkpoint. A durable success whose acknowledgment is lost may still supply progress on the next lookup; guarded failure reporting cannot overwrite it. Stale running records never imply success. No schema migration, combined raw/metadata transaction, or automatic reconciliation is part of this design.

## Indexing

Start with primary keys. Add indexes only for demonstrated access patterns, such as source update timestamps used by operational queries. Avoid speculative indexing of JSONB fields before dbt query patterns exist.
