# Testing Strategy

## Goal

Tests should protect pipeline behavior at the layer where failures are most meaningful, without requiring every test run to contact external services.

## Current Python unit tests

The repository currently tests:

- Twitch token acquisition/caching/expiration behavior;
- IGDB request headers, retries, and token refresh;
- reusable pagination: empty/partial pages, offset progression, ordered results, batch caps, and client-error propagation;
- games, genres, platforms, companies, and involved-companies query construction, default/custom fields, batch termination, and compatibility with the shared helper;
- immutable games/genres/platforms/companies/involved-companies contracts, source/raw key mappings, and isolation of per-call field overrides;
- JSONL serialization;
- environment configuration defaults/overrides;
- logger level configuration;
- raw-games connection settings; games/genres/platforms/companies/involved-companies table creation, upsert preparation, empty loads, and database failure propagation;
- run metadata DDL, UUIDs/UTC timestamps, counts, guarded terminal updates, and propagated execute/commit errors;
- optional source windows: explicit UTC cutoff/overlap calculations, bootstrap/reference reads, exact default/custom queries, frozen bounds across pages, payload fidelity, and invalid inputs;
- overlap replay preparation for games/companies/involved companies: ID-only conflict SQL, tied distinct IDs, changed/stale responses, input-order payloads and acknowledged counts;
- standalone watermark lookup: greatest successful non-NULL end, exact schema/entity SQL, modeled histories, propagated failures, and caller-owned transactions/connections;
- task 4.5 runtime selection: per-entity bootstrap/window lookup, fixed cutoff, start/end SQL parameters, capped/custom/direct-callback ineligibility, returned timestamp/count gates, empty success, raw/terminal failures, and all-mode composition;
- task 4.6 sequences and failures: consecutive bootstrap/overlap/no-change runs, runtime UTC/epoch conversion, failed-run retry, safe stage reporting, and all-mode retention of earlier eligible successes;
- CLI selection of each entity or all in deterministic order, per-entity limits/counts/archives, rejection before side effects, fail-fast retention of earlier successes, callback composition and defaults/options, direct runner use without CLI parsing, fetch/archive/storage wiring, output paths, UTC timestamps, preserved raw transaction boundaries, and isolated metadata connections;
- lifecycle failures across source/archive/raw/metadata stages, connection failures, and safe failure reporting that preserves the original exception.
- composed runner behavior using real games/genres/platforms/companies/involved-companies/pagination/archive/storage/metadata helpers: empty/full-page termination, repeated-ID prepared rows and counts, incomplete fetches, invalid-row preparation, and raw context-exit failure after the loader returns.

These tests use fake sessions/connections and are appropriate for fast local/CI execution.

From the repository root, with the Python 3.11 environment activated:

```bash
python -m pytest -q
```

For a focused check, append a test path, for example `python -m pytest -q tests/test_run_ingestion.py`. No `.env`, live credentials, or database is required. Phase 1 verified all 15 existing tests in a fresh Python 3.11 environment; no test or pipeline behavior changes were needed.

Task 2.1 adds pagination and games regression coverage. Run the affected tests before the full suite:

```bash
python -m pytest -q tests/test_pagination.py tests/test_fetch_games.py
python -m pytest -q
```

Verified September 25, 2026 using the existing Phase 1 Python 3.11.0 environment: 16 focused tests and all 28 tests passed; CLI help also passed. The exact verification commands were:

```bash
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_pagination.py tests/test_fetch_games.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m src.ingestion.run_ingestion --help
```

The temporary environment path is specific to this verification; use your activated Python 3.11 environment for normal development. Cache writes were disabled to preserve previously tracked generated artifacts. No live API/database checks were performed for task 2.1.

## Task 2.2 verification

Verified September 25, 2026 using the same Python 3.11.0 environment. The baseline ingestion-helper tests passed (2 tests). Storage coverage now lives in `tests/test_raw_games.py`; `tests/test_run_ingestion.py` exercises CLI wiring with the real storage helpers and a fake connection. The focused regression set also includes the unchanged games/pagination tests.

Exact commands, in validation order:

```bash
/private/tmp/data-platform-phase1-venv/bin/python --version
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_run_ingestion.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_raw_games.py tests/test_run_ingestion.py tests/test_fetch_games.py tests/test_pagination.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m src.ingestion.run_ingestion --help
git diff --check
```

The first post-extraction focused run had 27 passes and three failures caused by a new test assertion inspecting the entered cursor mock instead of its context manager. After correcting that assertion, the same focused command passed all 30 tests; the full suite then passed all 40 tests. CLI help and the diff whitespace check passed. Cache writes were disabled and existing tracked artifacts were preserved. No dependencies changed; no live IGDB or PostgreSQL checks were performed. These tests check SQL preparation, commit calls, and error/context propagation, not database-level idempotency or rollback.

## Task 2.3 verification

Verified September 25, 2026 using the existing Python 3.11.0 environment. Exact commands, in validation order:

```bash
/private/tmp/data-platform-phase1-venv/bin/python --version
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_raw_games.py tests/test_run_ingestion.py tests/test_fetch_games.py tests/test_pagination.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_entities.py tests/test_fetch_games.py tests/test_raw_games.py tests/test_run_ingestion.py tests/test_pagination.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m src.ingestion.run_ingestion --help
git diff --check
```

Results: 30 baseline focused tests passed, then 33 focused tests and all 43 unit tests passed after integration. CLI help and the whitespace check passed. New tests cover contract values/immutability and unchanged defaults after a custom-field query; the storage payload fixture includes `updated_at` while retaining exact SQL assertions. Existing query, pagination, raw schema, missing-field, empty-load, commit, and failure tests still pass.

No dependencies changed. Cache writes were disabled and existing user edits/generated artifacts were preserved. No live IGDB/PostgreSQL checks were performed; database-level idempotency and rollback remain outside this unit-test validation. The update-field contract does not implement incremental ingestion.

## Task 2.4 verification

Verified September 25, 2026 on Python 3.11.0, without changing dependencies. Exact commands in validation order:

```bash
/private/tmp/data-platform-phase1-venv/bin/python --version
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_entities.py tests/test_fetch_games.py tests/test_raw_games.py tests/test_run_ingestion.py tests/test_pagination.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_ingestion_runs.py tests/test_run_ingestion.py tests/test_raw_games.py tests/test_entities.py tests/test_fetch_games.py tests/test_pagination.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m src.ingestion.run_ingestion --help
git diff --check
```

Results: 33 baseline focused tests passed. The post-change focused command first passed 66 tests; it was repeated after adding the raw-load commit-failure case and passed all 67 tests. The full suite then passed all 77 tests. CLI help and the whitespace check passed. `tests/test_ingestion_runs.py` covers metadata SQL and helpers; expanded CLI tests cover real raw/metadata helper ordering using separate fake connections, default/custom archives, empty results, source and storage failures, success-record failure after a raw commit, and failure-reporting outages without masking errors or logging sensitive exception text.

No live API/PostgreSQL checks were performed. Fakes verify emitted SQL, guards, commit calls, and context exits; they do not prove database constraint enforcement, actual rollback, or commit outcomes after a connection loss. Bytecode and pytest cache writes were disabled to preserve tracked generated artifacts. Only task 2.4 was completed; broader generalized-path coverage remains task 2.6.

## Task 2.5 verification

Verified September 25, 2026 on the existing Python 3.11.0 environment. Exact commands in validation order (the focused baseline ran before changes):

```bash
/private/tmp/data-platform-phase1-venv/bin/python --version
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_ingestion_runs.py tests/test_run_ingestion.py tests/test_raw_games.py tests/test_entities.py tests/test_fetch_games.py tests/test_pagination.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_pipeline.py tests/test_ingestion_runs.py tests/test_run_ingestion.py tests/test_raw_games.py tests/test_entities.py tests/test_fetch_games.py tests/test_pagination.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m src.ingestion.run_ingestion --help
git diff --check
```

Results: 67 baseline focused tests, 71 post-refactor focused tests, and all 81 unit tests passed. CLI help and whitespace validation passed. New tests cover default/custom CLI callback composition, the existing zero batch cap, direct runner use without argument parsing, and acknowledged fetched/loaded counts. Existing CLI lifecycle tests retain their assertions while patching moved client/connection/metadata dependencies in `pipeline.py`.

No dependencies changed and no live IGDB/PostgreSQL calls were made. Bytecode and pytest cache writes were disabled, preserving tracked artifacts. Fakes validate SQL, calls, and context ordering; actual PostgreSQL rollback, constraints, and ambiguous commit outcomes remain unverified. Only task 2.5 was completed; the broader generalized-path test audit remains task 2.6.

## Task 2.6 coverage audit and verification

The audit found that the isolated behavior was already covered. The missing coverage was composition through `ingest_entity()` with the real helpers: existing CLI flow tests stubbed fetch/archive, and the direct runner test stubbed all callbacks and metadata helpers. Five new cases in `tests/test_pipeline.py` fill that gap without production changes or a second exhaustive lifecycle matrix.

| Area | Existing coverage retained | New composed-path coverage |
|---|---|---|
| Pagination termination | Empty/partial pages, offset/order, caps (including non-positive), client-error propagation | Full page followed by empty terminates before archive/load; a later-page error prevents partial archive/load and records zero counts |
| Empty results | Fetch returns an empty list; empty upsert skips cursor/commit; CLI reports zero-count success | Actual empty JSONL is created, raw DDL still runs, no upsert occurs, and real metadata helpers record zero-count success |
| Upsert preparation | Exact SQL, optional fields, iterable order, full JSONB, timestamp, missing ID before writes | Fetched payloads survive archive and row preparation; repeated IDs count as processed rows; invalid later row retains archive but allows only the DDL commit |
| Run metadata changes | Running insert, guarded terminal SQL, UUID/time/counts, execute/commit failures, stage failures and best-effort reporting | Same start UUID reaches success/failure through real helpers; raw context-exit failure retains the loader's acknowledged count and cannot report success |

Verified September 25, 2026 on the existing Python 3.11.0 environment. Exact commands in validation order:

```bash
/private/tmp/data-platform-phase1-venv/bin/python --version
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_pipeline.py tests/test_ingestion_runs.py tests/test_run_ingestion.py tests/test_raw_games.py tests/test_entities.py tests/test_fetch_games.py tests/test_pagination.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_pipeline.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_pipeline.py tests/test_ingestion_runs.py tests/test_run_ingestion.py tests/test_raw_games.py tests/test_entities.py tests/test_fetch_games.py tests/test_pagination.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
```

Results: 71 baseline focused tests passed before changes; then six runner tests, 76 focused tests, and all 86 unit tests passed. No test failures occurred. No production code or dependencies changed. Bytecode and pytest cache writes were disabled to preserve tracked artifacts; existing user edits were retained. Only task 2.6 was newly completed.

No live IGDB/PostgreSQL checks were performed. Fakes capture SQL, parameters, explicit commits, and context ordering; they do not execute SQL or simulate PostgreSQL constraints/rollback. The repeated-ID test verifies prepared rows and acknowledged counts, not database-level idempotency. Existing limitations around outages and ambiguous commits still apply; watermarks remain unused.

## Task 3.1 offline verification and smoke limitation

Verified September 25–26, 2026 using the existing Python 3.11.0 environment. No dependencies changed. Normal unit tests remain offline; bytecode and pytest cache writes were disabled to preserve tracked artifacts.

