# dbt Transformations

## Responsibility

dbt converts raw IGDB records into typed, documented, tested analytics models. Python should not duplicate this work.

## Current state

The dbt project is initialized and configured with three model directories:

```text
models/staging     → views
models/intermediate → views
models/marts       → tables
```

The five raw tables are declared as dbt `igdb` sources. `stg_games`, `stg_genres`, `stg_platforms`, `stg_companies`, and `stg_involved_companies` are implemented as views. All five are built and queried by PostgreSQL integration tests using synthetic fixtures in disposable schemas. All five models and 35 output columns have YAML descriptions. Ten source tests and ten staging identifier tests pass against synthetic fixtures and existing local data. See [repeatable integration checks](../engineering/TESTING.md#postgresql-integration-tests) and [local sample verification](../engineering/TESTING.md#task-59-model-documentation-and-build-verification).

The dbt profile writes future models to `DBT_SCHEMA` (default `analytics`), independently of the source schema selected by `POSTGRES_RAW_SCHEMA` (default `raw`). `dbt_project.yml` has no layer-specific `+schema` overrides, so future staging, intermediate, and mart models will use the configured output schema unless a later task changes that policy. dbt does not read `.env` itself. Source declarations create no relations or move data. Python and dbt resolve the source schema in the same order: `POSTGRES_RAW_SCHEMA`, then legacy `POSTGRES_SCHEMA`, then `raw`. Existing installations can continue using exported `POSTGRES_SCHEMA=analytics`; adopting `raw` still requires the [deliberate schema transition](../engineering/LOCAL_DEVELOPMENT.md#schema-names-and-existing-analytics-installations).

## Source layer

`dbt/models/sources.yml` declares `source('igdb', '<raw_table>')` for `raw_games`, `raw_genres`, `raw_platforms`, `raw_companies`, and `raw_involved_companies`. Each table describes one IGDB source record per `igdb_id`, with complete JSONB `payload` and loader assigned `fetched_at`. Games, genres, platforms, and companies also have nullable `name` and `slug` columns. For involved companies, `igdb_id` is the relationship record ID; game/company references and developer/publisher roles stay in `payload`.

Every raw table has source-level `unique` and `not_null` tests on `igdb_id`, matching Python's primary-key/upsert contract. These tests have passed against PostgreSQL and require a reachable database to run. They check raw keys, not the staging view’s scalar casts. No relationship tests or source freshness threshold is declared; bounded and manual ingestion has no documented schedule from which to set a reliable threshold. `ingestion_runs` is operational metadata, not an analytics source for this task.

## Staging layer

One staging model per source entity:

```text
stg_games
stg_genres
stg_platforms
stg_companies
stg_involved_companies
```

Staging responsibilities:

- select from one raw source;
- extract required JSONB fields;
- rename columns consistently;
- convert Unix timestamps to SQL timestamps where required;
- cast ratings/counts/IDs;
- standardize null/boolean handling;
- expose `fetched_at` and useful source update metadata.

Avoid joins and business aggregations in staging.

### `stg_games` (task 5.3)

`dbt/models/staging/stg_games.sql` is a view in `DBT_SCHEMA` (default `analytics`) selected directly from `source('igdb', 'raw_games')`. Its grain is one row per raw game `igdb_id`, exposed as `game_id`; there is no join, filter, deduplication, or relationship expansion. Raw upserts enforce this grain in PostgreSQL, while offline checks only inspect the contract. The output columns are:

| Column | SQL type | Meaning |
|---|---|---|
| `game_id` | `BIGINT` | Raw `igdb_id`, the IGDB game identifier. |
| `name`, `slug` | `TEXT`, nullable | Existing raw game name and slug. |
| `first_release_at` | `TIMESTAMPTZ`, nullable | `payload.first_release_date` Unix seconds converted to an instant; this is the game-level first release, not a platform or region release. |
| `source_updated_at` | `TIMESTAMPTZ`, nullable | `payload.updated_at` Unix seconds converted to an instant. |
| `rating`, `total_rating` | `NUMERIC`, nullable | IGDB rating values, without rounding or thresholds. |
| `rating_count`, `total_rating_count` | `BIGINT`, nullable | IGDB rating counts; zero is preserved when supplied. |
| `genre_ids`, `platform_ids` | `JSONB`, nullable | Source ID arrays for genre and platform relationships. |
| `involved_company_ids` | `JSONB`, nullable | Source involved-company **record** ID array, not company IDs. |
| `fetched_at` | `TIMESTAMPTZ` | Raw loader timestamp for this version of the game. |

Optional scalar fields use JSONB text extraction and casts. An absent key or explicit JSON null becomes SQL NULL; no missing rating/count is changed to zero. The three reference fields use JSONB extraction, preserving array order and empty arrays; absent keys yield SQL NULL, while explicit JSON null remains JSONB `null`. Invalid non-null numeric values raise PostgreSQL conversion errors when the affected view expressions are evaluated. Creating the view does not evaluate its rows, so `dbt build` can pass even when a later query fails: the dbt tests inspect raw and staging primary identifiers, not every projected value. The opt-in integration suite reads every staging column and checks invalid rating, count, and timestamp inputs explicitly. This model does not validate array members or referenced rows.

### `stg_genres` (task 5.4)

`dbt/models/staging/stg_genres.sql` is a view in independent `DBT_SCHEMA` (default `analytics`), selected directly from `source('igdb', 'raw_genres')`. Its grain is one row per raw genre `igdb_id`, enforced by the raw primary key. It adds no joins, filters, deduplication, relationship expansion, or business transformations.

| Column | SQL type | Meaning |
|---|---|---|
| `genre_id` | `BIGINT` | Raw `igdb_id`, the IGDB genre identifier. |
| `name`, `slug` | `TEXT`, nullable | Existing raw genre name and slug, passed through unchanged. |
| `source_updated_at` | `TIMESTAMPTZ`, nullable | `payload.updated_at` Unix seconds converted to an instant. |
| `fetched_at` | `TIMESTAMPTZ` | Raw loader timestamp for this version of the genre. |

As in `stg_games`, timestamp extraction uses `to_timestamp((payload ->> 'updated_at')::bigint)`. Missing keys and explicit JSON null become SQL NULL; epoch zero and negative Unix seconds retain their instants. Nullable names/slugs and empty strings remain unchanged. Invalid non-null timestamp text fails when the view expression is read, even if creation succeeds. Integration tests query every output column, check actual PostgreSQL types and grain, and verify invalid timestamp reads under explicit, legacy, and conflicting raw-schema settings. Primary-identifier tests are declared in task 5.8; model/column YAML documentation is in `dbt/models/staging/schema.yml` (task 5.9).

### `stg_platforms` (task 5.5)

`dbt/models/staging/stg_platforms.sql` is a view in independent `DBT_SCHEMA` (default `analytics`), selected directly from `source('igdb', 'raw_platforms')`. Its grain is one row per raw platform `igdb_id`, enforced by the raw primary key. It adds no joins, filters, deduplication, relationship expansion, or business transformations.

| Column | SQL type | Meaning |
|---|---|---|
| `platform_id` | `BIGINT` | Raw `igdb_id`, the IGDB platform identifier. |
| `name`, `slug` | `TEXT`, nullable | Existing raw platform name and slug, passed through unchanged. |
| `source_updated_at` | `TIMESTAMPTZ`, nullable | `payload.updated_at` Unix seconds converted to an instant. |
| `fetched_at` | `TIMESTAMPTZ` | Raw loader timestamp for this version of the platform. |

As in `stg_games`, timestamp extraction uses `to_timestamp((payload ->> 'updated_at')::bigint)`. Missing keys and explicit JSON null become SQL NULL; epoch zero and negative Unix seconds retain their instants. Nullable names/slugs and empty strings remain unchanged. Invalid non-null timestamp text fails when the view expression is read, even if creation succeeds. Integration tests query every output column, check actual PostgreSQL types and grain, and verify invalid timestamp reads under explicit, legacy, and conflicting raw-schema settings. Primary-identifier tests are declared in task 5.8; model/column YAML documentation is in `dbt/models/staging/schema.yml` (task 5.9).

### `stg_companies` (task 5.6)

`dbt/models/staging/stg_companies.sql` is a view in independent `DBT_SCHEMA` (default `analytics`), selected directly from `source('igdb', 'raw_companies')`. Its grain is one row per raw company `igdb_id`, enforced by the raw primary key. It adds no joins, filters, deduplication, relationship expansion, or business transformations.

| Column | SQL type | Meaning |
|---|---|---|
| `company_id` | `BIGINT` | Raw `igdb_id`, the IGDB company identifier. |
| `name`, `slug` | `TEXT`, nullable | Existing raw company name and slug, passed through unchanged. |
| `source_updated_at` | `TIMESTAMPTZ`, nullable | `payload.updated_at` Unix seconds converted to an instant. |
| `fetched_at` | `TIMESTAMPTZ` | Raw loader timestamp for this version of the company. |

As in `stg_games`, timestamp extraction uses `to_timestamp((payload ->> 'updated_at')::bigint)`. Missing keys and explicit JSON null become SQL NULL; epoch zero and negative Unix seconds retain their instants. Nullable names/slugs and empty strings remain unchanged. Invalid non-null timestamp text fails when the view expression is read, even if creation succeeds. Integration tests query every output column, check actual PostgreSQL types and grain, and verify invalid timestamp reads under explicit, legacy, and conflicting raw-schema settings. Primary-identifier tests are declared in task 5.8; model/column YAML documentation is in `dbt/models/staging/schema.yml` (task 5.9).

### `stg_involved_companies` (task 5.7)

`dbt/models/staging/stg_involved_companies.sql` selects directly from `source('igdb', 'raw_involved_companies')` as a view in independent `DBT_SCHEMA`. Its grain is one row per raw relationship record ID, enforced by the raw primary key. Distinct records sharing the same game/company pair remain distinct. There are no joins, filters, deduplication, expansion, or business transformations.

| Column | SQL type | Meaning |
|---|---|---|
| `involved_company_id` | `BIGINT` | Raw `igdb_id`, the relationship record ID, not a company ID. |
| `game_id`, `company_id` | `BIGINT`, nullable | Payload game/company references; referenced rows need not exist in bounded raw samples. |
| `developer`, `publisher` | `BOOLEAN`, nullable | Independent source role flags; both may be true, both false, or unknown. |
| `source_updated_at` | `TIMESTAMPTZ`, nullable | Payload `updated_at` Unix seconds converted to an instant using the existing staging convention. |
| `fetched_at` | `TIMESTAMPTZ` | Unchanged raw loader timestamp. |

JSONB text extraction and direct casts turn absent keys and explicit JSON null into SQL NULL. False booleans and zero references remain unchanged; no default role is inferred. Epoch zero and negative source timestamps retain their instants. Invalid non-null references, booleans, and timestamps fail when the affected view expressions are read. View creation and identifier tests alone do not validate every scalar cast. Offline contract checks and opt-in PostgreSQL tests cover the projection, actual types, relationship grain, repeated/unmatched pairs, all four role combinations, large IDs, missing/null cases, and invalid scalar reads. Primary-identifier tests are declared in task 5.8; model/column YAML documentation is in `dbt/models/staging/schema.yml` (task 5.9).

## Intermediate layer

Use intermediate models for reusable relationships and logic. Expected relationship areas are:

- game ↔ genre;
- game ↔ platform;
- game ↔ company with developer/publisher role.

Task 3.5 preserves games `genres`, `platforms`, and `involved_companies` as ID arrays in raw JSONB; `stg_games` carries them forward as JSONB. The first two reference the corresponding lookup IDs; the third references involved-company record IDs, whose `company` points to companies and whose `game`, `developer`, and `publisher` describe the association. Future dbt models will expand these arrays and resolve roles. Raw bounded samples are not required to contain all references; missing relationships must not be interpreted as verified absence of a real-world association. No relationship models or tests are implemented yet.

The exact representation remains a later modeling decision. Prefer explicit bridge-style grains such as one row per game/genre rather than arrays inside mart tables when relational analysis benefits from it.

## Mart layer

Each mart must document its grain before implementation.

Candidate marts:

### `mart_game_catalog`

Potential grain: one row per game. Useful for game exploration and common descriptive fields.

### `mart_release_trends`

Potential grain: release period plus selected dimensions. Used for counts/trends over time.

### Genre/platform performance

Potential grain should be chosen carefully so ratings are not accidentally double-counted across many-to-many relationships.

### Company output

Use involved-company roles to distinguish developer/publisher relationships where the source supports them.

## Tests

Use dbt tests for warehouse contracts:

- `unique` and `not_null` on primary identifiers;
- relationship tests on valid foreign keys when source semantics warrant them;
- accepted values for controlled role/type fields when appropriate;
- custom singular tests only when they express a meaningful invariant.

Do not add tests merely to increase test count.

### Staging identifier tests (task 5.8)

`dbt/models/staging/schema.yml` declares `unique` and `not_null` on `stg_games.game_id`, `stg_genres.genre_id`, `stg_platforms.platform_id`, `stg_companies.company_id`, and `stg_involved_companies.involved_company_id`. These ten default-error tests protect the output grain separately from the ten existing source-key tests. The involved-company identifier is the relationship record ID, not either reference or the game/company pair. No optional reference, role, name, or timestamp is made required.

Strict relationship checks are deferred as follows:

| Candidate check | Reason deferred |
|---|---|
| `stg_involved_companies.game_id` → `stg_games.game_id` | Games and relationship records are ingested independently; bounded runs/backfills may omit referenced games. References are nullable by contract. |
| `stg_involved_companies.company_id` → `stg_companies.company_id` | Independent company ingestion does not guarantee referenced companies are loaded. Nullable references and repeated companies are valid. |
| `stg_games.genre_ids` → `stg_genres.genre_id` | References remain JSONB arrays, including absent/null/empty values. No bridge exists yet, and bounded genre loads need not cover every reference. |
| `stg_games.platform_ids` → `stg_platforms.platform_id` | Same array and incomplete-ingestion limitations as genres. |
| `stg_games.involved_company_ids` → `stg_involved_companies.involved_company_id` | Array elements identify relationship records, not companies; independent bounded relationship loads may omit them. |

Neither individual game/company references nor their pair is unique at relationship-record grain. Presence, positivity, role exclusivity, and reciprocal-array consistency are not documented invariants. No warning-only or filtered relationship test is added to imply coverage we do not have. Revisit reference-existence checks when relationship models and an explicit ingestion-completeness policy justify them; joining away unmatched records alone would not prove coverage.

Offline tests check the YAML against entity key mappings and existing model aliases. Opt-in database tests build all models with incomplete references, then introduce duplicate or NULL identifiers into disposable staging views while keeping raw constraints and data valid. Each affected model test must fail with one violation, all ten source tests must still pass, and all twenty tests must pass again after restoring the views. Existing tests continue to query every scalar and check malformed inputs. Identifier tests cannot validate unrelated casts or establish source completeness. See [task 5.8 verification](../engineering/TESTING.md#task-58-dbt-tests-verification).

## Documentation

Task 5.9 documents all five staging views and all 35 output columns in `dbt/models/staging/schema.yml`. Descriptions specify source lineage, row grain, SQL types, nullable scalars, Unix-seconds timestamp conversion, unchanged loader timestamps, and rating/count pass-through without thresholds or defaults. JSONB reference descriptions distinguish absent keys (SQL NULL), explicit JSON null, empty arrays, and relationship record IDs. Involved-company docs retain repeated pairs, nullable/unmatched references, and independent nullable roles. The [relationship-test deferrals](#staging-identifier-tests-task-58) remain in effect.

Offline coverage rejects missing, duplicate, stale, or blank column documentation against each SQL projection. PostgreSQL integration checks verify that dbt's parsed manifest retains nonempty model/column descriptions covering the actual built view columns under all three source-schema configurations. Descriptions are dbt metadata; no enforced model constraints or persisted database comments are added.

For future models, document:

- source purpose;
- model grain;
- important columns;
- metric definitions;
- relationship caveats;
- rating-count thresholds or filters used in marts.

A reviewer should be able to understand the model without reading every SQL file.

## Build contract

The verified validation command is:

```bash
dbt build
```

It builds five documented staging views and runs ten source plus ten staging identifier tests as one transformation step. Task 5.9 verified this against existing local data, including parsed documentation and separate full-row comparisons; see [verification and limitations](../engineering/TESTING.md#task-59-model-documentation-and-build-verification).
