# Analytics App

## Purpose

Streamlit is the consumption/demo layer. Its job is to make the curated warehouse outputs tangible, not to perform data engineering work that belongs upstream.

## Current state

`app/` is a placeholder. No application is implemented.

## Data contract

The app should query dbt marts only.

It must not:

- call IGDB directly;
- parse raw JSON payloads;
- recreate joins already represented in dbt;
- calculate core business metrics differently from documented mart definitions.

## Recommended views

Keep the UI compact:

1. **Release trends** — releases over time with genre/platform filters.
2. **Genre/platform analysis** — counts and rating summaries with appropriate minimum rating-count safeguards.
3. **Company output** — developer/publisher output over time if the mart is retained.
4. **Game explorer** — searchable/filterable catalog backed by `mart_game_catalog`.

## Database access

Use a small shared query/connection helper. Credentials remain environment-backed. Prefer read-only database permissions for the app if adding a dedicated application user remains simple.

## Caching

Streamlit caching can be used for stable warehouse queries to keep the demo responsive. Do not cache in a way that hides pipeline updates indefinitely.

## AI summaries

An AI summary feature is optional and intentionally deferred. If added, it should summarize already-curated query results and should not become a dependency of the core application or pipeline.
