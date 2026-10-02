# Data Quality

## Purpose

Data quality in this project is layered. API success alone does not mean the resulting analytics are trustworthy.

## Raw-layer checks

Raw ingestion should enforce or verify:

- IGDB ID is present for records that require one;
- primary-key uniqueness through database constraints;
- payload is valid JSONB and non-null;
- ingestion timestamps are present;
- record counts are captured per run;
- failed runs do not advance incremental state.

## Transformation checks

Use dbt tests for:

- unique/not-null staging identifiers;
- valid relationships where source semantics support strict relationships;
- accepted role/type values where appropriate;
- mart grain uniqueness;
- required dimensions/metrics.

Task 5.8 adds ten staging primary-identifier tests (`unique`/`not_null`) alongside the ten raw source-key tests. The involved-company key is its own record ID; repeated game/company pairs are valid. Optional references remain nullable. Strict foreign-key tests are deferred because independently bounded raw loads do not guarantee referenced rows, and staging game references use JSONB arrays. The [test policy and per-relationship deferrals](../pipeline/DBT_TRANSFORMATIONS.md#staging-identifier-tests-task-58) record when to reconsider these checks. Successful identifier tests do not validate all scalar casts or source completeness.

Task 5.9 adds documentation coverage for all five staging models and 35 columns. Offline checks compare YAML documentation with SQL projections; database checks compare the parsed manifest with actual view columns. Documentation preserves nullable/reference semantics and adds no new data-quality constraints.

Task 6.1 adds two required-key tests and a composite-uniqueness singular test for `int_game_genres`. Repeated array IDs collapse to one pair; individual game/genre IDs can repeat across pairs. Missing/null/empty arrays emit no association. Null members fail the required genre-key test; non-array values and non-castable members raise on evaluation. Valid unmatched genre IDs are retained: no strict genre reference-existence test is justified by independent bounded ingestion. Exact-row PostgreSQL fixtures verify both missing and extra associations, including unmatched references. Deliberately broken bridge views prove each dbt grain/key test fails and recovers. See the [contract](../pipeline/DBT_TRANSFORMATIONS.md#int_game_genres-task-61).

Task 6.2 applies the same grain/key policy to `int_game_platforms`: two `not_null` tests and one composite-uniqueness test. PostgreSQL fixtures compare exact pairs with stored platform arrays, including cast-normalized duplicates, absent/null/empty arrays, large/reused/zero/negative IDs, and incomplete platform coverage. Malformed arrays/members raise, null members fail the platform-key test, and corrected input recovers. Deliberately broken output proves all three tests fail individually and recover after restoration. No platform reference-existence test is justified. See the [platform contract](../pipeline/DBT_TRANSFORMATIONS.md#int_game_platforms-task-62).

Task 6.3 adds `unique` and `not_null` tests only on `int_game_companies.involved_company_id`. Distinct relationship IDs sharing a game/company pair remain distinct, including identical role values. References and independent BOOLEAN roles remain nullable; both-true, both-false, and all unknown combinations are valid. Existing staging casts reject malformed non-null references/roles when read. No reference-existence, reciprocal-array, positivity, required-reference, or exclusive-role rule is justified. Offline contracts and PostgreSQL exact-row checks protect this behavior; deliberate duplicate/NULL record IDs must fail and recover after view restoration. See the [company contract](../pipeline/DBT_TRANSFORMATIONS.md#int_game_companies-task-63).

Task 6.4 adds `unique`/`not_null` on `mart_game_catalog.game_id` plus a singular
test comparing catalog and staged game IDs in both directions. This protects
one-row-per-game grain and catches both dropped and invented games. These are
transformation coverage checks, not claims that IGDB ingestion is complete.
PostgreSQL tests compare every scalar and ordered relationship object, exercise
fanout, duplicate IDs/labels/record pairs, all nullable roles, incomplete lookups,
and absent/null/empty values. Deliberate duplicate/NULL/missing/extra output rows
must fail the corresponding tests and recover on rebuild. Malformed projected
inputs must fail table materialization; corrected inputs must rebuild successfully.
No optional field becomes required, and no rating or reference constraint is added.
See the [catalog contract](../pipeline/DBT_TRANSFORMATIONS.md#mart_game_catalog-task-64).

Task 6.5 declares five release-trend invariants: unique/non-NULL `release_year`,
non-NULL `release_count`, positive counts for observed years, and exact annual
reconciliation with dated `stg_games` in both directions. Missing/extra years and
incorrect counts must fail even when the total is unchanged. At the same snapshot,
annual counts (zero for empty output) plus undated staged games equal all staged
games. NULL dates do not mean unreleased; omitted years do not prove real-world
absence. UTC extraction is explicit; no epoch/date-range constraint is added.
The PostgreSQL cases exercise different session timezones, zero/negative epochs,
empty/all-undated populations, and deliberate failures of every declared invariant
with rebuild recovery. These checks protect the stored population, not ingestion
completeness. See the [release contract](../pipeline/DBT_TRANSFORMATIONS.md#mart_release_trends-task-65).

Task 6.6 adds three tests per performance mart: unique/non-NULL dimension ID
and a singular exact reconciliation of every output column to source models.
The reconciliation uses a semi-join from observed IDs to games, preventing repeated
bridge pairs from multiplying the oracle's metrics. A full outer join and
NULL-safe comparisons catch missing/extra IDs, label drift, every wrong or NULL
count/denominator/aggregate, and accidental zero-filling. Existing key tests protect
staged game/lookup identity. No range, completeness, or reference-existence policy
is added. Tests compare snapshots with current sources, so rebuild after ingestion.
See the [performance contract](../pipeline/DBT_TRANSFORMATIONS.md#genreplatform-performance-task-66).

Task 6.7 adds unique/non-NULL company ID and exact, NULL-safe bidirectional
reconciliation for all nine `mart_company_output` columns. Its oracle independently
groups game pairs and uses role evidence per pair; record counts remain separate.
Reconciliation catches dropped/invented companies, label/loading-state drift, and
wrong/NULL counts. Distinct game metrics resist repeated relationship records;
record identity defects remain subject to the unchanged upstream tests. Lookup
keys stay unique by existing contracts. NULL-company records reconcile upstream,
and NULL games count only as records, unlike valid unloaded game IDs. Both roles
can count the same game, while unknown roles supply no explicit true evidence.
No completeness, positive-ID, reciprocal-array, or exclusive-role invariant is
imposed. Rebuild snapshots before reconciliation. See the
[company-output contract](../pipeline/DBT_TRANSFORMATIONS.md#mart_company_output-task-67).

## Mart contract coverage matrix (task 6.8)

Audit result: all five mart grains and all 36 output columns already have type,
nullability and meaning documentation in the [mart contracts](../pipeline/DBT_TRANSFORMATIONS.md#mart-layer)
and dbt YAML. Population, omitted rows, nullable/zero values, labels, unloaded
references, repetition, overlap and fanout semantics are defined there. Task 6.8
makes shared refresh/denominator semantics and required catalog containers explicit.
No model violates its documented contract; no production SQL fix is needed.

| Mart / documented contract | Declared dbt invariants | Integration value evidence retained |
|---|---|---|
| [Catalog](../pipeline/DBT_TRANSFORMATIONS.md#mart_game_catalog-task-64): one row per staged game; scalar pass-through; three independent ordered arrays | Unique/non-NULL `game_id`; bidirectional game coverage; **new** `mart_game_catalog_relationship_arrays` requires all three containers to be non-NULL JSON arrays (4 tests total) | `assert_catalog_matches_sources` compares all 11 columns with independent Python grouping. `test_game_catalog_*` covers NULL/zero scalars, ordered objects, missing/empty labels, unmatched/NULL references, all nine role combinations, repeated company records, pair deduplication, fanout, empty input, snapshots and malformed-input recovery. Exact contents/order remain integration-only. |
| [Release trends](../pipeline/DBT_TRANSFORMATIONS.md#mart_release_trends-task-65): one row per observed UTC year; count dated games once; omit undated/unobserved years | Unique/non-NULL year, non-NULL positive count, exact bidirectional yearly reconciliation (5 tests) | `assert_release_trends_matches_sources` independently groups dates in Python. `test_release_trends_*` covers UTC boundaries/session timezones, zero/negative epochs, future dates, missing/empty populations, total/undated reconciliation, multiplicity, snapshots and malformed-input recovery. |
| [Genre performance](../pipeline/DBT_TRANSFORMATIONS.md#genreplatform-performance-task-66): one row per observed genre ID; distinct staged games; independent rating/count contributors | Unique/non-NULL genre ID; exact NULL-safe reconciliation of every column, including population, labels, counts, denominator, mean and sum (3 tests) | `assert_performance_matches_sources` uses raw arrays, Python sets and Decimal arithmetic. `test_performance_*` covers repeated pairs, cross-genre overlap, absent/NULL/zero/negative values, unmatched/unnamed labels, empty input, snapshots and cast recovery. |
| [Platform performance](../pipeline/DBT_TRANSFORMATIONS.md#genreplatform-performance-task-66): same metrics at separate platform-ID grain | Unique/non-NULL platform ID; exact NULL-safe reconciliation of all seven columns (3 tests) | The same performance helpers check the platform population independently, including overlap across platforms and protection from genre/company fanout. |
| [Company output](../pipeline/DBT_TRANSFORMATIONS.md#mart_company_output-task-67): one row per observed non-NULL company ID; records versus distinct game references; independent explicit role evidence | Unique/non-NULL company ID; exact NULL-safe reconciliation of all nine columns (3 tests) | `assert_company_output_matches_sources` independently groups raw/staged records and game sets. `test_company_output_*` covers repeated/conflicting records, all nullable roles, NULL versus unloaded games, company loading/labels, overlapping roles/companies, duplicate lookups, omitted/empty populations, snapshots and cast recovery. |

Test helpers live in `tests/integration/test_dbt_postgres.py`. Existing deliberate
defect tests assert exact failed-test names/counts and successful recovery for
each declared invariant. The new array test checks all three columns separately
with SQL NULL, JSON null, object and scalar containers: exactly 12 game/column
violations, followed by a rebuild and exact source comparison. Existing catalog
NULL/extra-row defects also fail the new check (three invalid containers each).
Empty arrays and nullable object fields continue to pass.

All-model manifest/column checks and fresh/cached builds in three dedicated schema
modes protect documentation, lineage and configuration. Behavioral fixtures check
actual PostgreSQL types and values; offline SQL/YAML checks detect missing/stale
documentation without a database. Descriptions themselves are not SQL constraints.
The optimized harness keeps 64 existing scenarios and adds just one primary-schema
scenario. No extra schema-mode Cartesian product or full-project setup is added.

**Coverage sufficient; no duplicate invariants added:** performance/company exact
reconciliation already catches required-count NULLs, incorrect zeros, label drift,
missing/extra groups and incorrect metrics. Additional range/denominator tests
would duplicate those guarantees. Catalog scalar fidelity and JSON element content
remain integration-only; its new container guard protects safe array consumption
without copying the catalog transformation into another reconciliation query.

**Limitations, not defensible invariants:** bounded independent loads cannot prove
complete reference coverage, reciprocal game/company arrays, full catalogs,
real-world absence, or that unknown dates mean unreleased games. Empty arrays,
omitted years/dimensions/companies and zero role counts describe only stored
observations. Do not require references/labels/roles, positive IDs, exclusive
roles, rating ranges, arbitrary thresholds, or cross-dimension/company sums equal
to distinct games. Repeated company record IDs fail existing identity tests;
distinct record IDs sharing a pair are valid. All marts depend on upstream key
contracts; reconciliation is not an ingestion-completeness or freshness guarantee.
Comparisons require rebuilt snapshots and stable sources. Tests do not validate
every unused staging cast, and the small local sample needs the retained synthetic
edge cases. No remaining mart contract gap requires another model or metric.

See [task 6.8 verification](TESTING.md#task-68-mart-contract-audit-verification)
for exact commands, results and preservation checks.

## Rating metrics

IGDB rating fields can be misleading when very few users contributed ratings. Analytics marts/app views that rank or compare ratings should include rating-count context and, where ranking is used, a documented minimum-count threshold or other explicit rule.

Do not present a raw average rating as equally reliable across vastly different rating counts.

Task 6.6 reports unweighted `rating` means with `rated_game_count`, plus
`rating_count_sum` and its independent `rating_count_game_count` contributor count.
Known counts still contribute when a rating is missing; known ratings still
contribute when counts are missing or zero. All-missing aggregates remain NULL;
supplied zeros count as known values. No thresholds/rankings are introduced, and
`total_rating` remains separate in staging/catalog. Count sums describe reported
rating volume, not distinct raters or a confidence guarantee.

## Many-to-many relationships

Games can relate to multiple genres/platforms/companies. Models must define their grain clearly so aggregations do not accidentally double-count games or ratings.

Every relationship/mart model should document whether a game can appear multiple times and how downstream aggregations should interpret that grain.

The catalog aggregates each relationship independently before joining to games.
Genre/platform elements count distinct bridge pairs; company elements count
involved-company records, including repeated company/role combinations. Empty
arrays mean no observed relationships in bounded stored data, not real-world
absence. Unknown company roles remain JSON null; both-true/both-false are valid.

## Freshness

Pipeline operational metadata should make the most recent successful ingestion visible. dbt source freshness can be added where a meaningful source-update expectation exists, but arbitrary freshness thresholds should not be introduced solely to demonstrate the feature.

The [accepted watermark design](../pipeline/WATERMARKS.md) distinguishes successful loading from eligible incremental progress. Capped/custom/reference/backfill runs and runs with unusable returned timestamps may load successfully without a checkpoint. A non-NULL successful end describes an extraction cutoff, not the newest payload timestamp or a proof of completeness. Empty uncapped normal/full-refresh runs may advance; offset drift and source visibility delays can still hide records. Runtime timestamp/count gates and explicit modes have only offline validation so far.

## Observability signals

Useful lightweight signals include:

- run status;
- start/end timestamps;
- records fetched/loaded;
- source watermark range;
- dbt test failures;
- unexpected zero-record incremental runs when source behavior suggests otherwise.

These provide enough operational visibility for the project's scope without adding a dedicated observability platform.
