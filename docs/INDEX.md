# IGDB Data Platform — Documentation

This directory is the source of truth for the project's architecture, implementation state, and delivery roadmap.

## Start here

- [Project overview](PROJECT_OVERVIEW.md) — purpose, scope, and success criteria.
- [Current state](CURRENT_STATE.md) — what is implemented now versus planned.
- [Architecture](ARCHITECTURE.md) — target system, data flow, and engineering principles.
- [Roadmap](ROADMAP.md) — ordered implementation plan designed for small Codex tasks.

## Pipeline

- [Ingestion](pipeline/INGESTION.md)
- [High-water-mark semantics](pipeline/WATERMARKS.md) — accepted design, persisted lookup, source windows, overlap replay, checkpoint gates, and explicit full-refresh/backfill behavior; live validation remains open.
- [Raw storage](pipeline/RAW_STORAGE.md)
- [dbt transformations](pipeline/DBT_TRANSFORMATIONS.md)
- [Orchestration](pipeline/ORCHESTRATION.md)
- [Analytics app](pipeline/ANALYTICS_APP.md)

## Engineering

- [Local development](engineering/LOCAL_DEVELOPMENT.md)
- [Testing](engineering/TESTING.md)
- [Data quality](engineering/DATA_QUALITY.md)

## Private portfolio notes

`docs/portfolio/` contains interview and resume notes for the project owner. It should remain local and be excluded from Git. The public documentation should stand on its own without it.

## Documentation rules

1. `CURRENT_STATE.md` describes reality, not intent.
2. `ARCHITECTURE.md` describes the target end state.
3. `ROADMAP.md` is the authoritative task order.
4. Update documentation in the same change that materially changes architecture or project status.
5. Never place credentials, tokens, personal notes, or interview-only material in public docs.
