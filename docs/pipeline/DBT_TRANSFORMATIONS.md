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

No dbt models or source definitions are implemented yet.

## Source layer

Declare each raw PostgreSQL table in source YAML. Source declarations should include descriptions and basic tests on stable identifiers where appropriate.

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

## Intermediate layer

Use intermediate models for reusable relationships and logic. Expected relationship areas are:

- game ↔ genre;
- game ↔ platform;
- game ↔ company with developer/publisher role.

Task 3.5 now preserves games `genres`, `platforms`, and `involved_companies` as ID arrays in raw JSONB. The first two reference the corresponding lookup IDs; the third references involved-company record IDs, whose `company` points to companies and whose `game`, `developer`, and `publisher` describe the association. Future dbt models will extract these arrays and resolve roles. Raw bounded samples are not required to contain all references; missing relationships must not be interpreted as verified absence of a real-world association. No dbt models or relationship tests are implemented yet.

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

## Documentation

Document:

- source purpose;
- model grain;
- important columns;
- metric definitions;
- relationship caveats;
- rating-count thresholds or filters used in marts.

A reviewer should be able to understand the model without reading every SQL file.

## Build contract

The target validation command is:

```bash
dbt build
```

It should build models and run associated tests as one reproducible transformation step.
