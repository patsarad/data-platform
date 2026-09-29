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

## Rating metrics

IGDB rating fields can be misleading when very few users contributed ratings. Analytics marts/app views that rank or compare ratings should include rating-count context and, where ranking is used, a documented minimum-count threshold or other explicit rule.

Do not present a raw average rating as equally reliable across vastly different rating counts.

## Many-to-many relationships

Games can relate to multiple genres/platforms/companies. Models must define their grain clearly so aggregations do not accidentally double-count games or ratings.

Every relationship/mart model should document whether a game can appear multiple times and how downstream aggregations should interpret that grain.

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
