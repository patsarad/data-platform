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

The five raw tables are declared as dbt `igdb` sources. `stg_games`, `stg_genres`, `stg_platforms`, `stg_companies`, and `stg_involved_companies` are implemented as views. All five are built and queried by PostgreSQL integration tests using synthetic fixtures in disposable schemas. All five staging models and 35 output columns have YAML descriptions. Tasks 6.1–6.2 add documented two-column `int_game_genres` and `int_game_platforms` relationship views, each with three grain/key tests. Task 6.3 adds the five-column `int_game_companies` view at relationship-record grain with two identifier tests, bringing documentation to eight models and 44 columns. Task 6.4 adds the eleven-column `mart_game_catalog` table, for nine models and 55 documented columns. Task 6.5 adds the two-column `mart_release_trends` table, bringing documentation to ten models and 57 columns. Task 6.6 adds separate seven-column genre/platform performance tables, bringing documentation to twelve models and 71 columns. Task 6.7 adds the nine-column company-output table, bringing documentation to thirteen models and 80 columns. Ten source, ten staging identifier, eight relationship, four catalog, five release-trend, six performance, and three company-output tests pass against synthetic fixtures and existing local data. See [repeatable integration checks](../engineering/TESTING.md#postgresql-integration-tests) and [local sample verification](../engineering/TESTING.md#task-68-mart-contract-audit-verification).

The optimized test harness separates schema configuration from data behavior:
three full-project cases cover explicit/legacy/precedence settings, independent
output schemas, all model documentation and mart reconciliation. The 64 existing detailed
behavior scenarios plus one task 6.8 array-container scenario run once with explicit
settings. Model SQL is unchanged; task 6.8 adds one invariant. Historical verification
sections retain their original counts.
See the [current coverage matrix](../engineering/TESTING.md#postgresql-integration-tests).

The dbt profile writes models to `DBT_SCHEMA` (default `analytics`), independently of the source schema selected by `POSTGRES_RAW_SCHEMA` (default `raw`). `dbt_project.yml` has no layer-specific `+schema` overrides, so staging, intermediate, and mart models use the configured output schema unless a later task changes that policy. dbt does not read `.env` itself. Source declarations create no relations or move data. Python and dbt resolve the source schema in the same order: `POSTGRES_RAW_SCHEMA`, then legacy `POSTGRES_SCHEMA`, then `raw`. Existing installations can continue using exported `POSTGRES_SCHEMA=analytics`; adopting `raw` still requires the [deliberate schema transition](../engineering/LOCAL_DEVELOPMENT.md#schema-names-and-existing-analytics-installations).

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

As in `stg_games`, timestamp extraction uses `to_timestamp((payload ->> 'updated_at')::bigint)`. Missing keys and explicit JSON null become SQL NULL; epoch zero and negative Unix seconds retain their instants. Nullable names/slugs and empty strings remain unchanged. Invalid non-null timestamp text fails when the view expression is read, even if creation succeeds. Integration tests query every output column, check actual PostgreSQL types and grain, and verify invalid timestamp reads with explicit raw-schema settings. Dedicated full-project cases separately cover explicit, legacy, and conflicting schema resolution. Primary-identifier tests are declared in task 5.8; model/column YAML documentation is in `dbt/models/staging/schema.yml` (task 5.9).

### `stg_platforms` (task 5.5)

`dbt/models/staging/stg_platforms.sql` is a view in independent `DBT_SCHEMA` (default `analytics`), selected directly from `source('igdb', 'raw_platforms')`. Its grain is one row per raw platform `igdb_id`, enforced by the raw primary key. It adds no joins, filters, deduplication, relationship expansion, or business transformations.

| Column | SQL type | Meaning |
|---|---|---|
| `platform_id` | `BIGINT` | Raw `igdb_id`, the IGDB platform identifier. |
| `name`, `slug` | `TEXT`, nullable | Existing raw platform name and slug, passed through unchanged. |
| `source_updated_at` | `TIMESTAMPTZ`, nullable | `payload.updated_at` Unix seconds converted to an instant. |
| `fetched_at` | `TIMESTAMPTZ` | Raw loader timestamp for this version of the platform. |

As in `stg_games`, timestamp extraction uses `to_timestamp((payload ->> 'updated_at')::bigint)`. Missing keys and explicit JSON null become SQL NULL; epoch zero and negative Unix seconds retain their instants. Nullable names/slugs and empty strings remain unchanged. Invalid non-null timestamp text fails when the view expression is read, even if creation succeeds. Integration tests query every output column, check actual PostgreSQL types and grain, and verify invalid timestamp reads with explicit raw-schema settings. Dedicated full-project cases separately cover explicit, legacy, and conflicting schema resolution. Primary-identifier tests are declared in task 5.8; model/column YAML documentation is in `dbt/models/staging/schema.yml` (task 5.9).

### `stg_companies` (task 5.6)

`dbt/models/staging/stg_companies.sql` is a view in independent `DBT_SCHEMA` (default `analytics`), selected directly from `source('igdb', 'raw_companies')`. Its grain is one row per raw company `igdb_id`, enforced by the raw primary key. It adds no joins, filters, deduplication, relationship expansion, or business transformations.

| Column | SQL type | Meaning |
|---|---|---|
| `company_id` | `BIGINT` | Raw `igdb_id`, the IGDB company identifier. |
| `name`, `slug` | `TEXT`, nullable | Existing raw company name and slug, passed through unchanged. |
| `source_updated_at` | `TIMESTAMPTZ`, nullable | `payload.updated_at` Unix seconds converted to an instant. |
| `fetched_at` | `TIMESTAMPTZ` | Raw loader timestamp for this version of the company. |

As in `stg_games`, timestamp extraction uses `to_timestamp((payload ->> 'updated_at')::bigint)`. Missing keys and explicit JSON null become SQL NULL; epoch zero and negative Unix seconds retain their instants. Nullable names/slugs and empty strings remain unchanged. Invalid non-null timestamp text fails when the view expression is read, even if creation succeeds. Integration tests query every output column, check actual PostgreSQL types and grain, and verify invalid timestamp reads with explicit raw-schema settings. Dedicated full-project cases separately cover explicit, legacy, and conflicting schema resolution. Primary-identifier tests are declared in task 5.8; model/column YAML documentation is in `dbt/models/staging/schema.yml` (task 5.9).

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

Task 3.5 preserves games `genres`, `platforms`, and `involved_companies` as ID arrays in raw JSONB; `stg_games` carries them forward as JSONB. The first two reference the corresponding lookup IDs; the third references involved-company record IDs, whose `company` points to companies and whose `game`, `developer`, and `publisher` describe the association. Tasks 6.1–6.2 expand genre and platform arrays; task 6.3 preserves company roles at involved-company record grain. Raw bounded samples are not required to contain all references; missing relationships must not be interpreted as verified absence of a real-world association.

### `int_game_genres` (task 6.1)

`dbt/models/intermediate/int_game_genres.sql` is a view in independent `DBT_SCHEMA`, selected only from `ref('stg_games')`. Its grain is **one row per distinct `(game_id, genre_id)` pair**. Both columns are `BIGINT`; neither column alone is unique. Multiple games can share a genre, and one game can have several genres. Downstream counts/ratings must account for this many-to-many grain.

A lateral `jsonb_array_elements_text` expands `genre_ids`; members cast to `BIGINT`, and `select distinct` collapses repeated pairs after conversion. No source order, array position, names, or extra game attributes are projected. No lookup join filters the result: a valid genre ID is retained even when independently bounded genre ingestion has not loaded it. There is no positivity or reference-existence constraint.

| Input `genre_ids` | Relationship output |
|---|---|
| Absent key / SQL NULL | Zero rows. |
| JSON null | Normalized to SQL NULL before expansion; zero rows. |
| Empty array `[]` | Zero rows. |
| `[2, 2, 999]` | Two pairs for that game: genres 2 and 999, whether or not either genre is loaded. |
| Array containing JSON null | A NULL genre member remains visible and fails `genre_id`'s `not_null` test. Valid members are retained. |
| Non-null non-array value, or member that cannot cast to BIGINT | PostgreSQL raises when evaluated; malformed data is not silently treated as an empty array. |

Absent/null/empty distinctions remain available in staging/raw. Zero bridge rows only means no relationship was represented by that stored array; it does not prove the game has no real-world genres. Text members use PostgreSQL's BIGINT cast (including castable integer strings); no separate JSON-type or positive-ID validation is imposed.

Two `not_null` tests in `intermediate/schema.yml` protect the keys. `dbt/tests/int_game_genres_unique_pair.sql` checks composite uniqueness without an extra package or surrogate key. Offline checks protect SQL lineage, expansion/null normalization, pair grain, and YAML documentation/tests. Opt-in PostgreSQL checks evaluate exact values/types, missing/null/empty arrays, duplicate/reused/large/zero IDs, incomplete genre coverage, malformed input, and deliberate pair/key defects with recovery under the primary schema configuration; dedicated full-project cases cover all source-schema modes. See [task 6.1 verification](../engineering/TESTING.md#task-61-game-genre-relationship-verification).

### `int_game_platforms` (task 6.2)

`dbt/models/intermediate/int_game_platforms.sql` is a view in independent `DBT_SCHEMA`, selected only from `ref('stg_games')`. Its grain is **one row per distinct `(game_id, platform_id)` pair**. Both columns are `BIGINT`; neither column alone is unique. Multiple games can share a platform, and one game can have several platforms. Downstream counts/ratings must account for this many-to-many grain.

A lateral `jsonb_array_elements_text` expands `platform_ids`; members cast to `BIGINT`, and `select distinct` collapses repeated pairs after conversion. No source order, array position, names, or extra game attributes are projected. No lookup join filters the result: a valid platform ID is retained even when independently bounded platform ingestion has not loaded it. There is no positivity or reference-existence constraint.

| Input `platform_ids` | Relationship output |
|---|---|
| Absent key / SQL NULL | Zero rows. |
| JSON null | Normalized to SQL NULL before expansion; zero rows. |
| Empty array `[]` | Zero rows. |
| `[2, 2, 999]` | Two pairs for that game: platforms 2 and 999, whether or not either platform is loaded. |
| Array containing JSON null | A NULL platform member remains visible and fails `platform_id`'s `not_null` test. Valid members are retained. |
| Non-null non-array value, or member that cannot cast to BIGINT | PostgreSQL raises when evaluated; malformed data is not silently treated as an empty array. |

Absent/null/empty distinctions remain available in staging/raw. Zero bridge rows only means no relationship was represented by that stored array; it does not prove the game has no real-world platforms. Text members use PostgreSQL's BIGINT cast (including castable integer strings); no separate JSON-type or positive-ID validation is imposed.

This deliberately follows the genre bridge contract without refactoring it. Castable integer strings deduplicate with numeric IDs after conversion; zero and negative IDs are not filtered.

Two `not_null` tests in `intermediate/schema.yml` protect the keys. `dbt/tests/int_game_platforms_unique_pair.sql` checks composite uniqueness without an extra package or surrogate key. Offline checks protect SQL lineage, expansion/null normalization, pair grain, and YAML documentation/tests. Opt-in PostgreSQL checks evaluate exact values/types, missing/null/empty arrays, duplicate/reused/large/zero IDs, incomplete platform coverage, malformed input, and deliberate pair/key defects with recovery under the primary schema configuration; dedicated full-project cases cover all source-schema modes. See [task 6.2 verification](../engineering/TESTING.md#task-62-game-platform-relationship-verification).

### `int_game_companies` (task 6.3)

Grain defined before implementation: **one row per involved-company relationship
record (`involved_company_id`)**, sourced only from `ref('stg_involved_companies')`.
The model is a view in independent `DBT_SCHEMA`. It projects five columns:

| Column | SQL type | Meaning |
|---|---|---|
| `involved_company_id` | `BIGINT`, required and unique | Source relationship record identity, not a company ID. |
| `game_id`, `company_id` | `BIGINT`, nullable | Staged references, retained even if the corresponding game/company is not loaded. |
| `developer`, `publisher` | `BOOLEAN`, nullable | Independent source roles, preserved without defaults. |

Distinct relationship IDs sharing a game/company pair remain separate, even when
their role values also match. There is no pair-level deduplication, aggregation,
role expansion, join, or filtering. Raw upserts already replace repeated versions
of the same record ID; unexpected duplicate staged IDs remain visible and fail
the model's `unique` test rather than being silently collapsed. Downstream counts
must distinguish relationship records from distinct games or game/company pairs.

Both roles may be true, both false, or individually unknown (SQL NULL). False
means the source flag is false; unknown is not inferred as false. Missing and JSON
null references/roles remain SQL NULL. Nullable references do not remove records.
The existing staging BIGINT/BOOLEAN casts supply typing: castable strings and
zero/negative references pass through, while malformed non-null values raise
when evaluated. This projection adds no tolerant cast or malformed-input default.
Source/fetch timestamps remain available in staging and are not projected here.

`stg_games.involved_company_ids` contains relationship record IDs, not company
IDs, and does not drive this model. Independent bounded ingestion does not justify
reference-existence, reciprocal-array, positivity, required-reference, or role
exclusivity tests. Only `involved_company_id` has `unique` and `not_null` dbt
tests; BOOLEAN typing supplies the role domain. Identifier tests and view creation
alone do not evaluate every reference/role cast or establish source completeness.
Offline contracts and opt-in PostgreSQL tests cover values/types, repeated pairs,
all nine nullable role combinations, incomplete references, malformed-input
recovery, and deliberate record-key failures under the primary configuration.
Dedicated full-project cases cover all schema modes. See
[task 6.3 verification](../engineering/TESTING.md#task-63-game-company-relationship-verification).

## Mart layer

Each mart must document its grain before implementation.

The implemented mart contracts follow.

### Shared mart interpretation (task 6.8 audit)

All five marts are rebuilt **tables**, not incremental models or live views.
Their staging/intermediate ancestors are views over the latest stored raw rows.
Run/build the marts after ingestion; `dbt test` alone does not refresh them.
Reconciliation assumes unchanged sources between materialization and testing;
a project build does not promise one atomic snapshot across all five tables.
A later test failure does not roll back models already materialized by that build.
No ingestion schedule, automatic refresh, deletion propagation, or full IGDB
coverage is implied. Raw upserts retain one stored version per record ID, not
source history; see [raw storage](RAW_STORAGE.md#upsert-semantics).

The column tables below and `dbt/models/marts/schema.yml` define all 36 mart
columns' PostgreSQL types, semantic nullability, and meanings. “Required” is a
data contract checked by tests, not an enforced SQL NOT NULL/model constraint.
Grouping always uses the documented IDs/year, never labels. Counts are absolute
counts of the stated population, with no implicit percentage denominator.
Only `avg_rating` is a ratio: the sum of non-NULL ratings divided by
`rated_game_count`, using PostgreSQL AVG precision; zero contributors produce
NULL. `rating_count_sum` has no denominator and is not unique people.

The [documentation-to-test matrix](../engineering/DATA_QUALITY.md#mart-contract-coverage-matrix-task-68)
distinguishes declared dbt invariants, integration-only value checks, and claims
the bounded data cannot support. Existing exact-value coverage is retained;
task 6.8 adds only the catalog array-container invariant, with no model SQL change.

### `mart_game_catalog` (task 6.4)

Contract defined before implementation: **exactly one row per `stg_games.game_id`,
including every staged game**. Use the existing marts **table** materialization
in independent `DBT_SCHEMA`. This is a snapshot refreshed by a successful dbt
run/build, so rebuild after ingestion before exploring changed data. No game
filter, ranking threshold, rating default, or performance metric is introduced.

| Column | SQL type | Meaning |
|---|---|---|
| `game_id` | `BIGINT`, required and unique | Staged game identity; exact staged-game coverage. |
| `name`, `slug` | `TEXT`, nullable | Staged descriptive values, including empty strings. |
| `first_release_at` | `TIMESTAMPTZ`, nullable | Staged game-level first release instant, not a platform/region release. |
| `rating`, `total_rating` | `NUMERIC`, nullable | Unchanged staged ratings, without rounding or defaults. |
| `rating_count`, `total_rating_count` | `BIGINT`, nullable | Unchanged staged rating counts; zero and NULL remain distinct. |
| `observed_genres` | `JSONB` array, required | Objects with `genre_id` and `name`, one per distinct bridge pair, ordered by numeric `genre_id` ascending. |
| `observed_platforms` | `JSONB` array, required | Objects with `platform_id` and `name`, one per distinct bridge pair, ordered by numeric `platform_id` ascending. |
| `observed_company_relationships` | `JSONB` array, required | Objects with `involved_company_id`, `company_id`, `name`, `developer`, and `publisher`, one per relationship record, ordered by numeric `involved_company_id` ascending. |

Scalar lineage is `raw_games` → `stg_games` → catalog. Genre/platform arrays
come through their game bridges and left-joined staged lookup names; company
objects come from `raw_involved_companies` → `stg_involved_companies` →
`int_game_companies`, with `stg_companies` labels. Array lengths count observed
genre/platform pairs or company **records**, not distinct companies or games.
The catalog defines no aggregate rating metric or denominator. Supplied zero
ratings/counts remain known values; NULL is unknown, not zero.

Each relationship is aggregated independently by game before left joining to
`stg_games`, preventing cross-products among genres, platforms, and companies.
Reference names come from left joins to the corresponding staging lookup; valid
unmatched IDs survive with JSON null names. A loaded reference's NULL or empty
name stays NULL or empty. Names are labels, never deduplication keys. The existing
genre/platform bridges collapse repeated IDs after their BIGINT casts; the mart
adds no deduplication. Distinct company record IDs remain separate even with the
same company and identical roles. All nullable developer/publisher combinations
are retained independently, with unknown represented as JSON null, never false.
Nullable company references likewise remain JSON null inside observed records.

Company membership follows `int_game_companies.game_id`, not the games'
`involved_company_ids` array (which contains relationship record IDs, not company
IDs). Records referencing unloaded or NULL games remain in the intermediate
model but cannot attach to a catalog game; they do not create extra game rows.
The catalog does not impose reciprocal-array consistency or reference existence.

Each aggregate defaults to `[]` only when there are no observed relationship
rows for that game. Arrays are never SQL NULL and contain no placeholder object
for a missing relationship. Missing/null/empty game genre/platform arrays all
yield `[]`; their original distinctions remain in staging/raw. Empty aggregates
mean **no observed associations in the stored bounded data**, not verified absence
in IGDB or the real world. Nonempty arrays likewise do not establish completeness.
Object key order and catalog row order are not part of the contract; array element
order is deterministic. Clients should order game rows explicitly.

Existing staging casts and relationship tests remain authoritative; malformed
non-null values are not silently normalized by the mart. The table build evaluates
its projected expressions but does not validate every unprojected staging field.
Only game identity is a required/unique key; a singular coverage test compares
staged and catalog game IDs in both directions. Task 6.8 additionally requires
each relationship container to be a non-NULL JSON array. The singular
`mart_game_catalog_relationship_arrays` test emits one violation per game/column
for SQL NULL, JSON null, objects, or scalars. It permits empty arrays and does not
validate elements: exact scalar/object values, element order, and fanout remain
independent integration checks. There are no required-reference,
positivity, role-exclusivity, or rating-count constraints. Release-trend and genre/platform performance marts follow below; company output follows below.

### `mart_release_trends` (task 6.5)

Contract defined before implementation: **one row per observed UTC calendar year
of `stg_games.first_release_at`**. Lineage is `raw_games` → `stg_games` →
`mart_release_trends`, with no relationship joins or expansions. Use the existing
marts **table** materialization in independent `DBT_SCHEMA`; rebuild after
ingestion to refresh this snapshot.

| Column | SQL type | Meaning |
|---|---|---|
| `release_year` | `INTEGER`, required and unique | Calendar year extracted from `first_release_at AT TIME ZONE 'UTC'`, independent of the PostgreSQL session timezone. |
| `release_count` | `BIGINT`, required and positive | Number of staged games with a non-NULL game-level first release instant in this UTC year; each staged game contributes once. |

The metric counts games, not platform/regional releases, relationship records,
or ingestion events. Existing staging identity tests enforce one row per game;
counting those rows directly prevents relationship fanout. The game-level instant
is passed through the existing staging cast: valid zero and negative Unix epochs
remain eligible, with no date cutoffs, present-date filter, or tolerant recast.
Malformed non-NULL release timestamps continue to fail when evaluated.

Missing/JSON-null release dates become SQL NULL in staging and are excluded from
this mart, without an unknown-year row. An unknown date does **not** mean a game
is unreleased. Years without dated observations are omitted, never zero-filled;
empty or entirely undated input produces an empty table. Missing years and counts
from bounded ingestion do not establish real-world absence or complete coverage.
Consumers should order by `release_year`; physical row ordering is not guaranteed.

At the same source snapshot, `coalesce(sum(release_count), 0)` equals the number
of staged games with non-NULL `first_release_at`. Adding the staged undated-game
count reconciles to the entire staged game population (and raw games under the
existing staging contract). Undated counts remain available in staging/catalog,
not repeated on every annual row. The catalog's scalar/relationship contract is
unchanged; this mart reads staging directly so it does not depend on catalog
refresh order.

Declared dbt invariants: unique/non-NULL year, non-NULL positive count, and exact
yearly reconciliation against dated staged games in both directions. A singular
reconciliation test catches missing/extra years and incorrect counts, including
redistribution that preserves the grand total. No year range or source-coverage
constraint is imposed. These tests compare a table snapshot with current staging,
so rerun/build after source changes before expecting reconciliation to pass.

### Genre/platform performance (task 6.6)

Contract defined before implementation: separate `mart_genre_performance` and
`mart_platform_performance` **tables**, using the existing marts materialization
in independent `DBT_SCHEMA`. Each row represents one observed genre ID or platform
ID associated with at least one staged game. Separate tables keep the two ID
namespaces and grains unambiguous. These are descriptive stored-game comparisons,
not rankings, sales/revenue measures, or estimates of all IGDB games.

Lineage: `raw_games` → `stg_games` → `int_game_genres` or `int_game_platforms`,
joined back to `stg_games` for ratings. The corresponding `stg_genres` or
`stg_platforms` supplies only a label, via a left join **after** ID aggregation.
Genres and platforms are aggregated independently; neither mart joins the other
bridge or companies. Distinct `(game_id, dimension_id)` pairs before aggregation
ensure one contribution per game within a dimension, even if a bridge repeats a
pair. Existing staging/source identifier tests remain authoritative for game and
lookup identity; unexpected duplicate staged IDs are not silently resolved.

Both models expose these seven columns in order (substitute genre/platform):

| Column | SQL type | Meaning |
|---|---|---|
| `genre_id` / `platform_id` | `BIGINT`, required and unique | Observed relationship ID; the grouping key, never the name. Zero/negative/large valid IDs survive. |
| `name` | `TEXT`, nullable | Corresponding staged label; unmatched references and loaded NULL names yield NULL; empty strings remain empty. Duplicate labels on distinct IDs remain separate rows. |
| `game_count` | `BIGINT`, required | Number of distinct associated staged games, including games with no rating or rating count. Positive because only observed dimensions appear. |
| `rated_game_count` | `BIGINT`, required | Number of associated games with non-NULL `stg_games.rating`; explicit denominator for `avg_rating`. Zero if none. |
| `avg_rating` | `NUMERIC`, nullable | Unweighted arithmetic mean of those non-NULL ratings, one contribution per game regardless of `rating_count`; NULL if denominator is zero. PostgreSQL NUMERIC average precision is retained, without explicit rounding. |
| `rating_count_game_count` | `BIGINT`, required | Number of associated games with non-NULL `stg_games.rating_count`, independently of whether `rating` exists. Explicit contributor count for the sum. |
| `rating_count_sum` | `NUMERIC`, nullable | PostgreSQL SUM(BIGINT) of non-NULL `rating_count` across those games; NULL when no count is supplied. Context for reported rating volume, not unique raters, an average denominator, or a weighting factor. |

Only the existing `rating`/`rating_count` pair is used. `total_rating` and
`total_rating_count` remain separate, unchanged staging/catalog fields; they are
not substituted or mixed into these summaries. This is the smallest metric set
that shows observed size, average rating and its coverage, and supplied count
volume and its coverage. No minimum threshold, weighting, ranking, range filter,
forecast, or new interpretation of otherwise valid staging values is added.

Absent/JSON-null ratings and counts become SQL NULL in staging and contribute to
neither their respective aggregate nor its non-NULL denominator. A supplied zero
rating contributes zero and one rated game; a supplied zero count contributes zero
and one count-bearing game. Missing ratings do not exclude known counts, and
missing/zero counts do not exclude known ratings. Valid negative values also pass
through without a new range policy. Malformed non-NULL projected values still
raise on evaluation, using existing staging casts.

Unloaded references and loaded dimensions with missing/empty names survive.
A NULL label means an observed ID has no available label, not a missing association;
staging lookups distinguish an unloaded reference from a loaded unnamed dimension.
Missing/null/empty association arrays create no row and no synthetic unknown bucket.
Loaded dimensions with no observed games are omitted; entirely empty or
association-free game input produces empty marts. These omissions describe bounded
stored observations, never verified absence of real-world relationships. Counts
summed across dimensions can exceed the distinct game population because one game
may contribute once to each of several dimensions; summed rating counts likewise
repeat across dimensions. Neither cross-dimension totals nor averages of dimension
averages describe the distinct game population.

Declared dbt invariants per mart: unique/non-NULL dimension ID and exact
bidirectional reconciliation of all seven columns with relationship/game/label
source models at the same snapshot. Reconciliation enforces observed coverage,
labels, positive game counts, non-NULL denominators and exact NULL-aware metrics
without imposing rating/count ranges or reference completeness. Rebuild after
ingestion before testing reconciliation: tables are snapshots, and standalone
tests compare them to current source views. Consumers supply row ordering.

### `mart_company_output` (task 6.7)

Contract defined before SQL implementation: one **table** row per distinct non-NULL
`int_game_companies.company_id`, using existing marts materialization in independent
`DBT_SCHEMA`. Membership comes exclusively from involved-company records, never
`stg_games.involved_company_ids`; reciprocal arrays are not required. Lineage:
`raw_involved_companies` → `stg_involved_companies` → `int_game_companies` → mart,
with `stg_companies` for labels/loading context and `stg_games` only for reference
presence. No ratings, rankings, thresholds, forecasting, or ingestion expansion.

Coverage assessment before implementation: existing local data has five relationship
records, five observed company IDs (1, 3, 4, 7, 11), and three referenced game IDs
(2, 37, 38). Company IDs 7/11 and game IDs 37/38 are unloaded. All five records
have non-NULL references and explicit roles; three are developer-only, two are
publisher-only. This supports descriptive **observed game-reference output**,
not complete company catalogs, verified releases, sales, or absence claims.
Synthetic tests supplement the small sample's role/null/repetition coverage.

| Column | SQL type | Meaning |
|---|---|---|
| `company_id` | `BIGINT`, required and unique | Observed non-NULL company reference; grouping key, including valid zero/negative/large IDs. |
| `name` | `TEXT`, nullable | Staged company label; unloaded or loaded unnamed companies yield NULL. Empty strings and duplicate labels on distinct IDs remain unchanged. |
| `company_loaded` | `BOOLEAN`, required | Whether this ID exists in `stg_companies`; distinguishes unloaded from loaded unnamed companies. |
| `relationship_record_count` | `BIGINT`, required, positive | Number of observed relationship records with this company ID, including NULL games and repeated pairs with distinct record IDs. |
| `null_game_relationship_count` | `BIGINT`, required | Relationship records with SQL NULL game references; no identifiable game, unlike a non-NULL unloaded reference. |
| `game_count` | `BIGINT`, required | Distinct non-NULL game references for this company, including unloaded games and all role combinations. Zero if all its game references are NULL. |
| `loaded_game_count` | `BIGINT`, required | Distinct referenced games present in `stg_games`; `game_count - loaded_game_count` is the distinct unloaded-reference count. |
| `developer_game_count` | `BIGINT`, required | Distinct non-NULL game references with at least one record explicitly `developer = true`, regardless of publisher or game loading. |
| `publisher_game_count` | `BIGINT`, required | Distinct non-NULL game references with at least one record explicitly `publisher = true`, regardless of developer or game loading. |

All counts except relationship_record_count may be zero. Aggregate by company ID
before attaching labels; use game existence checks, not multiplying game joins.
Existing source/staging unique-ID tests protect lookup identity. Duplicate labels
never merge IDs. Unexpected duplicate lookup IDs are invalid upstream and must fail
key tests, not be resolved by choosing an arbitrary name; an invalid company lookup
can repeat output rows but cannot multiply the precomputed metrics.

Distinct involved-company IDs sharing a pair retain their identity upstream and
each contributes one relationship record. Every game counts at most once per
company and declared role scope, even with identical or conflicting role records.
Raw duplicate source IDs use existing last-upsert replacement (not source-version
ordering); only the stored version contributes. Unexpected duplicate bridge record
IDs remain visible to its existing unique test; they count as physical records in
record metrics, while DISTINCT protects game metrics. No record deduplication or
role conflict winner is invented. Explicit true evidence on any record qualifies
a game for that role even when another record says false or NULL.

For a non-NULL game, the nine developer/publisher combinations contribute as follows
(before distinct-game collapse within each scope):

| developer | publisher | game | developer game | publisher game |
|---|---|---|---|---|
| true | true | yes | yes | yes |
| true | false | yes | yes | no |
| true | NULL | yes | yes | no |
| false | true | yes | no | yes |
| false | false | yes | no | no |
| false | NULL | yes | no | no |
| NULL | true | yes | no | yes |
| NULL | false | yes | no | no |
| NULL | NULL | yes | no | no |

Here “no” means no explicit true evidence from that record, not a conversion of
unknown to false. NULL-game records contribute to both record metrics and no game
metric regardless of roles. Developer/publisher counts can overlap on a both-true
record or separate conflicting records; never sum them as distinct output. Games
with neither observed true role still contribute to game_count. Cross-company sums
also repeat games associated with multiple companies.

Loaded companies without observed relationships are omitted. NULL-company records
remain in staging/relationship models but cannot be attributed to a company: no
unknown-company row or repeated global count is invented. At the same snapshot,
SUM(relationship_record_count), defaulting to zero for an empty mart, plus the
number of NULL-company relationship records equals all relationship rows. The sum
of game_count equals distinct non-NULL (company_id, game_id) pairs, not all staged
games or relationship records. Empty input or only NULL companies produces no rows.
Omitted rows and zero metrics establish only a lack of corresponding stored
observations/explicit true evidence, never verified real-world absence or full
coverage. Missing names are not missing relationships. Source casts remain unchanged;
malformed projected references/roles still raise rather than being silently filtered.

Declared dbt invariants: unique/non-NULL company ID and exact bidirectional,
NULL-safe reconciliation of every column with relationship and lookup models.
This enforces the population, labels/loading state and all record/game metrics
without positivity constraints on IDs or reference-completeness requirements.
Rebuild after ingestion: this is a table snapshot, and standalone reconciliation
compares it with current source views. Row ordering is supplied by consumers.

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
| `stg_games.genre_ids` → `stg_genres.genre_id` | Staging preserves JSONB arrays. Task 6.1 expands them into `int_game_genres`, but bounded genre loads still need not cover every reference; the bridge retains unmatched IDs. |
| `stg_games.platform_ids` → `stg_platforms.platform_id` | Task 6.2 expands arrays into `int_game_platforms` and retains unmatched IDs; bounded platform ingestion does not establish reference completeness. |
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

For startup and the intended ingestion → build sequence, follow
[Compose first use and subsequent sessions](../engineering/LOCAL_DEVELOPMENT.md#compose-first-use-and-subsequent-sessions-task-74).
PostgreSQL initialization creates the database/login; Python creates all five raw
tables before a full dbt build. dbt source declarations do not create those tables.
Task 7.5 verified this sequence on new Compose volumes: two five-record-per-entity
live runs followed by all thirteen models and 46 passing tests, exact raw-to-model
reconciliation, and persistence across container recreation. This validates bounded
startup, not source completeness or an uncapped incremental bootstrap. See the
[verification record](../engineering/TESTING.md#task-75-clean-volume-live-workflow-verification).

The task-7.2 shared image supports these same dbt commands directly, with project
and profile directories set to `/app/dbt`. Runtime `POSTGRES_*`/`DBT_SCHEMA`
variables keep the existing schema resolution; the image carries no credentials.
Default target/log directories are `/tmp/dbt/target` and `/tmp/dbt/logs`, and
telemetry is disabled. See [build and direct invocation examples](../engineering/LOCAL_DEVELOPMENT.md#shared-pythondbt-image-task-72).
This packaging does not change models, invariants, or the optimized test harness.
Task 7.3 additionally supports `dc run --rm runtime dbt <command>` through the
profiled Compose service. The environment fixes database addressing to
`postgres:5432`; unset schema variables remain absent, preserving the same source
precedence and independent output default. Direct dbt targets/logs persist in the
project's `dbt_artifacts` volume at `/tmp/dbt`, separate from host artifacts.
Use separate subdirectories for concurrent commands. See [Compose environment and
artifact export](../engineering/LOCAL_DEVELOPMENT.md#on-demand-compose-runtime-task-73).


The verified validation command is:

```bash
dbt build
```

It builds five staging views, three relationship views, and five mart tables (`mart_game_catalog`, `mart_release_trends`, `mart_genre_performance`, `mart_platform_performance`, `mart_company_output`), running 46 tests: ten source, ten staging identifier, eight relationship, four catalog, five release-trend, six performance, and three company-output. Task 6.8 verified all thirteen models and 80 documented columns against existing local data, including every earlier comparison and exact company-output metrics independently derived from source-model values. See [verification and limitations](../engineering/TESTING.md#task-68-mart-contract-audit-verification). Rebuild all five marts after ingestion because they are table snapshots.
