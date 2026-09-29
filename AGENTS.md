# AGENTS.md

## Purpose

This repository is an incremental data-engineering portfolio project. Codex should treat the documentation under `docs/` as the source of truth for architecture, current state, and task order.

## Required context before implementation

Before changing code, read:

1. `docs/CURRENT_STATE.md`
2. `docs/ARCHITECTURE.md`
3. `docs/ROADMAP.md`
4. the documentation page for the affected subsystem

`docs/portfolio/` is private interview/resume material and is not required for implementation.

## Task discipline

- Implement one roadmap task at a time unless explicitly asked otherwise.
- Keep changes small enough to review in roughly 15–30 minutes where practical.
- Do not implement future roadmap phases opportunistically.
- Do not rewrite working modules solely for stylistic preference.
- Prefer the simplest design that satisfies the documented architecture.

## Architecture boundaries

- Python owns source ingestion and raw loading.
- dbt owns analytics transformations.
- Airflow orchestrates reusable commands; business logic should not live only in DAG code.
- Streamlit reads curated dbt models; it does not call IGDB or transform raw payloads.
- PostgreSQL raw loads must remain idempotent.

## Code expectations

- Use modular, readable Python.
- Add type hints where they improve clarity.
- Add docstrings to public functions/classes and non-obvious helpers.
- Use logging instead of `print` for pipeline behavior.
- Keep secrets and tokens out of code/logs.
- Handle expected external failures explicitly.
- Avoid adding dependencies unless they materially simplify the task.

## Testing expectations

For every behavior change:

1. add or update relevant tests;
2. run the narrow affected tests first;
3. run the full applicable test suite before completion;
4. report the exact commands run and their results.

Normal unit tests must not require live IGDB access.

## Documentation expectations

Update documentation in the same change when implementation changes project truth.

- Update `docs/CURRENT_STATE.md` only for functionality that actually exists and has been verified.
- Check a roadmap item only after its implementation and validation are complete.
- Update architecture/subsystem docs when a design decision changes.
- Do not write planned behavior as though it is implemented.

## File safety

- Do not modify unrelated files.
- Do not delete working code without a task-specific reason.
- Never commit `.env`, credentials, local raw data, caches, generated dbt artifacts, or `docs/portfolio/`.
- If generated/private files are already tracked, report them before removing them from Git history/index unless explicitly authorized.

## Completion report

At the end of a task, provide:

- what changed;
- files created/modified;
- important design decisions;
- tests/verification commands and results;
- documentation/roadmap updates;
- any remaining caveats directly related to the task.