Exact test/CLI commands in validation order:

```bash
/private/tmp/data-platform-phase1-venv/bin/python --version
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_pipeline.py tests/test_ingestion_runs.py tests/test_run_ingestion.py tests/test_raw_games.py tests/test_entities.py tests/test_fetch_games.py tests/test_pagination.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_entities.py tests/test_fetch_genres.py tests/test_raw_genres.py tests/test_pipeline.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_pipeline.py tests/test_ingestion_runs.py tests/test_run_ingestion.py tests/test_raw_games.py tests/test_raw_genres.py tests/test_entities.py tests/test_fetch_games.py tests/test_fetch_genres.py tests/test_pagination.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m src.ingestion.run_ingestion --help
git diff --check
```

Results: **76 baseline focused**, **30 narrow affected**, **98 expanded focused**, and **108 total unit tests passed**. No test failures occurred. CLI help and the whitespace check passed. Existing games production code, CLI options, raw/metadata schemas, and lifecycle implementation were not modified.

Coverage added:

- minimal immutable genres contract and source/raw key mapping;
- exact default/custom genres queries, iterable fields across capped pages, and non-positive caps;
- JSONL payload fidelity, parent creation, empty archives, and propagated I/O errors;
- quoted schema/table/key identifiers, complete JSONB, optional attributes, conflict updates, iterable row order, and processed-row counts;
- empty/missing-ID loads and propagated schema/table/upsert/commit failures;
- existing composed runner cases parameterized for games and genres: durable metadata start before client creation, empty/full-page termination, archive/load fidelity, later-page error, invalid-row preparation, success after raw context exit, and raw exit failure preserving acknowledged counts. Existing best-effort failure-reporting tests remain in the unchanged games CLI suite. No watermark values are written.

These fakes verify emitted SQL, parameters, commits, and lifecycle ordering. They do not prove PostgreSQL constraint enforcement, actual rollback, or database-level repeated-load idempotency.

IGDB client ID and secret were checked for presence without displaying their values; both are configured. The first bounded connectivity probe was:

```bash
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python - <<'PY'
import psycopg
from src.utils.config import get_settings
s = get_settings()
try:
    with psycopg.connect(host=s.postgres_host, port=s.postgres_port, dbname=s.postgres_db, user=s.postgres_user, password=s.postgres_password, connect_timeout=5) as conn:
        print('PostgreSQL read-only connectivity check:', conn.execute('SELECT 1').fetchone() == (1,))
except psycopg.Error as error:
    print('PostgreSQL unavailable:', type(error).__name__)
PY
```

Result: `PostgreSQL unavailable: OperationalError`. Retried outside the network sandbox with sanitized error classification:

```bash
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python - <<'PY'
import psycopg
from src.utils.config import get_settings
s = get_settings()
try:
    with psycopg.connect(host=s.postgres_host, port=s.postgres_port, dbname=s.postgres_db, user=s.postgres_user, password=s.postgres_password, connect_timeout=5) as conn:
        print('PostgreSQL read-only connectivity check:', conn.execute('SELECT 1').fetchone() == (1,))
except psycopg.Error as error:
    message = str(error).lower()
    reason = next((label for text, label in [('connection refused', 'connection refused'), ('password authentication failed', 'authentication failed'), ('does not exist', 'configured database or role missing'), ('timed out', 'connection timeout'), ('operation not permitted', 'connection permission denied')] if text in message), 'connection failed')
    print('PostgreSQL unavailable:', type(error).__name__, '-', reason)
PY
```

Result: `PostgreSQL unavailable: OperationalError - connection refused`. Both probe commands exited zero because the diagnostic catches the error; that does **not** indicate connectivity or smoke success. A documentation-edit command initially failed due to a nested heredoc delimiter; its accidentally executed sandboxed probe reported connection permission denied. The edit was corrected using a distinct delimiter. At that point, no live IGDB request or raw database write had been performed, and task 3.1 remained unchecked. The service blocker was subsequently resolved and live verification completed as recorded below; later tasks remain untouched.

## Task 3.1 live smoke completion

