# Orchestration

## Purpose

Airflow coordinates already-runnable pipeline components. It should not become the only place where ingestion or transformation logic works.

## Current state

`dags/` exists but contains no DAG implementation.

## Target DAG

A simple end-to-end DAG is sufficient:

```text
start
  │
  ├─► ingest_genres ───────┐
  ├─► ingest_platforms ────┤
  ├─► ingest_companies ────┼─► ingest_games_and_relationships ─► dbt_build ─► end
  └────────────────────────┘
```

The exact dependency graph should follow actual source requirements. If all entity ingestion tasks are independent, they can run in parallel before `dbt_build`.

## Task design

Airflow tasks should invoke stable application entrypoints/commands. For example, an ingestion task should call the same Python CLI that a developer can execute locally.

Benefits:

- logic is testable without Airflow;
- debugging is simpler;
- orchestration code stays small;
- local/manual backfills remain possible.

## Scheduling

Choose an intentionally modest schedule appropriate for a portfolio/local source pipeline, such as daily. Document:

- schedule expression;
- timezone;
- `start_date`;
- whether `catchup` is enabled;
- retry count/delay;
- expected incremental behavior.

Avoid pretending a high-frequency schedule is required when the source/use case does not justify it.

## Failure behavior

- A failed ingestion task prevents dbt from running against a partially updated source set unless the dependency design explicitly allows it.
- Retries should be bounded.
- Task logs should identify the entity/run but never reveal secrets.
- Failed runs should remain visible in `ingestion_runs` where the failure occurs after run initialization.

## Backfills

The underlying ingestion CLI should expose full-refresh/backfill behavior. Airflow can invoke that behavior manually when needed rather than embedding separate extraction logic in the DAG.