Completed September 26, 2026. The user installed native Apple Silicon Homebrew PostgreSQL 17.11 and started its service. A read-only check found that the configured `postgres` role and `gaming_analytics` database were missing. Both were created using the existing settings, with the project role owning its database but without superuser, CREATEDB, or CREATEROLE privileges. Project TCP connectivity then returned `('gaming_analytics', 'postgres')`; the three privilege flags were all false. Passwords/tokens were not printed and `.env` was not modified. [Local development](LOCAL_DEVELOPMENT.md#local-postgresql-on-apple-silicon) records the service commands.

Before the live runs, these exact offline commands passed again, in order:

```bash
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_entities.py tests/test_fetch_genres.py tests/test_raw_genres.py tests/test_pipeline.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
```

Results: **30 passed**, then **108 passed**. No application code or dependencies changed during this service setup and validation follow-up.

Exact live smoke command, executed with network/local database access outside the sandbox:

```bash
PYTHONDONTWRITEBYTECODE=1 LOG_LEVEL=INFO /private/tmp/data-platform-phase1-venv/bin/python - <<'PY'
import json
import sys
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
import psycopg
from psycopg import sql
from src.entities import GENRES
from src.ingestion.fetch_genres import fetch_genres_batches, save_genres_to_jsonl
from src.ingestion.pipeline import ingest_entity
from src.storage.raw_genres import ensure_raw_genres_table, upsert_raw_genres
from src.utils.config import get_settings
from src.utils.logger import get_logger

s = get_settings()
logger = get_logger('genres_smoke')
def connect():
    return psycopg.connect(host=s.postgres_host, port=s.postgres_port, dbname=s.postgres_db, user=s.postgres_user, password=s.postgres_password, connect_timeout=5)

try:
    results = []
    previous_ids = None
    previous_times = {}
    for attempt in (1, 2):
        started = datetime.now(timezone.utc)
        stamp = started.strftime('%Y%m%dT%H%M%S%fZ')
        path = Path('data/raw') / f'raw_genres_{stamp}.jsonl'
        counts = ingest_entity(
            entity=GENRES, schema_name=s.postgres_schema, output_path=path,
            fetch_records=partial(fetch_genres_batches, batch_size=5, max_batches=1),
            archive_records=save_genres_to_jsonl, ensure_table=ensure_raw_genres_table,
            upsert_records=upsert_raw_genres, logger=logger,
        )
        records = [json.loads(line) for line in path.read_text().splitlines()]
        assert counts == (5, 5) and len(records) == 5
        ids = [record['id'] for record in records]
        assert ids == sorted(set(ids))
        with connect() as conn:
            rows = conn.execute(sql.SQL('SELECT igdb_id, name, slug, payload, fetched_at FROM {}.raw_genres WHERE igdb_id = ANY(%s) ORDER BY igdb_id').format(sql.Identifier(s.postgres_schema)), (ids,)).fetchall()
            assert len(rows) == len(records)
            for row, record in zip(rows, records):
                assert row[:4] == (record['id'], record.get('name'), record.get('slug'), record)
                assert row[4].astimezone(timezone.utc) >= started
                if previous_times:
                    assert row[4] > previous_times[row[0]]
            total, distinct = conn.execute(sql.SQL('SELECT count(*), count(DISTINCT igdb_id) FROM {}.raw_genres').format(sql.Identifier(s.postgres_schema))).fetchone()
            assert total == distinct == 5
            runs = conn.execute(sql.SQL('SELECT run_id, status, records_fetched, records_loaded, source_watermark_start, source_watermark_end, error_message, started_at, completed_at FROM {}.ingestion_runs WHERE entity = %s AND started_at >= %s ORDER BY started_at').format(sql.Identifier(s.postgres_schema)), ('genres', started)).fetchall()
            assert len(runs) == 1
            run = runs[0]
            assert run[1:7] == ('succeeded', 5, 5, None, None, None)
            assert run[8] >= run[7] >= started
        if previous_ids is not None:
            assert ids == previous_ids
        previous_ids = ids
        previous_times = {row[0]: row[4] for row in rows}
        result = {'attempt': attempt, 'archive': str(path), 'counts': counts, 'ids': ids, 'raw_rows': total, 'run_id': str(run[0]), 'status': run[1], 'watermarks': [None, None]}
        results.append(result)
        print(json.dumps(result))
    Path('/private/tmp/data-platform-genres-smoke-results.json').write_text(json.dumps(results, indent=2))
    print('PASS: live genres archive, JSONB fidelity, metadata, and repeated-load idempotency.')
except Exception as error:
    print('Genres smoke failed:', type(error).__name__)
    sys.exit(1)
PY
```

The command exited **0** with `PASS: live genres archive, JSONB fidelity, metadata, and repeated-load idempotency.` Both runs fetched and loaded five genres, IDs `[2, 4, 5, 7, 8]`. Each full archived object matched its JSONB row and extracted name/slug; the second run increased `fetched_at` without increasing the five-row/distinct-ID count. Both run records had `succeeded`, fetched/loaded counts 5/5, NULL watermarks, and no error.

| Run | UTC archive filename under ignored `data/raw/` | Metadata run ID |
|---|---|---|
| 1 | `raw_genres_20260926T061358457070Z.jsonl` | `4081cfe6-89fa-4aa3-8366-28b78c3f24fc` |
| 2 | `raw_genres_20260926T061359155111Z.jsonl` | `1c36239d-bac0-4d4e-af52-cd965537f1b6` |

This harness assumes an otherwise empty `raw_genres` table and no concurrent genres run. For routine smoke checks against a populated database, use the bounded invocation in [Ingestion](../pipeline/INGESTION.md#genres-task-31) and compare only sampled IDs. Live validation here covers successful DDL/commits, archives, upserts, and terminal metadata; it does not establish full endpoint coverage, rollback under failure, or ambiguous commit recovery. Normal tests remain offline. Task **3.1 is complete**; no later task was started.

## Task 3.2 verification

Completed September 26, 2026 on Python 3.11.0, using the existing environment without dependency changes. The baseline focused tests passed before implementation; the affected tests ran before the full suite. Exact offline commands:

```bash
/private/tmp/data-platform-phase1-venv/bin/python --version
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_entities.py tests/test_fetch_genres.py tests/test_raw_genres.py tests/test_pipeline.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_entities.py tests/test_fetch_platforms.py tests/test_raw_platforms.py tests/test_pipeline.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m src.ingestion.run_ingestion --help
git diff --check
```

Results: **30 baseline focused**, **36 affected**, and **130 total tests passed**. CLI help and whitespace validation passed. No unit-test failures occurred. New coverage follows genres: immutable contract, exact/default/custom queries, iterable overrides across pages, caps, empty/Unicode/nested archives, I/O failures, quoted SQL, optional fields, complete JSONB, conflict updates, missing IDs before writes, empty loads, and propagated execute/commit failures. Existing composed cases now also exercise platforms through real pagination/archive/storage/metadata helpers, including durable start, success after raw context exit, later-page failure, invalid rows, and raw exit failure. Existing CLI tests protect best-effort failure reporting. Bytecode/cache writes were disabled and tracked artifacts retained.

Live validation used existing settings/credentials and databases; no credentials were printed. The first service startup command immediately ran the harness and failed its initial connection probe with `OperationalError`, before ingestion. Its EXIT trap stopped the service. A bounded readiness loop was then added. The next attempt ingested five platforms but the manual harness failed an assertion that required the returned TIMESTAMPTZ display offset to be zero. PostgreSQL can present the same instant in its session timezone; the check was corrected to require a timezone-aware value and compare instants. That attempt's archive and committed data were retained, and the service was again stopped. No production change was needed for either validation issue.

The corrected harness below was saved at `/private/tmp/data-platform-platforms-smoke.py`. It runs two five-record requests with `batch_size=5, max_batches=1`, compares captured source records to archives and JSONB, checks extracted fields and timestamp refresh, accounts for existing raw IDs, and checks running metadata through an independent connection before fetching. Terminal validation targets the same run UUID. It assumes no concurrent platforms ingestion during the check; it does not empty or recreate tables.

```bash
cat > /private/tmp/data-platform-platforms-smoke.py <<'PY'
"""Manual task 3.2 validation; run from the repository root, outside pytest."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql

from src.entities import PLATFORMS
from src.ingestion.fetch_platforms import fetch_platforms_batches, save_platforms_to_jsonl
from src.ingestion.pipeline import ingest_entity
from src.storage.raw_platforms import ensure_raw_platforms_table, upsert_raw_platforms
from src.utils.config import get_settings
from src.utils.logger import get_logger

settings = get_settings()
logger = get_logger('platforms_smoke')
raw_table = sql.Identifier(settings.postgres_schema, PLATFORMS.raw_table)
run_table = sql.Identifier(settings.postgres_schema, 'ingestion_runs')


def connect():
    """Bound the validation connection without changing production defaults."""
    return psycopg.connect(
        host=settings.postgres_host, port=settings.postgres_port,
        dbname=settings.postgres_db, user=settings.postgres_user,
        password=settings.postgres_password, connect_timeout=5,
    )


try:
    with connect() as connection:
        exists = connection.execute('SELECT to_regclass(%s)', (raw_table.as_string(),)).fetchone()[0]
        initial_ids = set() if exists is None else {
            row[0] for row in connection.execute(sql.SQL('SELECT igdb_id FROM {}').format(raw_table))
        }
    previous_ids = None
    previous_times = {}
    results = []
    for attempt in (1, 2):
        started = datetime.now(timezone.utc)
        stamp = started.strftime('%Y%m%dT%H%M%S%fZ')
        path = Path('data/raw') / f'raw_platforms_{stamp}.jsonl'
        captured = []
        run_ids = []

        def fetch(client):
            """Verify start visibility on a separate connection before source work."""
            with connect() as connection:
                runs = connection.execute(sql.SQL(
                    'SELECT run_id, status, records_fetched, records_loaded, '
                    'source_watermark_start, source_watermark_end, completed_at '
                    'FROM {} WHERE entity = %s AND started_at >= %s'
                ).format(run_table), ('platforms', started)).fetchall()
                assert len(runs) == 1
                assert runs[0][1:] == ('running', 0, 0, None, None, None)
                run_ids.append(runs[0][0])
            records = fetch_platforms_batches(client, batch_size=5, max_batches=1)
            captured.extend(records)
            return records

        counts = ingest_entity(
            entity=PLATFORMS, schema_name=settings.postgres_schema, output_path=path,
            fetch_records=fetch, archive_records=save_platforms_to_jsonl,
            ensure_table=ensure_raw_platforms_table, upsert_records=upsert_raw_platforms,
            logger=logger,
        )
        records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        assert counts == (5, 5) and len(records) == 5
        assert records == captured
        ids = [record['id'] for record in records]
        assert ids == sorted(set(ids))
        with connect() as connection:
            rows = connection.execute(sql.SQL(
                'SELECT igdb_id, name, slug, payload, fetched_at FROM {} '
                'WHERE igdb_id = ANY(%s) ORDER BY igdb_id'
            ).format(raw_table), (ids,)).fetchall()
            assert len(rows) == len(records)
            for row, record in zip(rows, records):
                assert row[:4] == (record['id'], record.get('name'), record.get('slug'), record)
                assert row[4].tzinfo is not None
                assert row[4] >= started
                if previous_times:
                    assert row[4] > previous_times[row[0]]
            total, distinct = connection.execute(sql.SQL(
                'SELECT count(*), count(DISTINCT igdb_id) FROM {}'
            ).format(raw_table)).fetchone()
            assert total == distinct == len(initial_ids | set(ids))
            run = connection.execute(sql.SQL(
                'SELECT status, records_fetched, records_loaded, source_watermark_start, '
                'source_watermark_end, error_message, started_at, completed_at '
                'FROM {} WHERE run_id = %s'
            ).format(run_table), (run_ids[0],)).fetchone()
            assert run[:6] == ('succeeded', 5, 5, None, None, None)
            assert run[7] >= max(row[4] for row in rows) >= run[6] >= started
        if previous_ids is not None:
            assert ids == previous_ids
        previous_ids = ids
        previous_times = {row[0]: row[4] for row in rows}
        result = {
            'attempt': attempt, 'archive': str(path), 'counts': counts, 'ids': ids,
            'raw_rows': total, 'run_id': str(run_ids[0]), 'status': run[0],
            'watermarks': [None, None],
        }
        results.append(result)
        logger.info('Verified smoke: %s', json.dumps(result))
    Path('/private/tmp/data-platform-platforms-smoke-results.json').write_text(json.dumps(results, indent=2))
    logger.info('PASS: two bounded platforms runs; durable starts, source/archive/JSONB fidelity, upserts, metadata, NULL watermarks.')
except Exception as error:
    logger.error('Platforms smoke failed (%s at line %s).', type(error).__name__, error.__traceback__.tb_lineno)
    sys.exit(1)
PY
```

Exact successful live command (executed with network/local database access outside the sandbox):

```bash
set -e
cleanup_platforms_smoke() {
    validation_status=$?
    trap - EXIT
    /opt/homebrew/bin/brew services stop postgresql@17 || exit 1
    exit "$validation_status"
}
trap cleanup_platforms_smoke EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
/opt/homebrew/bin/brew services run postgresql@17
for attempt in {1..20}; do
    if /opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432; then
        break
    fi
    sleep 0.5
done
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
PYTHONDONTWRITEBYTECODE=1 LOG_LEVEL=INFO PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python - < /private/tmp/data-platform-platforms-smoke.py
```

Result: **exit 0**. Both verified runs fetched/loaded five records, IDs `[3, 4, 5, 6, 7]`. Source objects matched JSONL and JSONB; extracted fields matched; aware fetch timestamps advanced on repeat. `raw_platforms` remained at five rows and five distinct IDs. Each running record was visible before source work and finished `succeeded` with 5/5 counts, no error, and NULL watermarks.

| Run | UTC archive filename under ignored `data/raw/` | Metadata run ID |
|---|---|---|
| 1 | `raw_platforms_20260926T184718082755Z.jsonl` | `4a2720fd-8147-4daa-9461-1c62fa6a9232` |
| 2 | `raw_platforms_20260926T184718591842Z.jsonl` | `d7d1dc14-5d8a-4c26-983c-a0243d09bde5` |

Final service checks:

```bash
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
```

`services info` exited 0 with `Running: false`, `Loaded: false`, and `Schedulable: false`. `pg_isready` exited 2 with `localhost:5432 - no response`, as expected for the intentionally stopped server. Every validation attempt stopped PostgreSQL on exit; automatic login startup was never enabled. Database files and existing settings were retained.

Task **3.2 is complete**. Games/genres production code, CLI arguments/defaults, existing schemas, runner transactions, and failure semantics are unchanged. No later task was implemented. Live coverage is bounded to successful sample ingestion; full endpoint coverage, failure rollback, and ambiguous commit recovery remain unverified. Normal tests remain offline; watermarks remain NULL.

## Task 3.3 verification

Completed September 26, 2026 on Python 3.11.0 with no dependency changes. Exact offline commands, in order:

```bash
/private/tmp/data-platform-phase1-venv/bin/python --version
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_entities.py tests/test_fetch_platforms.py tests/test_raw_platforms.py tests/test_pipeline.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_entities.py tests/test_fetch_companies.py tests/test_raw_companies.py tests/test_pipeline.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m src.ingestion.run_ingestion --help
git diff --check
```

Results: **36 baseline focused**, **42 affected**, and **152 total tests passed**. CLI help and whitespace validation passed. No unit-test or live-validation failures occurred. New offline coverage verifies the immutable minimal contract, exact/default/custom queries, iterable overrides across pages, caps, JSONL fidelity/empty archives/I/O failures, quoted SQL, complete JSONB, optional fields, conflict updates, empty/missing-ID loads, and propagated execute/commit failures. Existing composed runner cases now also exercise companies, covering durable start, archive/load fidelity, success after raw context exit, later-page failure, invalid rows, and raw exit failure with acknowledged counts. Existing CLI tests retain best-effort failure-reporting coverage. Bytecode/cache writes were disabled to preserve tracked artifacts.

The live harness below was saved to `/private/tmp/data-platform-companies-smoke.py` and executed from the repository root outside pytest. Each of its two invocations uses `batch_size=5, max_batches=1`. It checks the running record on an independent connection before fetching and validates terminal metadata for that same UUID. It accounts for preexisting IDs, verifies rows outside the sample remain unchanged, and compares timezone-aware instants without assuming a PostgreSQL display offset. It assumes no concurrent companies ingestion during validation. Existing credentials/settings are used without printing secrets; tables are never cleared and databases are never recreated.

```bash
cat > /private/tmp/data-platform-companies-smoke.py <<'PY'
"""Manual task 3.3 validation; run from the repository root, outside pytest."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql

from src.entities import COMPANIES
from src.ingestion.fetch_companies import fetch_companies_batches, save_companies_to_jsonl
from src.ingestion.pipeline import ingest_entity
from src.storage.raw_companies import ensure_raw_companies_table, upsert_raw_companies
from src.utils.config import get_settings
from src.utils.logger import get_logger

settings = get_settings()
logger = get_logger('companies_smoke')
raw_table = sql.Identifier(settings.postgres_schema, COMPANIES.raw_table)
run_table = sql.Identifier(settings.postgres_schema, 'ingestion_runs')


def connect():
    """Bound the validation connection without changing production defaults."""
    return psycopg.connect(
        host=settings.postgres_host, port=settings.postgres_port,
        dbname=settings.postgres_db, user=settings.postgres_user,
        password=settings.postgres_password, connect_timeout=5,
    )


try:
    with connect() as connection:
        exists = connection.execute('SELECT to_regclass(%s)', (raw_table.as_string(),)).fetchone()[0]
        initial_rows = {} if exists is None else {
            row[0]: row for row in connection.execute(sql.SQL(
                'SELECT igdb_id, name, slug, payload, fetched_at FROM {}'
            ).format(raw_table))
        }
        initial_ids = set(initial_rows)
    previous_ids = None
    previous_times = {}
    results = []
    for attempt in (1, 2):
        started = datetime.now(timezone.utc)
        stamp = started.strftime('%Y%m%dT%H%M%S%fZ')
        path = Path('data/raw') / f'raw_companies_{stamp}.jsonl'
        captured = []
        run_ids = []

        def fetch(client):
            """Verify start visibility on a separate connection before source work."""
            with connect() as connection:
                runs = connection.execute(sql.SQL(
                    'SELECT run_id, status, records_fetched, records_loaded, '
                    'source_watermark_start, source_watermark_end, completed_at '
                    'FROM {} WHERE entity = %s AND started_at >= %s'
                ).format(run_table), ('companies', started)).fetchall()
                assert len(runs) == 1
                assert runs[0][1:] == ('running', 0, 0, None, None, None)
                run_ids.append(runs[0][0])
            records = fetch_companies_batches(client, batch_size=5, max_batches=1)
            captured.extend(records)
            return records

        counts = ingest_entity(
            entity=COMPANIES, schema_name=settings.postgres_schema, output_path=path,
            fetch_records=fetch, archive_records=save_companies_to_jsonl,
            ensure_table=ensure_raw_companies_table, upsert_records=upsert_raw_companies,
            logger=logger,
        )
        records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        assert counts == (5, 5) and len(records) == 5
        assert records == captured
        assert all(set(COMPANIES.fields) <= record.keys() for record in records)
        ids = [record['id'] for record in records]
        assert ids == sorted(set(ids))
        with connect() as connection:
            rows = connection.execute(sql.SQL(
                'SELECT igdb_id, name, slug, payload, fetched_at FROM {} '
                'WHERE igdb_id = ANY(%s) ORDER BY igdb_id'
            ).format(raw_table), (ids,)).fetchall()
            assert len(rows) == len(records)
            for row, record in zip(rows, records):
                assert row[:4] == (record['id'], record.get('name'), record.get('slug'), record)
                assert row[4].tzinfo is not None
                assert row[4] >= started
                if previous_times:
                    assert row[4] > previous_times[row[0]]
            total, distinct = connection.execute(sql.SQL(
                'SELECT count(*), count(DISTINCT igdb_id) FROM {}'
            ).format(raw_table)).fetchone()
            assert total == distinct == len(initial_ids | set(ids))
            current_rows = {row[0]: row for row in connection.execute(sql.SQL(
                'SELECT igdb_id, name, slug, payload, fetched_at FROM {}'
            ).format(raw_table))}
            assert set(current_rows) == initial_ids | set(ids)
            assert all(current_rows[key] == initial_rows[key] for key in initial_ids - set(ids))
            run = connection.execute(sql.SQL(
                'SELECT status, records_fetched, records_loaded, source_watermark_start, '
                'source_watermark_end, error_message, started_at, completed_at '
                'FROM {} WHERE run_id = %s'
            ).format(run_table), (run_ids[0],)).fetchone()
            assert run[:6] == ('succeeded', 5, 5, None, None, None)
            assert run[7] >= max(row[4] for row in rows) >= run[6] >= started
        if previous_ids is not None:
            assert ids == previous_ids
        previous_ids = ids
        previous_times = {row[0]: row[4] for row in rows}
        result = {
            'attempt': attempt, 'archive': str(path), 'counts': counts, 'ids': ids,
            'initial_raw_rows': len(initial_ids), 'raw_rows': total, 'run_id': str(run_ids[0]), 'status': run[0],
            'watermarks': [None, None],
        }
        results.append(result)
        logger.info('Verified smoke: %s', json.dumps(result))
    assert len({result['run_id'] for result in results}) == 2
    Path('/private/tmp/data-platform-companies-smoke-results.json').write_text(json.dumps(results, indent=2))
    logger.info('PASS: two bounded companies runs; durable starts, source/archive/JSONB fidelity, upserts, metadata, NULL watermarks.')
except Exception as error:
    logger.error('Companies smoke failed (%s at line %s).', type(error).__name__, error.__traceback__.tb_lineno)
    sys.exit(1)
PY
```

Exact live command (network/local database access outside the sandbox):

```bash
set -e
cleanup_companies_smoke() {
    validation_status=$?
    trap - EXIT
    /opt/homebrew/bin/brew services stop postgresql@17 || exit 1
    exit "$validation_status"
}
trap cleanup_companies_smoke EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
/opt/homebrew/bin/brew services run postgresql@17
for attempt in {1..20}; do
    if /opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432; then
        break
    fi
    sleep 0.5
done
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
PYTHONDONTWRITEBYTECODE=1 LOG_LEVEL=INFO PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python - < /private/tmp/data-platform-companies-smoke.py
```

Result: **exit 0**. Readiness initially reported no response, then accepting connections before any database connection. Both runs fetched/loaded five companies, IDs `[1, 2, 3, 4, 5]`. Source objects matched JSONL and JSONB; extracted fields matched; aware fetch timestamps advanced on repeat. `raw_companies` was initially absent and ended at five rows/five distinct IDs after each run. Both independently visible running records became `succeeded` with 5/5 counts, no error, and NULL watermarks.

| Run | UTC archive filename under ignored `data/raw/` | Metadata run ID |
|---|---|---|
| 1 | `raw_companies_20260926T231135106408Z.jsonl` | `e0bfae35-e06c-4a04-a94b-ebea6b889ca2` |
| 2 | `raw_companies_20260926T231135866412Z.jsonl` | `cb7499a5-1fa0-4fcb-8b0e-4ed4dcfc752f` |

Final service verification commands:

```bash
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
```

`services info` succeeded with `Running: false`, `Loaded: false`, `Schedulable: false`; `pg_isready` exited **2** with `localhost:5432 - no response`, the expected stopped state. The smoke command stopped PostgreSQL through its EXIT trap. Login startup was never enabled; existing database files and settings remain intact.

Task **3.3 is complete**. Existing entity modules, games CLI/defaults, existing schemas, runner transactions, and lifecycle semantics are unchanged. Pre-task SHA-256 comparisons verified all files outside the task's source/test/documentation edits remained unchanged, including tracked artifacts. Only task 3.3 was implemented. The live sample establishes successful ingestion and repeated upserts; full endpoint coverage, failure rollback, and ambiguous commit recovery remain unverified. Watermarks remain NULL.

## Task 3.4 verification

Completed September 26, 2026 locally (September 27 UTC) on Python 3.11.0 without dependency changes. Exact offline commands in order:

```bash
/private/tmp/data-platform-phase1-venv/bin/python --version
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_entities.py tests/test_fetch_companies.py tests/test_raw_companies.py tests/test_pipeline.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_entities.py tests/test_fetch_involved_companies.py tests/test_raw_involved_companies.py tests/test_pipeline.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m src.ingestion.run_ingestion --help
git diff --check
```

Results: **42 baseline focused**, **48 affected**, and **174 total tests passed**. CLI help and whitespace checks passed. No offline or live validation failures occurred. Bytecode/cache writes were disabled, preserving tracked artifacts.

New coverage verifies the immutable relationship contract; default/custom queries and iterable fields across pages; caps; complete JSONL and JSONB fidelity including false roles, missing optional fields, Unicode and nested values; minimal three-column SQL; relationship record IDs distinct from shared game/company references; conflict updates; empty loads; missing IDs before writes; and propagated DDL/upsert/commit failures. Existing composed runner cases now also exercise involved companies, verifying durable start, success after raw context exit, acknowledged counts, later-page failure, invalid rows, and raw exit failure. Existing CLI regressions protect best-effort failure reporting and unchanged arguments/defaults.

The following manual harness was saved outside the repository and run via stdin from the repository root. Each of two runs requests `batch_size=5, max_batches=1`. It compares source/archive/JSONB, validates relationship IDs and boolean roles, checks running metadata from an independent connection, compares aware timestamp instants, accounts for existing rows, and verifies rows outside the sample remain unchanged. It assumes no concurrent ingestion for this entity. It neither clears tables nor requires referenced games/companies to exist. Existing credentials are used without printing secrets.

```bash
cat > /private/tmp/data-platform-involved_companies-smoke.py <<'PY'
"""Manual task 3.4 validation; run from the repository root, outside pytest."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql

from src.entities import INVOLVED_COMPANIES
from src.ingestion.fetch_involved_companies import fetch_involved_companies_batches, save_involved_companies_to_jsonl
from src.ingestion.pipeline import ingest_entity
from src.storage.raw_involved_companies import ensure_raw_involved_companies_table, upsert_raw_involved_companies
from src.utils.config import get_settings
from src.utils.logger import get_logger

settings = get_settings()
logger = get_logger('involved_companies_smoke')
raw_table = sql.Identifier(settings.postgres_schema, INVOLVED_COMPANIES.raw_table)
run_table = sql.Identifier(settings.postgres_schema, 'ingestion_runs')


def connect():
    """Bound the validation connection without changing production defaults."""
    return psycopg.connect(
        host=settings.postgres_host, port=settings.postgres_port,
        dbname=settings.postgres_db, user=settings.postgres_user,
        password=settings.postgres_password, connect_timeout=5,
    )


try:
    with connect() as connection:
        exists = connection.execute('SELECT to_regclass(%s)', (raw_table.as_string(),)).fetchone()[0]
        initial_rows = {} if exists is None else {
            row[0]: row for row in connection.execute(sql.SQL(
                'SELECT igdb_id, payload, fetched_at FROM {}'
            ).format(raw_table))
        }
        initial_ids = set(initial_rows)
    previous_ids = None
    previous_times = {}
    results = []
    for attempt in (1, 2):
        started = datetime.now(timezone.utc)
        stamp = started.strftime('%Y%m%dT%H%M%S%fZ')
        path = Path('data/raw') / f'raw_involved_companies_{stamp}.jsonl'
        captured = []
        run_ids = []

        def fetch(client):
            """Verify start visibility on a separate connection before source work."""
            with connect() as connection:
                runs = connection.execute(sql.SQL(
                    'SELECT run_id, status, records_fetched, records_loaded, '
                    'source_watermark_start, source_watermark_end, completed_at '
                    'FROM {} WHERE entity = %s AND started_at >= %s'
                ).format(run_table), ('involved_companies', started)).fetchall()
                assert len(runs) == 1
                assert runs[0][1:] == ('running', 0, 0, None, None, None)
                run_ids.append(runs[0][0])
            records = fetch_involved_companies_batches(client, batch_size=5, max_batches=1)
            captured.extend(records)
            return records

        counts = ingest_entity(
            entity=INVOLVED_COMPANIES, schema_name=settings.postgres_schema, output_path=path,
            fetch_records=fetch, archive_records=save_involved_companies_to_jsonl,
            ensure_table=ensure_raw_involved_companies_table, upsert_records=upsert_raw_involved_companies,
            logger=logger,
        )
        records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        assert counts == (5, 5) and len(records) == 5
        assert records == captured
        assert all(set(INVOLVED_COMPANIES.fields) <= record.keys() for record in records)
        for record in records:
            assert type(record['game']) is int and record['game'] > 0
            assert type(record['company']) is int and record['company'] > 0
            assert type(record['developer']) is bool
            assert type(record['publisher']) is bool
            assert type(record['updated_at']) is int
        ids = [record['id'] for record in records]
        assert ids == sorted(set(ids))
        with connect() as connection:
            rows = connection.execute(sql.SQL(
                'SELECT igdb_id, payload, fetched_at FROM {} '
                'WHERE igdb_id = ANY(%s) ORDER BY igdb_id'
            ).format(raw_table), (ids,)).fetchall()
            assert len(rows) == len(records)
            for row, record in zip(rows, records):
                assert row[:2] == (record['id'], record)
                assert row[2].tzinfo is not None
                assert row[2] >= started
                if previous_times:
                    assert row[2] > previous_times[row[0]]
            total, distinct = connection.execute(sql.SQL(
                'SELECT count(*), count(DISTINCT igdb_id) FROM {}'
            ).format(raw_table)).fetchone()
            assert total == distinct == len(initial_ids | set(ids))
            current_rows = {row[0]: row for row in connection.execute(sql.SQL(
                'SELECT igdb_id, payload, fetched_at FROM {}'
            ).format(raw_table))}
            assert set(current_rows) == initial_ids | set(ids)
            assert all(current_rows[key] == initial_rows[key] for key in initial_ids - set(ids))
            run = connection.execute(sql.SQL(
                'SELECT status, records_fetched, records_loaded, source_watermark_start, '
                'source_watermark_end, error_message, started_at, completed_at '
                'FROM {} WHERE run_id = %s'
            ).format(run_table), (run_ids[0],)).fetchone()
            assert run[:6] == ('succeeded', 5, 5, None, None, None)
            assert run[7] >= max(row[2] for row in rows) >= run[6] >= started
        if previous_ids is not None:
            assert ids == previous_ids
        previous_ids = ids
        previous_times = {row[0]: row[2] for row in rows}
        result = {
            'attempt': attempt, 'archive': str(path), 'counts': counts, 'ids': ids,
            'initial_raw_rows': len(initial_ids), 'raw_rows': total, 'run_id': str(run_ids[0]), 'status': run[0],
            'watermarks': [None, None],
            'relationships': [{key: record[key] for key in ('id', 'game', 'company', 'developer', 'publisher')} for record in records],
        }
        results.append(result)
        logger.info('Verified smoke: %s', json.dumps(result))
    assert len({result['run_id'] for result in results}) == 2
    Path('/private/tmp/data-platform-involved_companies-smoke-results.json').write_text(json.dumps(results, indent=2))
    logger.info('PASS: two bounded involved_companies runs; durable starts, source/archive/JSONB fidelity, upserts, metadata, NULL watermarks.')
except Exception as error:
    logger.error('Involved companies smoke failed (%s at line %s).', type(error).__name__, error.__traceback__.tb_lineno)
    sys.exit(1)
PY
```

Exact live command (network/local database access outside the sandbox):

```bash
set -e
cleanup_involved_companies_smoke() {
    validation_status=$?
    trap - EXIT
    /opt/homebrew/bin/brew services stop postgresql@17 || exit 1
    exit "$validation_status"
}
trap cleanup_involved_companies_smoke EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
/opt/homebrew/bin/brew services run postgresql@17
for attempt in {1..20}; do
    if /opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432; then
        break
    fi
    sleep 0.5
done
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
PYTHONDONTWRITEBYTECODE=1 LOG_LEVEL=INFO PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python - < /private/tmp/data-platform-involved_companies-smoke.py
```

Result: **exit 0**. Readiness reported accepting connections before the harness connected. Both runs fetched/loaded five records, IDs `[2, 6, 7, 8, 9]`. Every source object matched its archive and stored JSONB. `updated_at` was returned. The initially absent raw table contained five rows/five distinct IDs after each run, and all sampled timestamps advanced on repeat. Both independently visible running records became `succeeded` with 5/5 counts, NULL watermarks, and no error.

| Record ID | Game ID | Company ID | Developer | Publisher |
|---|---|---|---|---|
| 2 | 38 | 1 | false | true |
| 6 | 2 | 3 | true | false |
| 7 | 2 | 4 | false | true |
| 8 | 38 | 7 | true | false |
| 9 | 37 | 11 | true | false |

| Run | UTC archive filename under ignored `data/raw/` | Metadata run ID |
|---|---|---|
| 1 | `raw_involved_companies_20260927T003501694576Z.jsonl` | `46bfb0e1-f4bb-4e6d-abc8-ebf4b9660186` |
| 2 | `raw_involved_companies_20260927T003502445651Z.jsonl` | `87ab4942-e5d7-42e8-8fdd-7789ca740e1d` |

Final service verification commands:

```bash
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
```

`services info` exited **0** with `Running: false`, `Loaded: false`, and `Schedulable: false`. `pg_isready` exited **2**, reporting `localhost:5432 - no response`, as expected for the stopped service. The EXIT trap stopped PostgreSQL; automatic login startup was never enabled. Existing database files/settings were preserved.

Task **3.4 is complete**. Existing entity modules, schemas, CLI/defaults, shared runner, transactions, and failure semantics are unchanged. Pre-task SHA-256 comparisons verified unrelated files, user edits, and tracked artifacts remain unchanged. The live sample validates successful ingestion and repeated upserts, not full endpoint coverage, failure rollback, or ambiguous commit recovery. Watermarks remain NULL. No later roadmap task was implemented.

## Task 3.5 verification

Completed September 26, 2026 locally (September 27 UTC), using the existing Python 3.11.0 environment with no dependency changes. Only the games default field contract changed in production. Existing CLI options/defaults, custom field behavior, schemas, pagination, runner connections/transactions, durable start, success after raw context exit, and best-effort failure reporting remain in place. Watermarks remain NULL.

Exact offline commands, in order (the focused command ran both before and after the changes):

```bash
/private/tmp/data-platform-phase1-venv/bin/python --version
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_entities.py tests/test_fetch_games.py tests/test_raw_games.py tests/test_pipeline.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m src.ingestion.run_ingestion --help
git diff --check
```

Results: **50 baseline focused**, **55 affected**, and **179 total offline tests passed**. CLI help and whitespace checks passed. Existing default-contract assertions now require all twelve fields; custom tuple/list field overrides still produce exactly their supplied fields across pages. Four composed cases verify relationship arrays, source order/duplicates, missing keys, empty arrays, mixed explicit nulls, extra nested/Unicode data, unchanged source records, complete JSONL/JSONB row preparation, and preserved metadata lifecycle. Existing SQL and failure tests remain intact. Unit tests make no live service calls. Bytecode and pytest cache writes were disabled.

The live harness below uses existing settings/credentials without printing secrets. It captures two default-field runs at `batch_size=5, max_batches=1`, checks starts through an independent connection, then compares source/archive/JSONB, integer ID arrays, schema, timestamp instants, distinct IDs, and terminal metadata. It snapshots rows before each run, allows existing IDs, and checks rows outside each sample stay unchanged. It assumes no concurrent games ingestion and never clears tables or requires referenced records to exist.

If either default sample lacks a nonempty array for any added relationship, it performs exactly two additional five-record runs using this **validation-only** filter with the same fields and pagination helper:

```text
where genres != null & platforms != null & involved_companies != null;
```

The filter checks [documented null predicates](https://api-docs.igdb.com/#filters); it does not change production defaults. Coverage must still pass on the actual filtered response. This fallback was **not used**: both default samples exercised all three relationships for every game.

Save and run the manual harness outside pytest, from the repository root:

```bash
cat > /private/tmp/data-platform-games-smoke.py <<'PY'
"""Manual task 3.5 validation; execute via stdin from the repository root."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql

from src.entities import GAMES
from src.ingestion.fetch_games import build_games_query, fetch_games_batches, save_games_to_jsonl
from src.ingestion.pagination import fetch_paginated
from src.ingestion.pipeline import ingest_entity
from src.storage.raw_games import ensure_raw_games_table, upsert_raw_games
from src.utils.config import get_settings
from src.utils.logger import get_logger

settings = get_settings()
logger = get_logger('games_smoke')
raw_table = sql.Identifier(settings.postgres_schema, GAMES.raw_table)
run_table = sql.Identifier(settings.postgres_schema, 'ingestion_runs')
relationships = ('genres', 'platforms', 'involved_companies')


def connect():
    """Bound validation connections using existing settings without printing them."""
    return psycopg.connect(
        host=settings.postgres_host, port=settings.postgres_port,
        dbname=settings.postgres_db, user=settings.postgres_user,
        password=settings.postgres_password, connect_timeout=5,
    )


def raw_rows(connection):
    """Snapshot existing rows without changing the database."""
    exists = connection.execute('SELECT to_regclass(%s)', (raw_table.as_string(),)).fetchone()[0]
    return {} if exists is None else {row[0]: row for row in connection.execute(sql.SQL(
        'SELECT igdb_id, name, slug, payload, fetched_at FROM {}'
    ).format(raw_table))}


def run_pair(mode):
    """Repeat one bounded sample; use a filter only if default coverage is insufficient."""
    previous_ids = None
    results = []
    for attempt in (1, 2):
        with connect() as connection:
            before_rows = raw_rows(connection)
        started = datetime.now(timezone.utc)
        path = Path('data/raw') / f'raw_games_{started:%Y%m%dT%H%M%S%fZ}.jsonl'
        captured = []
        run_ids = []

        def fetch(client):
            """Check independently visible durable start, then capture source objects."""
            with connect() as connection:
                runs = connection.execute(sql.SQL(
                    'SELECT run_id, status, records_fetched, records_loaded, '
                    'source_watermark_start, source_watermark_end, completed_at '
                    'FROM {} WHERE entity = %s AND started_at >= %s'
                ).format(run_table), ('games', started)).fetchall()
                assert len(runs) == 1
                assert runs[0][1:] == ('running', 0, 0, None, None, None)
                run_ids.append(runs[0][0])
            if mode == 'default':
                records = fetch_games_batches(client, batch_size=5, max_batches=1)
            else:
                records = fetch_paginated(
                    client, endpoint=GAMES.endpoint, batch_size=5, max_batches=1,
                    build_query=lambda limit, offset: build_games_query(limit=limit, offset=offset)
                    + ' where genres != null & platforms != null & involved_companies != null;',
                )
            captured.extend(records)
            return records

        counts = ingest_entity(
            entity=GAMES, schema_name=settings.postgres_schema, output_path=path,
            fetch_records=fetch, archive_records=save_games_to_jsonl,
            ensure_table=ensure_raw_games_table, upsert_records=upsert_raw_games, logger=logger,
        )
        records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        assert counts == (5, 5) and len(records) == 5
        assert records == captured
        for record in records:
            for field in relationships:
                if field in record:
                    assert isinstance(record[field], list)
                    assert all(type(value) is int and value > 0 for value in record[field])
        coverage = {field: sum(bool(record.get(field)) for record in records) for field in relationships}
        ids = [record['id'] for record in records]
        assert ids == sorted(set(ids))
        with connect() as connection:
            current_rows = raw_rows(connection)
            rows = [current_rows[key] for key in ids]
            for row, record in zip(rows, records):
                assert row[:4] == (record['id'], record.get('name'), record.get('slug'), record)
                assert row[4].tzinfo is not None and row[4] >= started
                if row[0] in before_rows:
                    assert row[4] > before_rows[row[0]][4]
            total, distinct = connection.execute(sql.SQL(
                'SELECT count(*), count(DISTINCT igdb_id) FROM {}'
            ).format(raw_table)).fetchone()
            assert total == distinct == len(set(before_rows) | set(ids))
            assert set(current_rows) == set(before_rows) | set(ids)
            assert all(current_rows[key] == before_rows[key] for key in set(before_rows) - set(ids))
            columns = connection.execute(
                'SELECT column_name FROM information_schema.columns '
                'WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position',
                (settings.postgres_schema, GAMES.raw_table),
            ).fetchall()
            assert columns == [(name,) for name in ('igdb_id', 'name', 'slug', 'payload', 'fetched_at')]
            run = connection.execute(sql.SQL(
                'SELECT status, records_fetched, records_loaded, source_watermark_start, '
                'source_watermark_end, error_message, started_at, completed_at '
                'FROM {} WHERE run_id = %s'
            ).format(run_table), (run_ids[0],)).fetchone()
            assert run[:6] == ('succeeded', 5, 5, None, None, None)
            assert run[7] >= max(row[4] for row in rows) >= run[6] >= started
        if previous_ids is not None:
            assert ids == previous_ids
        previous_ids = ids
        result = {
            'mode': mode, 'attempt': attempt, 'archive': str(path), 'counts': counts,
            'ids': ids, 'rows_before': len(before_rows), 'rows_after': total,
            'run_id': str(run_ids[0]), 'status': run[0], 'watermarks': [None, None],
            'coverage': coverage,
            'relationships': [{key: record[key] for key in ('id', *relationships) if key in record}
                              for record in records],
        }
        results.append(result)
        logger.info('Verified smoke: %s', json.dumps(result))
    return results


try:
    results = run_pair('default')
    if not all(all(result['coverage'].values()) for result in results):
        logger.info('Default sample lacks relationship coverage; trying a bounded filtered pair.')
        filtered = run_pair('relationships-present')
        results.extend(filtered)
        assert all(all(result['coverage'].values()) for result in filtered)
    assert len({result['run_id'] for result in results}) == len(results)
    Path('/private/tmp/data-platform-games-smoke-results.json').write_text(json.dumps(results, indent=2))
    logger.info('PASS: repeated games ingestion, relationship coverage, fidelity, upserts, metadata, NULL watermarks.')
except Exception as error:
    logger.error('Games smoke failed (%s at line %s).', type(error).__name__, error.__traceback__.tb_lineno)
    sys.exit(1)
PY
```

Exact live command (executed with network/local database access outside the sandbox):

```bash
set -e
cleanup_games_smoke() {
    validation_status=$?
    trap - EXIT
    /opt/homebrew/bin/brew services stop postgresql@17 || exit 1
    exit "$validation_status"
}
trap cleanup_games_smoke EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
/opt/homebrew/bin/brew services run postgresql@17
for attempt in {1..20}; do
    if /opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432; then
        break
    fi
    sleep 0.5
done
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
PYTHONDONTWRITEBYTECODE=1 LOG_LEVEL=INFO PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python - < /private/tmp/data-platform-games-smoke.py
```

Result: **exit 0**. Readiness reported accepting connections before the harness connected. Both runs fetched and loaded five games, IDs `[1, 2, 3, 4, 5]`. All five returned nonempty integer arrays for `genres`, `platforms`, and `involved_companies`; source objects, JSONL, and JSONB matched completely, including array order. The table initially had zero rows, then five rows/five distinct IDs after both runs. On repeat all five timestamps advanced, comparing timezone-aware instants without requiring a particular display offset. Both independently visible running rows became `succeeded` with 5/5 counts, no error, and NULL watermarks. The five-column games schema was confirmed.

| Run | UTC archive filename under ignored `data/raw/` | Metadata run ID |
|---|---|---|
| 1 | `raw_games_20260927T010620461583Z.jsonl` | `e324160b-982c-432a-a84f-f60f7dfd2406` |
| 2 | `raw_games_20260927T010621096116Z.jsonl` | `c992b87e-2fb1-4a40-965e-e9d0b5cd8430` |

Example: game 2 returned `genres=[13, 31]`, `platforms=[6]`, `involved_companies=[7, 6, 265431]`. The latter values identify involved-company records, not company IDs. This task fetched no additional endpoints and did not require those referenced rows to exist in the bounded lookup samples.

Final service verification commands:

```bash
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
```

`services info` exited **0** with `Running: false`, `Loaded: false`, `Schedulable: false`. `pg_isready` exited **2**, reporting `localhost:5432 - no response`, as expected. The EXIT trap stopped PostgreSQL; automatic login startup was never enabled. Existing database files/settings and credentials were retained.

Task **3.5 is complete**. No offline or live validation failures occurred; an initial temporary harness-generation attempt had an indentation error before any service startup or source/database access and was replaced with the syntax-checked harness above. Pre-task file hashes were compared after the work to verify unrelated files, user edits, and tracked artifacts remained unchanged. The five-record sample does not establish full source coverage, reference completeness, failure rollback, or ambiguous commit recovery. Missing/empty/null relationship states were verified offline, not observed in this live sample. At that point task 3.6 and all later roadmap work remained unimplemented; task 3.6 verification follows.

## Task 3.6 verification

Completed September 26, 2026 locally (September 27 UTC), using the existing Python 3.11.0 environment without dependency changes. Production changes are confined to CLI composition. Existing entity contracts, fetchers, writers, loaders, and shared lifecycle runner are unchanged.

Exact offline commands (the focused command ran before and after implementation):

```bash
/private/tmp/data-platform-phase1-venv/bin/python --version
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_run_ingestion.py tests/test_pipeline.py tests/test_ingestion_runs.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m src.ingestion.run_ingestion --help
git diff --check
```

Results: **71 baseline focused**, **88 affected**, and **196 total offline tests passed**. CLI help and whitespace checks passed. The 17 new cases cover all five contracts/callbacks, separate timestamped paths and single-entity overrides, the exact existing default games path, rejection of unknown entities and ambiguous all-mode paths before side effects, deterministic all-mode execution through real fetch/archive/storage/metadata helpers, per-entity caps/counts, and a third-entity fetch/raw-exit/completion failure retaining the first two successes and never invoking later entities. Existing defaults/options, zero-cap, acknowledged counts, and best-effort failure-reporting regressions remain intact. Fake API/database boundaries keep normal tests offline; bytecode/cache writes were disabled to preserve tracked artifacts.

The manual harness below invokes the **actual CLI as a subprocess twice**, each with `--entity all --batch-size 5 --max-batches 1`, using existing settings/credentials without printing secrets. Before each command it snapshots existing rows/metadata and hashes existing archives. It checks only five new archives/run rows, complete archive/JSONB equality, original schemas, duplicate-free upserts accounting for existing IDs, strictly refreshed timezone-aware timestamp instants, sequential terminal/start times, succeeded 5/5 metadata, NULL watermarks, and the three games relationship arrays. It never clears tables, recreates databases, or requires referenced records to exist. It assumes no concurrent ingestion.

Save this harness outside the repository and run via stdin from the repository root:

```bash
cat > /private/tmp/data-platform-cli-smoke.py <<'PY'
"""Manual task 3.6 check: run via stdin from the repository root, outside pytest."""
import hashlib
import json
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql

from src.entities import GAMES, GENRES, PLATFORMS, COMPANIES, INVOLVED_COMPANIES
from src.utils.config import get_settings
from src.utils.logger import get_logger

entities = (GAMES, GENRES, PLATFORMS, COMPANIES, INVOLVED_COMPANIES)
settings = get_settings()
logger = get_logger('cli_smoke')
run_table = sql.Identifier(settings.postgres_schema, 'ingestion_runs')


def connect():
    """Use existing credentials silently, with a bounded connection timeout."""
    return psycopg.connect(
        host=settings.postgres_host, port=settings.postgres_port,
        dbname=settings.postgres_db, user=settings.postgres_user,
        password=settings.postgres_password, connect_timeout=5,
    )


def snapshot(connection, table):
    """Read complete existing rows; absent tables are empty, never recreated here."""
    if connection.execute('SELECT to_regclass(%s)', (table.as_string(),)).fetchone()[0] is None:
        return {}
    return {row[0]: row for row in connection.execute(sql.SQL('SELECT * FROM {}').format(table))}


def archives():
    """Hash existing archives to detect overwrites as well as new files."""
    return {path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in Path('data/raw').glob('raw_*.jsonl')}


try:
    results = []
    previous_ids = {}
    for attempt in (1, 2):
        with connect() as connection:
            before = {entity.endpoint: snapshot(connection, sql.Identifier(settings.postgres_schema, entity.raw_table))
                      for entity in entities}
            old_runs = snapshot(connection, run_table)
        old_archives = archives()
        started = datetime.now(timezone.utc)
        command = [sys.executable, '-m', 'src.ingestion.run_ingestion',
                   '--entity', 'all', '--batch-size', '5', '--max-batches', '1']
        logger.info('Actual CLI attempt %s: %s', attempt, ' '.join(command))
        completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
        # Do not echo exception traces or connection details from a failed subprocess.
        assert completed.returncode == 0, 'CLI returned a nonzero status'
        new_archives = archives()
        assert all(new_archives.get(path) == digest for path, digest in old_archives.items())
        paths = set(new_archives) - set(old_archives)
        assert len(paths) == 5
        with connect() as connection:
            current_runs = snapshot(connection, run_table)
            assert all(current_runs.get(key) == value for key, value in old_runs.items())
            runs = connection.execute(sql.SQL(
                'SELECT run_id, entity, status, records_fetched, records_loaded, '
                'source_watermark_start, source_watermark_end, error_message, started_at, completed_at '
                'FROM {} WHERE started_at >= %s ORDER BY started_at'
            ).format(run_table), (started,)).fetchall()
            assert [run[1] for run in runs] == [entity.endpoint for entity in entities]
            assert len(set(current_runs) - set(old_runs)) == 5
            for index, (entity, run) in enumerate(zip(entities, runs)):
                matching = [path for path in paths if path.name.startswith(entity.raw_table + '_')]
                assert len(matching) == 1
                path = matching[0]
                datetime.strptime(path.name, entity.raw_table + '_%Y%m%dT%H%M%SZ.jsonl')
                records = [json.loads(line) for line in path.read_text().splitlines()]
                assert len(records) == 5
                ids = [record['id'] for record in records]
                assert ids == sorted(set(ids))
                if attempt == 2:
                    assert ids == previous_ids[entity.endpoint]
                previous_ids[entity.endpoint] = ids
                table = sql.Identifier(settings.postgres_schema, entity.raw_table)
                current = snapshot(connection, table)
                initial = before[entity.endpoint]
                assert set(current) == set(initial) | set(ids)
                assert all(current[key] == initial[key] for key in set(initial) - set(ids))
                total, distinct = connection.execute(sql.SQL(
                    'SELECT count(*), count(DISTINCT igdb_id) FROM {}'
                ).format(table)).fetchone()
                assert total == distinct == len(set(initial) | set(ids))
                assert run[2:8] == ('succeeded', 5, 5, None, None, None)
                assert run[8].tzinfo is not None and run[9].tzinfo is not None
                assert run[9] >= run[8] >= started
                if index:
                    assert run[8] >= runs[index - 1][9]
                expected_columns = ['igdb_id', 'payload', 'fetched_at'] if entity is INVOLVED_COMPANIES else ['igdb_id', 'name', 'slug', 'payload', 'fetched_at']
                columns = connection.execute(
                    'SELECT column_name FROM information_schema.columns '
                    'WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position',
                    (settings.postgres_schema, entity.raw_table),
                ).fetchall()
                assert [column[0] for column in columns] == expected_columns
                for record in records:
                    row = current[record['id']]
                    assert row[-2] == record  # Complete JSONB, including arrays and optional fields.
                    assert row[-1].tzinfo is not None and run[8] <= row[-1] <= run[9]
                    if record['id'] in initial:
                        assert row[-1] > initial[record['id']][-1]
                    if entity is not INVOLVED_COMPANIES:
                        assert row[1:3] == (record.get('name'), record.get('slug'))
                coverage = None
                if entity is GAMES:
                    coverage = {field: sum(bool(record.get(field)) for record in records)
                                for field in ('genres', 'platforms', 'involved_companies')}
                    assert all(coverage.values())
                    assert all(type(value) is int for record in records for field in coverage
                               for value in record.get(field, []))
                result = dict(attempt=attempt, entity=entity.endpoint, archive=str(path), ids=ids,
                              rows_before=len(initial), rows_after=total, run_id=str(run[0]),
                              counts=list(run[3:5]), status=run[2], watermarks=[None, None],
                              relationship_coverage=coverage)
                results.append(result)
                logger.info('Verified: %s', json.dumps(result))
    assert len({result['archive'] for result in results}) == 10
    assert len({result['run_id'] for result in results}) == 10
    Path('/private/tmp/data-platform-cli-smoke-results.json').write_text(json.dumps(results, indent=2))
    logger.info('PASS: two actual all-entity CLI runs; archives, JSONB, upserts, timestamps, metadata, NULL watermarks.')
except Exception as error:
    logger.error('CLI smoke failed: %s at line %s.', type(error).__name__, traceback.extract_tb(error.__traceback__)[-1].lineno)
    sys.exit(1)
PY
```

The harness and shell wrapper were syntax-checked before service startup (`ast.parse()` for the Python file and `bash -n /private/tmp/data-platform-cli-smoke.sh`). Exact live wrapper saved to `/private/tmp/data-platform-cli-smoke.sh`:

```bash
#!/bin/bash
set -e
cleanup_cli_smoke() {
    validation_status=$?
    trap - EXIT
    /opt/homebrew/bin/brew services stop postgresql@17 || exit 1
    exit "$validation_status"
}
trap cleanup_cli_smoke EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
/opt/homebrew/bin/brew services run postgresql@17
for attempt in {1..20}; do
    if /opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432; then
        break
    fi
    sleep 0.5
done
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
PYTHONDONTWRITEBYTECODE=1 LOG_LEVEL=INFO PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python - < /private/tmp/data-platform-cli-smoke.py
```

Executed with network/local database access outside the sandbox:

```bash
bash /private/tmp/data-platform-cli-smoke.sh
```

The harness launched this exact command twice:

```bash
/private/tmp/data-platform-phase1-venv/bin/python -m src.ingestion.run_ingestion --entity all --batch-size 5 --max-batches 1
```

Result: **exit 0**, both CLI invocations and every assertion passed. Readiness changed from no response to accepting connections before the harness connected. Every raw table initially contained five records and retained five rows/five distinct IDs after each command. Both attempts returned the same IDs per entity: games `[1, 2, 3, 4, 5]`, genres `[2, 4, 5, 7, 8]`, platforms `[3, 4, 5, 6, 7]`, companies `[1, 2, 3, 4, 5]`, involved_companies `[2, 6, 7, 8, 9]`. All sampled timestamps advanced relative to the pre-run snapshot, including the repeat. Full archived payloads matched JSONB, including array order; extracted name/slug matched where applicable. Each of the ten new metadata rows succeeded with 5/5 counts, no error, and NULL watermarks. All five games contained nonempty integer arrays for all three relationship fields on both attempts. All preexisting archive hashes and metadata rows were unchanged.

| Attempt | UTC archive filename under ignored `data/raw/` | Metadata run ID |
|---|---|---|
| 1 | `raw_games_20260927T025706Z.jsonl` | `d6bbd853-9542-4a22-b541-56d3dfe30b6f` |
| 1 | `raw_genres_20260927T025707Z.jsonl` | `525a4a01-c0ed-4692-92cd-4385cecc6c00` |
| 1 | `raw_platforms_20260927T025707Z.jsonl` | `af2656ee-4530-43d1-9d82-9028a7c2afec` |
| 1 | `raw_companies_20260927T025708Z.jsonl` | `81228f44-8220-446e-9087-7639a1d43d24` |
| 1 | `raw_involved_companies_20260927T025708Z.jsonl` | `38124826-2106-4ee4-bf79-7f145bcf6452` |
| 2 | `raw_games_20260927T025709Z.jsonl` | `d278b68f-9719-41b3-8b50-466bb07d8732` |
| 2 | `raw_genres_20260927T025710Z.jsonl` | `6eb0359b-752d-4981-a924-38b571dbc9b1` |
| 2 | `raw_platforms_20260927T025710Z.jsonl` | `e47ebff7-f420-46c4-81b7-f6fb31c8108f` |
| 2 | `raw_companies_20260927T025711Z.jsonl` | `5d0b84dc-5d80-4caf-8dea-13dc3b3e9205` |
| 2 | `raw_involved_companies_20260927T025711Z.jsonl` | `6063c83c-daa7-49c7-935a-f546f81344bb` |

The EXIT trap stopped PostgreSQL on completion (also runs on validation failure). Final verification commands:

```bash
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
```

`services info` exited **0** with `Running: false`, `Loaded: false`, `Schedulable: false`. `pg_isready` exited **2**, `localhost:5432 - no response`, the expected stopped state. Login startup was never enabled; existing databases/settings/credentials were retained. A before/after SHA-256 comparison verified all existing files outside this task’s CLI/test/documentation edits remained unchanged, including user edits and tracked artifacts.

**Task 3.6 is complete.** No offline or live validation failures occurred. This is a five-record sample per endpoint, not full endpoint or reference coverage. It checks complete archive/JSONB fidelity, not an independent capture of the wire response; source-to-archive fidelity remains covered by offline composition and earlier direct-runner live checks. This subprocess harness validates terminal metadata; durable-start visibility and raw-context-exit ordering are covered by unchanged runner regressions and previous live checks. Fail-fast/failure-reporting behavior is exercised offline; live failures, rollback, and ambiguous commit recovery were not induced. All existing rows belonged to the sampled IDs, so the assertion protecting unsampled rows was vacuous in this database. The CLI retains games’ second-resolution filename format; same-entity invocations within one second can overwrite the same default filename, while distinct entities always have separate prefixes. No incremental behavior or later roadmap work was implemented.

## Task 4.1 design verification

Completed September 26, 2026. The [accepted watermark design](../pipeline/WATERMARKS.md) was checked against all five entity contracts/query builders, offset pagination, CLI composition, shared runner, raw loaders, metadata helpers, and their existing tests. Official IGDB field/filter/sort/pagination references were reviewed; timestamp-unit inference and source-consistency assumptions are distinguished from documented behavior. No application/test/dependency/schema changes were needed.

Exact regression and review commands:

```bash
/private/tmp/data-platform-phase1-venv/bin/python --version
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_run_ingestion.py tests/test_pipeline.py tests/test_ingestion_runs.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task41-review/verify_design.py
git diff --check
git diff --no-index --check /dev/null docs/pipeline/WATERMARKS.md
/opt/homebrew/bin/brew services info postgresql@17
```

Results: Python **3.11.0**, **88 focused tests passed**, then **196 total tests passed**. The temporary review-only helper checked **76 relative links/heading anchors** in changed docs, example epoch conversions, the future query's bounds, inclusive/exclusive ties, five scenario outcomes, whitespace in all changed documents, and SHA-256 preservation of unrelated files. It also saved a before/after documentation diff because `docs/` was already untracked at task start. `git diff --check` exited 0; the new-file `--no-index --check` emitted no whitespace diagnostics and exited 1 because the file differs from `/dev/null`, as expected. Official links were checked against the fetched documentation; the future query was reviewed for documented syntax, not executed against IGDB. The helper and snapshots live outside the repository and are not a new runtime tool or test suite.

Service inspection reported `Running: false`, `Loaded: false`, `Schedulable: false`. PostgreSQL was never started and no live ingestion/database writes occurred. Bytecode/pytest cache writes were disabled; user edits and tracked artifacts remain intact. These regressions protect the state at task 4.1, not later watermark behavior. At that point only roadmap 4.1 was newly complete; the [implementation status matrix](../pipeline/WATERMARKS.md#implementation-status) now records later progress. Runtime was then unfiltered from offset zero with NULL watermarks.

## Task 4.2 lookup verification

Completed September 27, 2026 on Python 3.11.0. Only `src/storage/ingestion_runs.py`, `tests/test_ingestion_runs.py`, and technical documentation changed. No dependencies, schema, runner, CLI, source queries, or write helpers changed.

Exact verification commands, with narrow tests before the full offline suite:

```bash
/private/tmp/data-platform-phase1-venv/bin/python --version
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_ingestion_runs.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
/opt/homebrew/bin/brew services info postgresql@17
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task42-review/verify_task.py
git diff --check
```

Results: **41 metadata tests passed**, then **217 total offline tests passed** (21 new cases). No test failures occurred. Service inspection reported `Running: false`, `Loaded: false`, `Schedulable: false`. PostgreSQL was never started; no live ingestion, database writes, or live database validation occurred. Bytecode and pytest cache writes were disabled.

The existing `MagicMock` connection/cursor approach now asserts the complete aggregate SELECT, schema quoting (including embedded quotes), exact bound entity values (including injection-like text), success/non-NULL predicates, and no other executed SQL. Modeled histories cover an eligible end, empty history, legacy NULL-only successes, failed/running-only history, mixed exclusions, later NULL-ended/older-ended successes, and reordered history. Tests verify the returned datetime/None, cursor cleanup, propagated connection/execute/missing-table/fetch/cleanup errors, and no commit, rollback, close, connection context, or transaction-context calls.

**Coverage boundary:** the fake computes an expected aggregate result in Python only after asserting the emitted SQL. Scoping is verified through exact SQL identifiers and parameters; the fake does not execute SQL, isolate databases/schemas, or implement PostgreSQL ordering/NULL semantics. Future PostgreSQL integration must verify actual `MAX(TIMESTAMPTZ)`/NULL behavior, entity/schema isolation, driver adaptation, transaction visibility and committed-history durability. The caller must supply a connection reading committed history without pending metadata writes; a SELECT can implicitly begin a driver transaction even though the helper manages none.

The temporary review script passed **80 relative documentation links/heading anchors**, the lookup example's syntax/signature, unchanged query examples and epoch values, whitespace, and SHA-256 preservation of **99 files outside the 10 task files**. Before/after snapshots and `task42.diff` under `/private/tmp/data-platform-task42-review/` include changes to already-untracked docs/source/tests that ordinary `git diff` omits. The task diff passed reverse applicability/whitespace validation; `git diff --check` exited 0 for existing tracked changes. These are review artifacts outside the repository, not new project tooling.

At that point only roadmap 4.2 was newly complete and tasks 4.3–4.7 remained deferred. Runtime never calls the lookup; default queries remain unfiltered from offset zero and watermarks stay NULL.

## Task 4.3 window verification

Completed September 27, 2026 on Python 3.11.0, with no new dependencies. Added `tests/test_windows.py` and `tests/test_fetch_windows.py`; existing tests remain unchanged. Exact verification commands, with narrow tests before the full offline suite:

```bash
/private/tmp/data-platform-phase1-venv/bin/python --version
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_windows.py tests/test_fetch_windows.py tests/test_fetch_games.py tests/test_fetch_companies.py tests/test_fetch_involved_companies.py tests/test_fetch_genres.py tests/test_fetch_platforms.py tests/test_pagination.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
/opt/homebrew/bin/brew services info postgresql@17
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task43-review/verify_task.py
git diff --check
```

Results: **144 affected tests passed**, then **315 total offline tests passed** (98 new parameterized cases). No test failures occurred. Bytecode and pytest cache writes were disabled. PostgreSQL was never started; service inspection reported `Running: false`, `Loaded: false`, `Schedulable: false`. No live ingestion, database writes, or live database validation occurred.

Coverage asserts unchanged complete default queries, full unfiltered bootstrap with its retained cutoff, unfiltered reference queries, overlap relative to W even after a long outage, epoch clamping, timezone conversion, whole-second cutoff flooring, and rejection of `U <= W`. Invalid/naive/pre-epoch time inputs, fractional watermarks, invalid/incomplete bounds, and immutability are covered. Supported fetchers use identical lower-inclusive/upper-exclusive predicates across offset pages, preserve ID sorting and all stopping/cap rules, propagate later-page errors, and keep exact tuple/list/iterator custom projections without appending timestamps. Queued tied/missing/null/malformed/out-of-window timestamps and nested data are returned unchanged.

**Coverage boundary:** fake clients record queries and return queued pages; they do not interpret predicates or simulate IGDB filtering. Out-of-window fake rows deliberately test payload preservation, not live selection. These tests do not establish source timestamp quality, API boundary behavior, snapshot consistency, overlap completeness, or database replay safety. Existing full-suite regressions retain CLI/default unfiltered queries, counts, archive/load behavior, transactions, and NULL-watermark SQL. Eligibility and runtime lookup/window wiring remain deferred.

The temporary review script passed **93 relative documentation links/heading anchors**, executed the offline window/bootstrap example, matched documented query output, checked whitespace and unchanged roadmap checkboxes, and verified SHA-256 preservation of **97 existing files outside the 15 task files**. Before/after snapshots and `task43.diff` under `/private/tmp/data-platform-task43-review/` include the docs and fetchers already untracked at task start. They are review artifacts, not new project tooling. Only roadmap 4.3 is newly complete; tasks 4.4–4.7 remain unchecked.

## Task 4.4 overlap upsert verification

Completed September 27, 2026 on Python 3.11.0. The coverage audit found no task-specific production defect: all three loaders already prepare ordered, unconditional primary-key upserts. Added only `tests/test_raw_overlap.py` and technical documentation; existing tests and production files are unchanged.

| Contract | Existing coverage retained | Focused additions |
|---|---|---|
| Identity and updates | Entity mappings, primary-key DDL, exact INSERT/conflict SQL, nonkey updates in raw-loader tests | Two explicitly calculated overlapping extractions through real fetch/pagination/load helpers; same ID with same/newer/stale/missing/null timestamps retains its conflict key |
| Payloads and order | Optional fields, JSONB preparation, games arrays, relationship IDs/false roles; repeated-ID runner counts | Tied distinct IDs across pages, shared game/company references, changed references under the same record ID, complete replacement payloads, nested/array/false/null values, repeated IDs in unsorted input order |
| Counts and transactions | Empty/no-cursor/no-commit behavior; missing-ID preparation, write/commit failures; runner archive order, separate DDL/load commits, raw-context exit and terminal counts | Replayed rows count again, independent of cursor `rowcount`; each nonempty helper call emits one ordered `executemany()` then one commit call |
| Runtime boundary | CLI defaults/all-mode ordering, reference reads, metadata SQL and NULL watermarks | No runtime wiring; optional windows are passed directly by tests only |

Exact commands from the repository root (the baseline command ran before edits; the affected command passed both before and after refining the replay fixture):

```bash
/private/tmp/data-platform-phase1-venv/bin/python --version
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_raw_games.py tests/test_raw_companies.py tests/test_raw_involved_companies.py tests/test_pipeline.py tests/test_fetch_windows.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_raw_overlap.py tests/test_raw_games.py tests/test_raw_companies.py tests/test_raw_involved_companies.py tests/test_pipeline.py tests/test_fetch_windows.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
/opt/homebrew/bin/brew services info postgresql@17
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task44-64_ocejc/verify_task.py
git diff --check
```

Results: **120 baseline affected tests**, **138 affected tests**, then **333 total offline tests passed** (18 new parameterized cases), with no failures. Bytecode and pytest cache writes were disabled. Service inspection reported `Running: false`, `Loaded: false`, `Schedulable: false`. PostgreSQL was never started; no live ingestion, database writes, or live database validation occurred.

**Coverage boundary:** queued fake clients do not interpret predicates; missing/null responses deliberately test preservation, not IGDB selection. Mock cursors record SQL and bound rows without modeling stored rows. Exact unconditional conflict SQL and input-order parameters request last-upsert semantics; they do not prove live PostgreSQL constraint enforcement, database idempotency, rollback, durability, or source completeness. Later stale responses can overwrite newer payloads because no source-version comparison exists. Complete payload assertions inspect the JSONB wrapper and JSON round-trip, not driver adaptation or stored JSONB.

Before/after snapshots and `task44.diff` under `/private/tmp/data-platform-task44-64_ocejc/` cover all seven task files, including six documentation files already untracked at task start. The temporary review script checks relative documentation links/anchors, executes the offline window/bootstrap example, compares documented query output, checks task whitespace/diff applicability and roadmap checkbox scope, and verifies preservation of the other 106 existing files, including tracked generated artifacts and user changes. These are review artifacts outside the repository. Only task 4.4 is newly checked; tasks 4.5–4.7 remain unchecked. CLI/shared-runner incremental ingestion stays inactive with NULL watermarks.

## Task 4.5 runtime checkpoint verification

Completed September 28, 2026 on Python 3.11.0. The pre-change coverage audit found standalone lookup/window tests, overlap upsert preparation, metadata guard tests, and CLI/runner failure tests, but no runtime checkpoint wiring. The CLI now passes explicit `RunSelection`; the runner performs per-entity lookup and one cutoff before source work for games, companies, and involved companies. Focused tests compose real fetch/pagination/archive/raw-loader/metadata helpers with queued source responses and fake connections. They cover unfiltered bootstrap and windowed pages, inclusive lower/exclusive upper SQL, actual lower-bound start parameter, eligible terminal end parameter, empty uncapped success, all supplied caps, bad/missing/out-of-window/future timestamps, custom and arbitrary callbacks, mismatched counts, lookup failure, nonprogressing cutoff, raw-context exit failure, terminal commit/guard failure, and all-mode entity independence. Existing lifecycle and reference-entity regressions remain in the affected suite.

Exact verification commands from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_task45_watermarks.py tests/test_ingestion_runs.py tests/test_pipeline.py tests/test_run_ingestion.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
```

The final focused run passed **147 tests** and the full offline suite passed **371 tests**. Bytecode and pytest cache writes were disabled. The tests record emitted SQL, bound parameters, prepared rows, acknowledged counts, commit calls, and context ordering. They do not execute PostgreSQL or prove constraint enforcement, rollback, durability, ambiguous commit outcomes, or source completeness. Queued clients do not interpret filters or model offset drift. The guarded terminal SQL permits a durable succeeded row after a client-observed completion error; tests model the guard and failure-reporting calls, not that a particular ambiguous commit took effect. PostgreSQL was kept stopped; no live ingestion or database validation occurred. At that point tasks 4.6–4.7 remained open.

## Task 4.6 incremental test verification

Completed September 28, 2026 on Python 3.11.0. The coverage audit found task 4.5 runtime cases for bootstrap and window selection across all three incremental entities, inclusive/exclusive predicates, empty uncapped success, every supplied cap (including zero, negative, and apparently exhausted reads), missing/null/invalid/future/out-of-window timestamps, custom projections and callbacks, page-size and acknowledged-count gates, lookup and terminal failures, guarded transitions, and modeled lost terminal acknowledgment. Earlier window and overlap tests cover boundary ties and complete payload preparation. The new nine cases focus on remaining risks: consecutive bootstrap, overlap replay with tied IDs, and no-change runs; UTC timezone conversion, second flooring, and epoch clamp through the runner; source/archive/raw failure counts and safe messages; all-mode failure after earlier eligible successes; and retry from the prior bound after raw context exit failure. No production code changed.

Exact test commands from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_task45_watermarks.py tests/test_windows.py tests/test_fetch_windows.py tests/test_ingestion_runs.py tests/test_pipeline.py tests/test_run_ingestion.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
```

The affected suite passed **254 tests** and the full offline suite passed **380 tests**. Bytecode and pytest cache writes were disabled. Fake clients supply responses without interpreting IGDB filters, and fake cursors record emitted SQL, bound parameters, prepared rows, acknowledged counts, commit calls, and context order. They do not establish live constraint enforcement, rollback, durability, which side of an ambiguous commit became durable, actual IGDB filtering, or source completeness. The modeled guard shows a failed update cannot replace a row already succeeded; it does not prove which terminal commit took effect. Offset drift, delayed source visibility, and stale-response overwrite remain documented limitations. PostgreSQL remained stopped; no live ingestion or database validation occurred. Only task 4.6 is newly complete; task 4.7 remains open.

## Task 4.7 refresh and backfill verification

Completed September 28, 2026 on Python 3.11.0. The coverage audit found existing normal-run tests for lookup, cutoff, caps, timestamp/count gates, raw context ordering, guarded transitions, and all-mode fail-fast behavior. New focused cases cover CLI option parsing and rejection before settings, source, or database work; full refresh with prior progress, caps, invalid timestamps, failures, and nonprogressing cutoffs; inclusive/exclusive backfill bounds on each page for all five entities; no-progress behavior with caps/failures; reruns with and without prior progress; reference full refresh; and all-mode selection. An earlier test that required reference fetchers to reject `window=` was updated because explicit backfill now uses that argument while default reference queries stay unfiltered.

Exact verification commands from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_task45_watermarks.py tests/test_run_ingestion.py tests/test_fetch_windows.py tests/test_fetch_genres.py tests/test_fetch_platforms.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
```

The final affected suite passed **189 tests** and the full offline suite passed **410 tests**. Bytecode and pytest cache writes were disabled. Fake clients and cursors assert emitted SQL, bound parameters, prepared rows, counts, commit calls, and context ordering. They do not establish live PostgreSQL constraint enforcement, rollback, durability, ambiguous commit outcomes, actual IGDB filtering, or source completeness. PostgreSQL remained stopped and unregistered; no live ingestion or database writes occurred.

## Target test layers

### Unit tests

Use for:

- query construction;
- pagination logic;
- watermark calculations;
- entity configuration;
- payload-to-row preparation;
- error/retry behavior;
- run-state transitions.

No network/database dependency.

### Database integration tests

Add a small set once Docker/PostgreSQL setup is stable. Validate behavior that fakes cannot prove, such as:

- actual table DDL;
- JSONB writes;
- `ON CONFLICT` semantics;
- transaction behavior;
- repeated loads remaining duplicate-free.

### dbt tests

Use dbt for warehouse/data contracts:

- uniqueness;
- not-null keys;
- relationships;
- accepted values;
- targeted business invariants.

### End-to-end smoke test

The final project should have a documented manual or automated smoke path that exercises:

```text
source → raw Postgres → dbt build/test → mart query
```

Airflow's end-to-end DAG run becomes an additional operational validation.

## CI

CI should begin with fast deterministic checks. At minimum:

```text
python -m pytest -q
```

Add database/dbt CI only when the repository can provision the required service predictably.

## Testing principles

- Do not hit IGDB from normal unit tests.
- Do not test implementation details when observable behavior is sufficient.
- Every bug fix should add a regression test when practical.
- New ingestion entities should reuse shared test patterns but still test entity-specific queries/contracts.
