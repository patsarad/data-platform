# Testing Strategy

## Goal

Tests should protect pipeline behavior at the layer where failures are most meaningful, without requiring every test run to contact external services.

## PostgreSQL integration tests

Run the default suite without external services:

```bash
python -m pytest -q
```

Database checks under `tests/integration/` skip unless explicitly enabled. With PostgreSQL running and the Python 3.11 requirements installed:

```bash
RUN_POSTGRES_INTEGRATION=1 python -m pytest -q tests/integration
# Full suite including database checks:
RUN_POSTGRES_INTEGRATION=1 python -m pytest -q
```

In PowerShell, set `$env:RUN_POSTGRES_INTEGRATION = "1"` before the command. Connection settings come from the same `.env`/exported `POSTGRES_*` variables as ingestion. The configured login needs permission to create schemas, tables, views, and trigger functions in the selected database. An opted-in connection failure fails the suite; it does not silently skip.

Each test creates unique `test_dp_<uuid>_raw` / `_dbt` schemas and drops only those schemas in fixture cleanup, including on assertion failures. Hard process termination can interrupt cleanup; there is no blanket prefix-based deletion. Existing configured raw/output schemas are not used for fixture data. JSONL and dbt targets/logs go to pytest temporary directories. No extra dependencies are required.

- `test_ingestion_postgres.py`: actual raw/metadata transactions for games, companies, and involved companies; bootstrap, overlap, duplicate-safe updates, caps, backfill, full refresh, empty success, raw SQL rollback, terminal SQL failure after committed raw data, retry, and guarded failure after a simulated lost acknowledgment. Source pages and the run clock are controlled; the database is real, with fresh connections checking committed state.
- `test_dbt_postgres.py`: **68 cases**: 65 distinct data-behavior scenarios using
  explicit raw-schema settings, plus three complete project builds for explicit,
  legacy, and explicit-over-legacy configuration. The full-project cases verify
  all 13 models and 46 dbt tests, source resolution, independent output schemas,
  staging lineage/identifier tests, all model/column documentation, and independent
  catalog/release/performance/company-output value comparisons. Each forces a fresh
  parse, then repeats all dbt tests using its own parse cache and compares model/source
  resolution and documentation. The behavior scenarios retain their original
  assertions, malformed inputs, deliberate failures and recovery checks.

The test matrix now separates schema configuration from data behavior. Every
scenario still gets fresh disposable schemas and an external artifact directory.
`loaded_sources` loads the original five rows per entity and six involved-company
records. `built_staging` uses `dbt run` for the five staging views plus dependencies
explicitly declared with `@pytest.mark.dbt_models(...)`. It does not build unrelated
marts or rerun the whole project's tests in every setup. Full builds and their
manifest assertions live in `test_full_project_schema_modes`. Focused dbt tests
and recovery builds retain their assertions, with catalog totals/failure expectations
extended for task 6.8. Cautious indirect selection remains where needed.

| Coverage family | Earlier cases (three schema modes) | Current distinct behavior cases | Retained checks |
|---|---:|---:|---|
| Staging | 36 | 12 | Every scalar/type, identifier failures/recovery, malformed casts |
| Game genres | 15 | 5 | Exact pairs, null/invalid members, key/grain failures/recovery |
| Game platforms | 15 | 5 | Exact pairs, cast-normalized duplicates, malformed/key failures |
| Game companies | 12 | 4 | Record grain, nullable roles/references, identity/cast failures |
| Catalog | 27 | 10 | Exact values, fanout, empty input, coverage/key/cast failures; task 6.8 array-container failures/recovery |
| Release trends | 39 | 13 | UTC boundaries/timezones, dated/undated counts, all invariant failures |
| Genre/platform performance | 21 | 7 | Exact metrics, empty input, repeated pairs, every-column/cast failures |
| Company output | 27 | 9 | Exact roles/counts, empty input, multiplicity, every-column/cast failures |
| Full-project schema configuration | Previously repeated in every setup | 3 additional cases | All models/tests, precedence, independent schemas, fresh/cached parity |

Optimization reduced dbt cases from 192 to 67; task 6.8 adds one array-container
scenario, bringing the current total to 68. The 15 ingestion integration cases
and 450 offline cases are unchanged. The 128 removed executions were repeats of the
same 64 scenarios under two extra schema modes. Those full Cartesian combinations
are no longer tested: configuration resolution is covered by dedicated complete
builds, while each data edge case runs under the primary configuration. No distinct
behavior scenario, assertion, malformed value, or deliberate failure was removed.
Historical task sections below retain their original counts and commands.

`run_dbt` enables partial parsing within one test's artifact directory. Caches are
never shared between tests or schemas; fresh schema-mode builds explicitly disable
partial parsing. Subsequent invocations can avoid parsing unchanged files, as
supported by [dbt's parsing contract](https://docs.getdbt.com/reference/parsing).
`dbt-invocations.jsonl` beside each test's target/log directories records command,
selectors, parse mode, return code and elapsed seconds, without environment values
or credentials. Use `--durations=25` to see pytest setup/call costs; a caller-owned
external `--basetemp` directory can retain all timings for analysis.

See [test-harness optimization verification](#test-harness-optimization-verification)
for before/after timings, exact commands, scope, and preservation checks.

These tests never call IGDB. HTTP requests in the test process are rejected, and dbt usage reporting is disabled in subprocesses. Live API smoke checks remain separate. The suite does not prove source completeness, real network acknowledgment loss, server-crash durability, or production-wide data quality. `stg_games`, `stg_genres`, `stg_platforms`, `stg_companies`, and `stg_involved_companies` are views: a successful view build does not evaluate their casts for every raw row. The catalog table evaluates the expressions it projects, but not all unprojected staging fields. The integration tests explicitly query staging output using known fixtures; the dbt key tests inspect raw and staging identifiers, not all scalar casts.

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

## Task 5.1 schema naming verification

Completed September 28, 2026 on Python 3.11.0. The coverage audit found existing fake-connection tests for SQL schema qualification and CLI routing, plus only general settings tests. New settings cases cover the `raw` default, explicit `POSTGRES_RAW_SCHEMA` precedence, and `POSTGRES_SCHEMA=analytics` fallback; the CLI test now asserts default schema routing. Storage SQL and ingestion lifecycle code were unchanged.

Exact Python and dbt commands from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_config.py tests/test_run_ingestion.py tests/test_raw_games.py tests/test_ingestion_runs.py
PYTHONDONTWRITEBYTECODE=1 DBT_SCHEMA=analytics POSTGRES_RAW_SCHEMA=raw /private/tmp/data-platform-phase1-venv/bin/dbt parse --project-dir dbt --profiles-dir dbt --no-partial-parse --target-path /private/tmp/data-platform-task51-VyAlFZ/dbt-target --log-path /private/tmp/data-platform-task51-VyAlFZ/dbt-logs
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task51-VyAlFZ/verify_docs.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m src.ingestion.run_ingestion --help
git diff --check
```

The pre-change focused suite passed **101**, the final focused suite **103**, and the full offline suite **412**. dbt parse passed without connecting to PostgreSQL; its three unused layer-configuration warnings are expected while no models exist. Bytecode and pytest cache writes were disabled, and dbt target/log output was directed outside the repository. Documentation links/examples and the final diff were checked separately. No live connection or migration was attempted. An existing `analytics` installation must keep its legacy raw setting or deliberately move all raw and metadata tables before selecting `raw`.

## Task 5.2 dbt source verification

Completed September 28, 2026 on Python 3.11.0. The coverage audit found entity contracts and fake-connection DDL/upsert tests for all five raw tables, but no dbt source declaration or source-contract test. A new offline test checks the YAML against entity table/key names, raw column shapes, key tests, the schema expression, and absence of unsupported freshness settings or extra sources. The pre-change raw/entity/config focus passed **56** tests; the new source/entity focus passed **7** tests; the full offline suite passed **413**.

Exact commands from the repository root (all dbt generated target/log paths are under `/private/tmp`):

```bash
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_entities.py tests/test_raw_games.py tests/test_raw_genres.py tests/test_raw_platforms.py tests/test_raw_companies.py tests/test_raw_involved_companies.py tests/test_config.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_sources.py tests/test_entities.py
PYTHONDONTWRITEBYTECODE=1 DBT_SCHEMA=analytics POSTGRES_RAW_SCHEMA=raw /private/tmp/data-platform-phase1-venv/bin/dbt parse --project-dir dbt --profiles-dir dbt --no-partial-parse --target-path /private/tmp/data-platform-task52-11b3Vz/raw-target --log-path /private/tmp/data-platform-task52-11b3Vz/raw-logs
PYTHONDONTWRITEBYTECODE=1 DBT_SCHEMA=analytics POSTGRES_RAW_SCHEMA=raw /private/tmp/data-platform-phase1-venv/bin/dbt ls --project-dir dbt --profiles-dir dbt --no-partial-parse --resource-type source --output name --target-path /private/tmp/data-platform-task52-11b3Vz/raw-list-target --log-path /private/tmp/data-platform-task52-11b3Vz/raw-list-logs
PYTHONDONTWRITEBYTECODE=1 DBT_SCHEMA=analytics POSTGRES_RAW_SCHEMA=analytics /private/tmp/data-platform-phase1-venv/bin/dbt parse --project-dir dbt --profiles-dir dbt --no-partial-parse --target-path /private/tmp/data-platform-task52-11b3Vz/analytics-target --log-path /private/tmp/data-platform-task52-11b3Vz/analytics-logs
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task52-11b3Vz/verify_manifest.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task52-11b3Vz/verify_docs.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task52-11b3Vz/verify_snapshot.py
git diff --check
```

The parsed manifests contained exactly five `igdb` sources and ten generic key tests in each schema configuration; each test depends on one source. `dbt ls` discovered all five tables. The docs check passed **125 local links** and the schema examples. The three unused model-directory warnings are expected while models do not exist. Bytecode/pytest caches were disabled; dbt artifacts were directed outside the repository, and before/after file snapshots showed no changes to existing unrelated or tracked generated files. This was parse/discovery validation only: PostgreSQL stayed stopped/unregistered, so the dbt tests did not execute against data, and source declarations did not move existing `analytics` tables or ingestion history.

## Task 5.3 games staging verification

Completed September 28, 2026 on Python 3.11.0. The audit found raw-games DDL/upsert and source-contract tests, plus the 12-field games extraction contract, but no staging model or staging checks. The new focused checks assert the one-source/one-row SQL shape, typed timestamps and ratings/counts, JSONB reference arrays, and absence of defaults, joins, or expansion. They inspect SQL offline; they do not execute it on PostgreSQL.

Exact commands from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_sources.py tests/test_entities.py tests/test_raw_games.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_stg_games.py tests/test_dbt_sources.py tests/test_entities.py tests/test_raw_games.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 DBT_SCHEMA=analytics POSTGRES_RAW_SCHEMA=raw /private/tmp/data-platform-phase1-venv/bin/dbt parse --project-dir dbt --profiles-dir dbt --no-partial-parse --target-path /private/tmp/data-platform-task53-U1CbNi/parse-target --log-path /private/tmp/data-platform-task53-U1CbNi/parse-logs
PYTHONDONTWRITEBYTECODE=1 DBT_SCHEMA=analytics POSTGRES_RAW_SCHEMA=raw /private/tmp/data-platform-phase1-venv/bin/dbt ls --project-dir dbt --profiles-dir dbt --no-partial-parse --resource-type model --output name --target-path /private/tmp/data-platform-task53-U1CbNi/list-target --log-path /private/tmp/data-platform-task53-U1CbNi/list-logs
PYTHONDONTWRITEBYTECODE=1 DBT_SCHEMA=analytics POSTGRES_RAW_SCHEMA=analytics /private/tmp/data-platform-phase1-venv/bin/dbt parse --project-dir dbt --profiles-dir dbt --no-partial-parse --target-path /private/tmp/data-platform-task53-U1CbNi/legacy-target --log-path /private/tmp/data-platform-task53-U1CbNi/legacy-logs
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -c "import json; p='/private/tmp/data-platform-task53-U1CbNi/parse-target/manifest.json'; m=json.load(open(p)); n=[v for v in m['nodes'].values() if v['resource_type']=='model']; assert len(n)==1; v=n[0]; assert v['name']=='stg_games'; assert v['config']['materialized']=='view'; assert v['schema']=='analytics'; assert v['depends_on']['nodes']==['source.data_platform.igdb.raw_games']; assert len(m['sources'])==5; print('manifest: one analytics view, raw_games dependency, five sources')"
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task52-11b3Vz/verify_docs.py
git diff --check
```

The baseline focus passed **17**, the new focus **19**, and the full offline suite **415** tests. dbt parsed successfully with `raw` and legacy `analytics` source schemas and discovered only `stg_games`; the manifest records one `analytics` view depending on `igdb.raw_games` and five sources. The docs check passed **128 local links** and the schema examples; `git diff --check` passed. The two files already untracked at task start, `dbt/models/sources.yml` and `tests/test_dbt_sources.py`, retained their before-task SHA-256 hashes. The two unused intermediate/marts configuration warnings are expected. Generated dbt files went to `/private/tmp`; bytecode and pytest caches were disabled. This verification establishes parser/discovery and static SQL contracts only: the view, casts, source tests, and row values have not been exercised against PostgreSQL. PostgreSQL remained stopped and unregistered.

## Task 5.4 genres staging verification

Verified September 29, 2026 (local time), using the existing Python 3.11.0 / PostgreSQL 17.11 / dbt Core 1.12.5 / dbt-postgres 1.11.0 environment. Only task 5.4 was implemented. The baseline had uncommitted edits, including `tests/integration/test_dbt_postgres.py`; its before-task copy and repository file hashes were recorded under `/private/tmp/data-platform-task54` to distinguish this change. No dependencies or ingestion modules changed.

Exact verification commands from the repository root:

```bash
# Narrow offline checks: 17 passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_stg_genres.py tests/test_dbt_stg_games.py tests/test_dbt_sources.py tests/test_raw_genres.py
# Initial state: Running/Loaded/Schedulable all false.
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/bin/brew services run postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
# Full default suite: 420 passed, 27 skipped.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
# Readiness was retried successfully before database tests.
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
# Narrow real-database checks: 12 passed.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_dbt_postgres.py
# Full enabled suite: 447 passed.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
# Existing local data build and explicit comparisons: passed.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task54/verify_existing_dbt.py
# Restore and inspect service state.
/opt/homebrew/bin/brew services stop postgresql@17
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
git diff --check
```

The first readiness probe reported no response; the retry reported accepting connections before database work. All tests passed on their first runs. Final service flags were all false and final readiness returned exit **2**, `no response`, as expected for the restored stopped service. Login registration was never enabled.

The integration fixture builds two views and passes ten source tests under each of explicit `POSTGRES_RAW_SCHEMA`, legacy `POSTGRES_SCHEMA`, and explicit-over-legacy settings, with independent disposable output schemas. Six added parameterized genre cases query actual values/types/grain and invalid timestamp reads; the six existing games cases remain. Genre fixtures cover absent optional keys, explicit JSON null and nullable names/slugs, empty strings, Unicode, epoch zero, negative seconds, a modern timestamp, and a BIGINT ID beyond 32 bits. Exact expected tuples include `fetched_at`. The default suite skips all 27 database cases and remains independent of PostgreSQL and live HTTP.

The temporary local verification harness loaded existing `.env` through the settings module without schema overrides or edits. Before building, `count(*)` confirmed **five** existing raw genres, so **no live-source requests or bounded ingestion were needed**. Its dbt subprocess executed this command using that loaded environment and `DBT_SEND_ANONYMOUS_USAGE_STATS=false`:

```bash
/private/tmp/data-platform-phase1-venv/bin/python -c 'from dbt.cli.main import cli; cli()' build --project-dir /Users/patrick/Desktop/Code/data_platform/dbt --profiles-dir /Users/patrick/Desktop/Code/data_platform/dbt --no-partial-parse --target-path /private/tmp/data-platform-task54/existing-dbt/target --log-path /private/tmp/data-platform-task54/existing-dbt/logs
```

Result: **2 views built, 10 source tests passed**, raw schema `analytics`, output schema `analytics`. Only the existing unused intermediate/marts configuration warnings appeared. The harness queried every output column of all five genres and games, checked one row per raw ID, and compared names/slugs, converted timestamps, fetched times, and games numbers/arrays with raw records. Actual genre types were `BIGINT`, `TEXT`, `TEXT`, `TIMESTAMPTZ`, `TIMESTAMPTZ` in the documented order. The five real genre results were:

| genre_id | name | slug | source_updated_at (UTC) |
|---|---|---|---|
| 2 | Point-and-click | point-and-click | 2011-12-08 22:08:06 |
| 4 | Fighting | fighting | 2011-12-07 20:20:15 |
| 5 | Shooter | shooter | 2011-12-07 20:20:15 |
| 7 | Music | music | 2011-12-07 20:20:15 |
| 8 | Platform | platform | 2011-12-07 20:20:15 |

All five retained raw `fetched_at = 2026-09-27 02:57:10.632774+00:00`. Existing game IDs **1–5** also matched their raw values. Before/after hashes of all five raw tables and `ingestion_runs` matched; no `test_dp_%` schemas remained. Full sampled values/types are in the temporary `existing-dbt/verification.json` artifact. Both local views remain available when PostgreSQL restarts. Temporary dbt artifacts stayed outside the repository; existing `.env`, unmodified baseline files, and tracked generated/private artifacts were retained.

Final review passed `git diff --check` and checked 74 local documentation links and anchors in the six modified documentation files. Before-task hashes confirmed that all 115 other baseline files, including `.env` and tracked generated artifacts, were unchanged. A task-only patch is retained at `/private/tmp/data-platform-task54/task54-only.diff` for review alongside the preexisting uncommitted work.

The real stored sample has no missing optional genre values; those cases are verified using synthetic PostgreSQL fixtures. Successful view creation alone still does not validate row casts, and malformed non-null timestamps fail on read by design. This bounded stored sample establishes no full IGDB coverage. Broader dbt model tests/documentation under tasks 5.8–5.9 remain open.

## Task 5.5 platforms staging verification

Verified September 29, 2026 (local time), using Python 3.11.0 / PostgreSQL 17.11 / dbt Core 1.12.5 / dbt-postgres 1.11.0. Only task 5.5 was implemented. Before-task copies and hashes of 124 existing files were captured under `/private/tmp/data-platform-task55`; `.env` was hashed without copying its contents. Existing uncommitted work, including the integration suite, was retained. No dependencies or ingestion modules changed.

Exact verification commands from the repository root, in execution order:

```bash
# Initial service state: Running/Loaded/Schedulable all false.
/opt/homebrew/bin/brew services info postgresql@17
# Narrow offline suite: 18 passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_stg_platforms.py tests/test_dbt_stg_genres.py tests/test_dbt_stg_games.py tests/test_dbt_sources.py tests/test_raw_platforms.py
# Full default suite: 421 passed, 33 skipped.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
/opt/homebrew/bin/brew services run postgresql@17
# Initial sandboxed readiness loop could not reach the service.
for attempt in {1..30}; do
  /opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432 && break
  sleep 1
done
# Outside the network sandbox: accepting connections, before database tests.
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
# Narrow dbt/PostgreSQL suite: 18 passed.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_dbt_postgres.py
# Full enabled suite: 454 passed.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
# Existing local build, row comparisons, raw/history preservation: passed.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task55/verify_existing_dbt.py
/opt/homebrew/bin/brew services stop postgresql@17
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
git diff --check
```

All tests passed on their first runs. The database checks ran outside the network sandbox after readiness succeeded. Final service inspection showed `Running: false`, `Loaded: false`, `Schedulable: false`; final readiness returned exit **2**, `no response`, as expected. PostgreSQL was started with `services run`, without login registration, and stopped after verification.

The integration fixture now expects exactly three staging views plus ten passing source tests, with explicit, legacy, and explicit-over-legacy source schema settings and independent disposable output schemas. Six new parameterized platform cases query actual PostgreSQL types, view materialization, every output value, raw IDs, and one-row-per-ID grain, and verify invalid timestamp reads fail. Fixtures include missing keys, explicit JSON null, nullable name/slug, empty strings, Unicode, epoch zero, negative Unix seconds, a modern timestamp, and a BIGINT ID beyond 32 bits. The twelve existing games/genres cases remain. Default tests skip all 33 database cases and require no live HTTP or PostgreSQL.

The local verification harness loaded existing `.env` through the settings module, without source/output schema overrides. Before building, `count(*)` confirmed **five existing platforms**. No bounded ingestion or live-source request was needed. Its dbt subprocess used `DBT_SEND_ANONYMOUS_USAGE_STATS=false` and ran:

```bash
/private/tmp/data-platform-phase1-venv/bin/python -c 'from dbt.cli.main import cli; cli()' build --project-dir /Users/patrick/Desktop/Code/data_platform/dbt --profiles-dir /Users/patrick/Desktop/Code/data_platform/dbt --no-partial-parse --target-path /private/tmp/data-platform-task55/existing-dbt/target --log-path /private/tmp/data-platform-task55/existing-dbt/logs
```

Result: **3 views built, 10 source tests passed**, raw schema `analytics`, output schema `analytics`. Only the expected unused intermediate/marts configuration warnings appeared. Platform output types were `BIGINT`, `TEXT`, `TEXT`, `TIMESTAMPTZ`, `TIMESTAMPTZ` in the documented order. All five platform rows were queried and compared with raw IDs, names/slugs, payload update times, and fetched times:

| platform_id | name | slug | source_updated_at (UTC) |
|---|---|---|---|
| 3 | Linux | linux | 2024-06-10 13:48:09 |
| 4 | Nintendo 64 | n64 | 2024-06-10 13:48:09 |
| 5 | Wii | wii | 2024-06-10 13:48:09 |
| 6 | PC (Microsoft Windows) | win | 2024-06-10 13:48:09 |
| 7 | PlayStation | ps | 2024-06-10 13:48:09 |

All five retained raw `fetched_at = 2026-09-27 02:57:11.235555+00:00`. The five games and five genres also matched every output value against raw records. Hashes of all five raw tables and `ingestion_runs` were unchanged across the local build. No `test_dp_%` schemas remained after integration cleanup. Detailed results are retained at `/private/tmp/data-platform-task55/existing-dbt/verification.json`; the harness and task-only diff are in the same temporary task directory. All three views remain available when PostgreSQL restarts. dbt targets/logs stayed outside the repository; `.env` and existing generated/private artifacts were preserved.

The real sample contains no missing platform values; synthetic PostgreSQL fixtures verify missing/null behavior. View creation and source-key tests alone do not evaluate every cast. Malformed non-null timestamps still fail on read by design, and five stored rows do not establish full IGDB coverage. Tasks 5.6 onward, including broader model tests and YAML documentation under 5.8–5.9, remain open.

## Task 5.6 companies staging verification

Verified September 29, 2026 (local time), using Python 3.11.0 / PostgreSQL 17.11 / dbt Core 1.12.5 / dbt-postgres 1.11.0. Only task 5.6 was implemented. Before-task copies and 126 file hashes were captured under `/private/tmp/data-platform-task56`; `.env` was hashed without copying its contents. Existing uncommitted changes and tracked artifacts were preserved. No dependencies, ingestion code, source declarations, profiles, or schema settings changed.

Exact test, build, and service verification commands from the repository root, in execution order:

```bash
# Initial service state: Running/Loaded/Schedulable all false.
/opt/homebrew/bin/brew services info postgresql@17
# Narrow offline suite: 19 passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_stg_companies.py tests/test_dbt_stg_platforms.py tests/test_dbt_stg_genres.py tests/test_dbt_stg_games.py tests/test_dbt_sources.py tests/test_raw_companies.py
# Full default suite: 422 passed, 39 skipped.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
/opt/homebrew/bin/brew services run postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
# Narrow dbt/PostgreSQL suite: 24 passed.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_dbt_postgres.py
# Full enabled suite: 461 passed.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
# Existing local build, comparisons, raw/history preservation, schema cleanup: passed.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task56/verify_existing_dbt.py
/opt/homebrew/bin/brew services stop postgresql@17
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
git diff --check
```

All test runs passed on their first attempts. Service startup and database commands ran outside the network sandbox. Readiness reported accepting connections before database tests. Final service flags were all false, and final readiness returned exit **2**, `no response`, as expected. The cluster remains on disk, stopped and unregistered.

The integration fixture expects exactly four staging views and ten passing source tests. The six new parameterized company cases retain explicit, legacy, and explicit-over-legacy source schema settings and independent disposable `DBT_SCHEMA` outputs. They query actual PostgreSQL column types, view materialization, every output value, raw IDs, and one-row-per-ID grain. Fixtures include missing optional fields, explicit JSON null, nullable names/slugs, empty strings, Unicode, epoch zero, negative Unix seconds, a modern timestamp, and a BIGINT ID beyond 32 bits. An invalid non-null timestamp fails on read as expected. All eighteen earlier games/genres/platforms cases remain. Default tests skip all 39 database cases; no test calls IGDB.

A read-only pre-build count confirmed **five existing companies**; no ingestion or live-source request was needed. The local harness repeats that count before building, loads existing `.env` through settings without schema overrides, and disables dbt usage reporting. Its exact dbt subprocess command was:

```bash
/private/tmp/data-platform-phase1-venv/bin/python -c 'from dbt.cli.main import cli; cli()' build --project-dir /Users/patrick/Desktop/Code/data_platform/dbt --profiles-dir /Users/patrick/Desktop/Code/data_platform/dbt --no-partial-parse --target-path /private/tmp/data-platform-task56/existing-dbt/target --log-path /private/tmp/data-platform-task56/existing-dbt/logs
```

Result: **4 views built, 10 source tests passed**, raw schema `analytics`, output schema `analytics`. Only expected unused intermediate/marts configuration warnings appeared. Company output types were `BIGINT`, `TEXT`, `TEXT`, `TIMESTAMPTZ`, `TIMESTAMPTZ` in the documented order. Every output field for all five companies matched raw IDs, names/slugs, payload update times, and fetched times:

| company_id | name | slug | source_updated_at (UTC) |
|---|---|---|---|
| 1 | Electronic Arts | electronic-arts | 2026-09-22 02:05:30 |
| 2 | BioWare | bioware | 2026-09-11 15:00:09 |
| 3 | Looking Glass Studios | looking-glass-studios | 2026-09-07 23:11:40 |
| 4 | Eidos Interactive | eidos-interactive | 2026-09-17 16:52:56 |
| 5 | Interplay Entertainment | interplay-entertainment | 2026-09-17 18:25:51 |

All five retained raw `fetched_at = 2026-09-27 02:57:11.745586+00:00`. Five games, five genres, and five platforms also matched every output value against raw records. Hashes of all five raw tables and `ingestion_runs` matched before/after the local build. No `test_dp_%` schemas remained after fixture cleanup. Detailed results are retained at `/private/tmp/data-platform-task56/existing-dbt/verification.json`; the harness and task-only diff are in the same temporary task directory. dbt targets/logs stayed outside the repository, and all four views remain available when PostgreSQL restarts. `.env`, baseline edits, raw archives, and existing tracked generated/private artifacts were preserved; nothing was committed or untracked.

The real sample contains no missing company values; synthetic PostgreSQL fixtures verify missing/null behavior. A view build and source-key tests alone do not evaluate all casts. Invalid non-null timestamps fail on read by design, and five stored rows do not establish full source coverage. Task 5.7 and broader model tests/YAML documentation under 5.8–5.9 remain open.

## Task 5.7 involved-companies staging verification

Verified September 30, 2026 (local time), using Python 3.11.0 / PostgreSQL 17.11 / dbt Core 1.12.5 / dbt-postgres 1.11.0. Only task 5.7 was implemented. Before-task copies and 128 file hashes were captured under `/private/tmp/data-platform-task57`; `.env` was hashed without copying its contents. Existing uncommitted changes and tracked artifacts were retained. No repository dependencies, ingestion code, source declarations, profiles, or schema settings changed.

The requested temporary virtual environment was incomplete: `pyvenv.cfg`, pytest's entrypoint, and pip files were missing. The first narrow run failed before collection with `No module named pytest`; restoring the venv metadata alone then exposed missing `pytest.__main__` and `pip.__main__`. Repair commands were:

```bash
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m venv --without-pip /private/tmp/data-platform-phase1-venv
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m ensurepip --upgrade
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pip install --ignore-installed -r requirements.txt > /private/tmp/data-platform-task57/environment-repair.log 2>&1
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pip check
```

The unchanged bounded requirements were reinstalled into the same requested environment; no repository files or dependency requirements changed. `pip check` reported no broken requirements, with warnings about four leftover damaged metadata directories. dbt Core, dbt-postgres, pytest (8.4.2), and psycopg (3.3.6) retained their baseline versions. Other transitive packages were resolved again from the existing ranges. No generated/private artifact was deleted or untracked.

Exact test, build, and service commands from the repository root:

```bash
# Initial state: Running/Loaded/Schedulable all false.
/opt/homebrew/bin/brew services info postgresql@17
# After environment repair: 20 passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_stg_involved_companies.py tests/test_dbt_stg_companies.py tests/test_dbt_stg_platforms.py tests/test_dbt_stg_genres.py tests/test_dbt_stg_games.py tests/test_dbt_sources.py tests/test_raw_involved_companies.py
# Full default suite: 423 passed, 45 skipped.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
/opt/homebrew/bin/brew services run postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
# Narrow dbt/PostgreSQL suite: 30 passed.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_dbt_postgres.py
# Full enabled suite: 468 passed.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
# Existing local build, row comparisons, raw/history hashes, schema cleanup: passed.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task57/verify_existing_dbt.py
/opt/homebrew/bin/brew services stop postgresql@17
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
git diff --check
```

All tests passed after the environment repair. Readiness reported accepting connections before database work. Database commands used the existing project login outside the network sandbox. The service was stopped immediately after the local comparison: all three service flags were false and final readiness returned exit **2**, `no response`, as expected. The on-disk cluster remains intact.

The integration fixture now expects exactly five staging views and ten passing source tests. Six new parameterized cases retain explicit, legacy, and explicit-over-legacy source settings with independent disposable `DBT_SCHEMA` outputs. Five fixtures remain in each earlier source; six involved-company fixtures cover missing fields, explicit JSON null, all four developer/publisher combinations, epoch zero, negative and modern timestamps, zero and BIGINT references, a BIGINT relationship ID, and distinct IDs sharing an unmatched game/company pair. Queries check actual column types, view materialization, every output value, raw IDs, and relationship-record grain. Invalid non-null game/company references, roles, and timestamps each fail on read as expected. All 24 earlier staging cases and all ingestion regressions remain; no test calls IGDB. The default suite skips all 45 database cases.

A read-only check before database tests counted **five existing involved-company records** in `analytics.raw_involved_companies` and saved raw/history hashes to `/private/tmp/data-platform-task57/raw-before-tests.json`. The local harness repeated the count before building, loaded existing `.env` through settings without schema overrides, and disabled dbt usage reporting. No ingestion or live-source request was needed. Its exact dbt subprocess command was:

```bash
/private/tmp/data-platform-phase1-venv/bin/python -c 'from dbt.cli.main import cli; cli()' build --project-dir /Users/patrick/Desktop/Code/data_platform/dbt --profiles-dir /Users/patrick/Desktop/Code/data_platform/dbt --no-partial-parse --target-path /private/tmp/data-platform-task57/existing-dbt/target --log-path /private/tmp/data-platform-task57/existing-dbt/logs
```

Result: **5 views built, 10 source tests passed**, raw schema `analytics`, output schema `analytics`. Only expected unused intermediate/marts configuration warnings appeared. Actual involved-company output types, in order, were `BIGINT`, `BIGINT`, `BIGINT`, `BOOLEAN`, `BOOLEAN`, `TIMESTAMPTZ`, `TIMESTAMPTZ`. Every field matched raw IDs, payload references/roles/update times, and fetched times:

| involved_company_id | game_id | company_id | developer | publisher |
|---|---|---|---|---|
| 2 | 38 | 1 | false | true |
| 6 | 2 | 3 | true | false |
| 7 | 2 | 4 | false | true |
| 8 | 38 | 7 | true | false |
| 9 | 37 | 11 | true | false |

All five source updates were `2011-11-12 00:00:00+00:00`; all five unchanged fetch timestamps were `2026-09-27 02:57:12.236506+00:00`. Each ID appeared exactly once. References outside the stored games/companies samples remained present. Five games, genres, platforms, and companies each also matched every output value against their raw records.

Hashes of all five raw tables and `ingestion_runs` matched before tests, before the local build, and after the build. No `test_dp_%` schemas existed before tests or remained afterward. Detailed results are at `/private/tmp/data-platform-task57/existing-dbt/verification.json`; the harness, baseline hashes, and task-only diff are in the task directory. dbt targets/logs stayed outside the repository. The five views persist for the next PostgreSQL session. `.env`, baseline edits, raw archives, and existing tracked artifacts were preserved; nothing was committed or untracked.

The real sample has no missing fields and covers developer-only/publisher-only roles. Synthetic fixtures verify missing/null and both-true/both-false cases. View creation and source-key tests alone do not validate scalar casts; malformed non-null scalars fail on read. Five stored rows do not establish source or reference completeness. Broader dbt model tests and YAML documentation remain tasks 5.8–5.9; no later checkbox changed.

## Tasks 4.5 through 5.3 reassessment fixes

Verified September 29, 2026 with Python 3.11.0, PostgreSQL 17.11, dbt Core 1.12.5, and dbt-postgres 1.11.0. dbt now resolves raw sources with `POSTGRES_RAW_SCHEMA`, then legacy `POSTGRES_SCHEMA`, then `raw`, matching Python. Four offline cases protect default/explicit/legacy/precedence behavior; six database cases also exercise dbt’s real schema rendering and SQL execution. The existing staging SQL and ingestion implementation are retained.

Exact test commands, from the repository root:

```bash
# Before changes: 7 passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_config.py tests/test_dbt_sources.py tests/test_dbt_stg_games.py
# After changes: 11 passed, 21 skipped (explicit database opt-in required).
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_config.py tests/test_dbt_sources.py tests/test_dbt_stg_games.py tests/integration
/opt/homebrew/bin/brew services run postgresql@17
# Narrow database suites: 15 passed, then 6 passed.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_ingestion_postgres.py
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_dbt_postgres.py
# Full default suite: 419 passed, 21 skipped.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
# Full enabled suite: 440 passed.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
```

A separate local verification loaded `.env` through the existing settings module and ran the dbt CLI with no source/output schema overrides. Its exact invocation was:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-review-fixes/verify_existing_dbt.py
```

That temporary harness invoked `dbt build` through the installed Python CLI, with project/profile paths pointing to this repository’s `dbt/` directory, `--no-partial-parse`, and targets/logs under `/private/tmp/data-platform-review-fixes/existing-dbt/`. All ten source tests passed, and `analytics.stg_games` was created successfully over the existing `analytics.raw_games`. All five existing game rows were queried, including their typed timestamps/numbers and relationship arrays. Before/after hashes of existing raw tables and ingestion history matched. This view remains available locally; no schema migration or `.env` change was needed.

The earlier September 29 audit separately passed two five-record live all-entity runs, bounded backfill filters on all five endpoints, and a capped full refresh. Its source requests were not repeated for this configuration/test-only fix. An initial Twitch OAuth timeout during that audit passed on rerun; no source-completeness claim follows from these bounded checks.

After validation, all temporary integration schemas were absent. `git diff --check` and local documentation-link checks passed. PostgreSQL was stopped using `brew services stop postgresql@17`; `services info` reported all three service flags false, and `pg_isready` returned exit 2/no response as expected. Existing tracked generated/private artifacts were retained. No later roadmap checkbox changed.

## Task 5.8 dbt tests verification

Verified September 30, 2026. Only task 5.8 was implemented. `dbt/models/staging/schema.yml` adds ten default-error `unique`/`not_null` tests on the five staging primary identifiers. The ten existing source tests remain. No strict relationship test is justified by current ingestion coverage: independent bounded loads omit referenced games/companies/lookup/relationship records, references are nullable, and game arrays have no bridge model yet. The [per-relationship deferral table](../pipeline/DBT_TRANSFORMATIONS.md#staging-identifier-tests-task-58) records the rationale. No model SQL, ingestion behavior, dependency, source definition, schema precedence, or independent `DBT_SCHEMA` behavior changed. Task 5.9 remains open.

Added one offline YAML/entity-key contract test and six opt-in database cases (duplicate/NULL × explicit/legacy/explicit-over-legacy schema modes). The existing thirty dbt and fifteen ingestion database regressions remain. Each failure case first builds five valid views and passes twenty tests, then alters only disposable staging views. One duplicate or NULL identifier per model must produce exactly five matching model-test failures (one violation each); the other fifteen tests, including all source tests, must pass. Restoring the original views must return all twenty tests to passing. Raw PK constraints stay intact. Existing fixture values retain absent/null references, repeated game/company pairs, independent roles, and invalid-scalar checks; each game reference array now also contains an unloaded ID. Manifest assertions check model test dependencies, tested columns, severity, exact model/test counts, source precedence, and separate output schemas.

Exact commands from the repository root (requested Python environment, bytecode/cache writes disabled):

```bash
# Baseline narrow checks: 11 passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_sources.py tests/test_dbt_stg_games.py tests/test_dbt_stg_genres.py tests/test_dbt_stg_platforms.py tests/test_dbt_stg_companies.py tests/test_dbt_stg_involved_companies.py
# Updated narrow offline checks: 12 passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_staging_tests.py tests/test_dbt_sources.py tests/test_dbt_stg_games.py tests/test_dbt_stg_genres.py tests/test_dbt_stg_platforms.py tests/test_dbt_stg_companies.py tests/test_dbt_stg_involved_companies.py
# Full default suite: 424 passed, 51 skipped.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
# Initial service state: Running/Loaded/Schedulable all false.
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/bin/brew services run postgresql@17
# Accepting connections before database work.
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
# Focused database suite: 36 passed.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_dbt_postgres.py
# Full enabled suite: 475 passed.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
# Local build, all staging row comparisons, preservation hashes, schema cleanup.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task58/verify_existing_dbt.py
/opt/homebrew/bin/brew services stop postgresql@17
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task58/check_docs.py
git diff --check
```

The local harness loads the existing `.env` without overrides and invokes:

```bash
/private/tmp/data-platform-phase1-venv/bin/python -c 'from dbt.cli.main import cli; cli()' build --project-dir /Users/patrick/Desktop/Code/data_platform/dbt --profiles-dir /Users/patrick/Desktop/Code/data_platform/dbt --no-partial-parse --target-path /private/tmp/data-platform-task58/existing-dbt/target --log-path /private/tmp/data-platform-task58/existing-dbt/logs
```

Result: **five views built; ten source and ten staging tests passed** over existing `analytics` raw tables, with output schema `analytics`. Every column in all five existing rows per staging model matched the raw records. No ingestion was needed. Before tests, the configured raw tables each had five rows and `ingestion_runs` had 21 rows. Their hashes matched before tests, before the local build, and after the build. No disposable `test_dp_%` schemas existed initially or remained after validation. Synthetic failures were expected assertions, not suite failures. Only unused intermediate/marts configuration warnings appeared in dbt.

PostgreSQL was started with `services run`, then stopped/unregistered: all three service flags false, final readiness exit 2 / no response. Database work ran outside the network sandbox. Temporary dbt targets/logs stayed outside the repository. Before-task copies and 130 hashes, raw/history hashes, the local harness/results, and a task-only diff are under `/private/tmp/data-platform-task58`; `.env` was hashed without copying its contents. Existing user changes, local raw archives, and the 26 already tracked generated/local artifacts were retained; nothing was committed, deleted, untracked, migrated, or reset.

The final documentation check passed 87 local links/anchors, `git diff --check` passed, and the baseline comparison found only the nine task files changed/created. All other baseline hashes, including `.env` and tracked artifacts, matched; only roadmap checkbox 5.8 changed.

Passing identifier tests does not validate every projected scalar cast or prove source/reference completeness. Full model/column YAML documentation and its build verification remain task 5.9.

## Task 5.9 model documentation and build verification

Verified September 30, 2026. Only task 5.9 was implemented. `dbt/models/staging/schema.yml` now describes all five staging models and all 35 output columns from the verified contracts: source lineage, entity/relationship-record grain, SQL types, nullable values, Unix-seconds timestamps, ratings/counts, JSONB array distinctions, loader timestamps, and independent role flags. Existing identifier tests, relationship-test deferrals, SQL, source-schema precedence, and independent `DBT_SCHEMA` are unchanged. Descriptions are dbt metadata; no persisted comments, enforced constraints, dependencies, ingestion, or Phase 6 models were added.

Five parameterized offline cases check descriptions and exact column coverage against SQL projections, rejecting missing, duplicate, stale, or blank column documentation. The existing identifier-test assertion now permits documented optional columns while requiring tests only on primary identifiers. Existing PostgreSQL fixtures additionally compare documented manifest columns with actual view columns and require nonempty descriptions under explicit, legacy, and conflicting schema settings. Existing scalar/null/reference/role/grain checks and deliberate duplicate/NULL failures with recovery remain intact.

Exact commands from the repository root:

```bash
# Start the requested service; await accepting connections.
/opt/homebrew/bin/brew services run postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
# Baseline narrow checks: 12 passed. After documentation/coverage changes: 17 passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_staging_tests.py tests/test_dbt_sources.py tests/test_dbt_stg_games.py tests/test_dbt_stg_genres.py tests/test_dbt_stg_platforms.py tests/test_dbt_stg_companies.py tests/test_dbt_stg_involved_companies.py
# Focused database suite: 36 passed.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_dbt_postgres.py
# Full default suite: 429 passed, 51 skipped.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
# Full enabled suite: 480 passed.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
# Existing-data build, parsed documentation, all staging values, preservation, and schema cleanup.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task59/verify_existing_dbt.py
/opt/homebrew/bin/brew services stop postgresql@17
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task59/check_docs.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task59/check_preservation.py
git diff --check
```

The existing-data harness loads `.env` without overrides and disables dbt usage reporting. It invokes:

```bash
/private/tmp/data-platform-phase1-venv/bin/python -c 'from dbt.cli.main import cli; cli()' build --project-dir /Users/patrick/Desktop/Code/data_platform/dbt --profiles-dir /Users/patrick/Desktop/Code/data_platform/dbt --no-partial-parse --target-path /private/tmp/data-platform-task59/existing-dbt/target --log-path /private/tmp/data-platform-task59/existing-dbt/logs
```

Result: **five views built and twenty dbt tests passed** (ten source, ten staging). All five model descriptions and 35 column descriptions exactly matched the parsed manifest and covered the actual view columns. Every output value in all five existing rows per staging model matched raw records. Both existing source/output schemas remained `analytics`; isolated integration tests retained separate output schemas and all three source-precedence modes. No ingestion was needed. Only expected unused intermediate/marts configuration warnings appeared.

Before testing, all five raw tables had five rows and `ingestion_runs` had 21 rows. SHA-256 hashes of sorted raw/history rows matched before tests, before the existing-data build, and afterward. No disposable `test_dp_%` schemas existed initially or remained after verification; fixtures drop only their own schemas. Targets/logs stayed outside the repository. The initial sandboxed service start failed with launchctl bootstrap exit 5; retry outside the sandbox succeeded. The initial socket readiness probe had no response; the explicit localhost probe confirmed readiness before database work. Database tests/build ran outside the network sandbox. PostgreSQL was stopped/unregistered afterward: Running/Loaded/Schedulable all false; readiness exit 2, no response.

Before-task copies, 153 baseline file hashes, raw/history hashes, verification scripts/results, and the task-only diff are under `/private/tmp/data-platform-task59`. `.env` was hashed without copying its contents. Only the nine task files changed; all other baseline hashes matched, including `.env`, raw archives, and the 26 previously reported tracked generated/local artifacts. Nothing was committed, deleted, untracked, migrated, or reset. Documentation link/anchor checks and `git diff --check` passed. Only roadmap checkbox 5.9 changed, completing Phase 5; Phase 6 remains unimplemented.

A successful view build and identifier tests still do not evaluate every scalar cast or prove source/reference completeness. This verification queries every stored staging column separately, while synthetic fixtures cover nullable/malformed inputs and incomplete references. Strict relationship checks remain deferred under the existing per-key policy.

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

The opt-in suite above now runs against the local PostgreSQL setup. It validates behavior that fakes cannot prove, including:

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

## Task 6.1 game-genre relationship verification

Verified September 30, 2026. Only task 6.1 was implemented. `int_game_genres` is a view over `stg_games` at distinct BIGINT `(game_id, genre_id)` grain. Lateral JSONB expansion normalizes whole-array JSON null to SQL NULL; absent/null/empty arrays emit zero rows. Duplicate pairs collapse after casting. No genre lookup join removes unmatched IDs, and no genre reference-existence or positivity tests are imposed. Null members remain visible to `not_null`; malformed non-null arrays/members fail on evaluation. See the [complete contract](../pipeline/DBT_TRANSFORMATIONS.md#int_game_genres-task-61).

Added two offline SQL/YAML contract cases and fifteen opt-in PostgreSQL cases under explicit, legacy, and explicit-over-legacy source-schema settings with independent disposable `DBT_SCHEMA`. Checks cover exact types/values, missing/null/empty arrays, duplicate/reused/large/zero IDs, incomplete genre coverage, malformed values, model/column documentation, and intentional composite-grain/null-key failures with recovery. The existing staging corruption checks now select source/staging tests explicitly so their expected failures remain independent of the new dependent bridge; all earlier coverage is retained.

Exact commands from the repository root, in validation order:

```bash
/opt/homebrew/bin/brew services run postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
# Baseline narrow offline checks: 13 passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_staging_tests.py tests/test_dbt_sources.py tests/test_dbt_stg_games.py
# Narrow offline checks with the new model: 15 passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_int_game_genres.py tests/test_dbt_staging_tests.py tests/test_dbt_sources.py tests/test_dbt_stg_games.py
# New relationship database cases: 15 passed, 36 deselected.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_dbt_postgres.py -k game_genres
# Full default suite: 431 passed, 66 skipped.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
# Affected staging failure/recovery checks: 6 passed, 45 deselected.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_dbt_postgres.py -k staging_identifier
# Full enabled suite: 497 passed.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
# Existing-data build, exact-row comparisons, raw/history preservation, cleanup check.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task61/verify_existing_dbt.py
/opt/homebrew/bin/brew services stop postgresql@17
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task61/check_docs.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task61/check_preservation.py
git diff --check
```

The existing-data harness uses environment-backed settings without overrides and disables dbt usage reporting. Its dbt invocation is:

```bash
/private/tmp/data-platform-phase1-venv/bin/python -c 'from dbt.cli.main import cli; cli()' build --project-dir /Users/patrick/Desktop/Code/data_platform/dbt --profiles-dir /Users/patrick/Desktop/Code/data_platform/dbt --no-partial-parse --target-path /private/tmp/data-platform-task61/existing-dbt/target --log-path /private/tmp/data-platform-task61/existing-dbt/logs
```

Result: **six views built, 23 dbt tests passed**, with six model descriptions and 37 documented columns matching the manifest and actual view columns. All five rows in each staging view still match raw records. `analytics.int_game_genres` exactly matches the 11 distinct pairs from these existing arrays:

| Game ID | Stored genre array | Output genre IDs |
|---|---|---|
| 1 | `[5, 13, 31]` | 5, 13, 31 |
| 2 | `[13, 31]` | 13, 31 |
| 3 | `[5, 13, 31]` | 5, 13, 31 |
| 4 | `[5, 31]` | 5, 31 |
| 5 | `[12]` | 12 |

Eight pairs reference genre IDs 12, 13, or 31 absent from the independently bounded genre table; all eight survive. Both existing source/output schemas remain `analytics`. No ingestion, settings change, migration, data clearing, or watermark reset was needed. The only dbt configuration warning is the expected unused marts path.

All tests passed on their first runs. The initial sandboxed service start returned launchctl bootstrap exit 5; retry outside the sandbox succeeded, and localhost readiness reported accepting connections before database work. Database tests/build ran outside the network sandbox. SHA-256 hashes of all five raw tables (five rows each) and 21 ingestion-run records matched before tests, before the build, and after the build. No disposable schemas existed initially or remained after verification. Each fixture dropped only its own schemas. PostgreSQL was stopped/unregistered afterward: Running/Loaded/Schedulable all false; final readiness exit 2/no response.

Baseline hashes of 153 files, the existing-data harness/results, and preservation/link check scripts are under `/private/tmp/data-platform-task61`; `.env` was hashed without copying its contents. dbt targets/logs stayed outside the repository. The two pre-existing uncommitted edits (`.env.example`, `.gitignore`), raw archives, `.env`, and all 26 previously reported tracked generated/local artifacts remain unchanged. Nothing was committed, deleted, or untracked. Documentation link/anchor checks and `git diff --check` passed.

Task-only files created: `dbt/models/intermediate/int_game_genres.sql`, `dbt/models/intermediate/schema.yml`, `dbt/tests/int_game_genres_unique_pair.sql`, and `tests/test_dbt_int_game_genres.py`. Files modified: `tests/integration/test_dbt_postgres.py`, `docs/CURRENT_STATE.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/pipeline/DBT_TRANSFORMATIONS.md`, `docs/engineering/LOCAL_DEVELOPMENT.md`, `docs/engineering/DATA_QUALITY.md`, and this page. Only roadmap checkbox 6.1 changed.

The offline tests inspect SQL/YAML contracts; actual row semantics are evaluated by the opt-in PostgreSQL tests. Passing this build does not prove full IGDB/genre coverage, and absent/null/empty arrays do not establish that a game has no real-world genres. Existing limitations of unrelated staging casts remain; genre members are evaluated by the bridge's tests. At that point no task 6.2 or later model was implemented; task 6.2 verification follows below.

## Task 6.2 game-platform relationship verification

Verified September 30, 2026. Only task 6.2 was implemented. `int_game_platforms` follows the existing genre bridge as a view over `stg_games`, at distinct BIGINT `(game_id, platform_id)` grain. Lateral expansion normalizes whole-array JSON null; absent/null/empty arrays emit zero rows. Duplicate members collapse after casting, including castable integer strings. Unmatched platform IDs survive independently bounded ingestion without a lookup join or reference-existence test. Null members remain visible to `not_null`; malformed non-null arrays/members raise on evaluation. The genre SQL is unchanged. See the [platform contract](../pipeline/DBT_TRANSFORMATIONS.md#int_game_platforms-task-62).

Two offline cases check SQL lineage/expansion/grain and YAML model/column descriptions and tests. The genre documentation test now selects its own model by name in the shared YAML, retaining its assertions. Fifteen new PostgreSQL cases cover all three source-schema modes with independent disposable output schemas: exact values/types/grain, absent/null/empty arrays, duplicate/reused/large/zero/negative IDs, integer-string casts, incomplete reference coverage, malformed inputs, deliberate pair/key defects, and recovery. Correcting invalid source input and restoring deliberately broken views each returns all three platform tests to passing. Existing genre/staging and ingestion coverage remains intact.

Exact commands from the repository root:

```bash
/opt/homebrew/bin/brew services run postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
# Baseline narrow offline: 15 passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_int_game_genres.py tests/test_dbt_staging_tests.py tests/test_dbt_sources.py tests/test_dbt_stg_games.py
# Record configured raw/history hashes before database tests.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task62/snapshot_database.py
# Updated narrow offline: 17 passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_int_game_platforms.py tests/test_dbt_int_game_genres.py tests/test_dbt_staging_tests.py tests/test_dbt_sources.py tests/test_dbt_stg_games.py
# New PostgreSQL cases: 15 passed, 51 deselected.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_dbt_postgres.py -k game_platforms
# Full default: 433 passed, 81 skipped.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
# Full enabled: 514 passed.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
# Existing-data build, all staging/bridge comparisons, preservation, schema cleanup.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task62/verify_existing_dbt.py
/opt/homebrew/bin/brew services stop postgresql@17
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task62/check_docs.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task62/check_preservation.py
git diff --check
```

The existing-data harness loads existing environment-backed settings without overrides, disables dbt usage reporting, and executes:

```bash
/private/tmp/data-platform-phase1-venv/bin/python -c 'from dbt.cli.main import cli; cli()' build --project-dir /Users/patrick/Desktop/Code/data_platform/dbt --profiles-dir /Users/patrick/Desktop/Code/data_platform/dbt --no-partial-parse --target-path /private/tmp/data-platform-task62/existing-dbt/target --log-path /private/tmp/data-platform-task62/existing-dbt/logs
```

Result: **seven views built, 26 dbt tests passed** (ten source, ten staging, six bridge). All seven model descriptions and 39 documented columns match the manifest and actual view columns. Every staging value still matches the five stored rows per source; the genre bridge still matches all 11 source-array pairs. The platform bridge matches exactly 14 distinct pairs:

| Game ID | Stored platform array | Output platform IDs |
|---|---|---|
| 1 | `[6]` | 6 |
| 2 | `[6]` | 6 |
| 3 | `[11, 6]` | 6, 11 |
| 4 | `[9, 48, 6, 14, 12, 49]` | 6, 9, 12, 14, 48, 49 |
| 5 | `[3, 6, 39, 14]` | 3, 6, 14, 39 |

Eight platform pairs reference IDs 9, 11, 12, 14, 39, 48, or 49 absent from the bounded platform table; all survive. Existing raw/output schemas remain `analytics`. No ingestion, schema migration, data clearing, or watermark reset was needed. Only the expected unused marts configuration warning remains.

The initial sandboxed service start returned launchctl bootstrap exit 5; the same command outside the sandbox succeeded, and localhost readiness confirmed accepting connections before database work. All tests passed on their first runs. Database validation ran outside the network sandbox. Hashes of all five raw tables (five rows each) and 21 ingestion-run records matched before tests, before the build, and after the build. No disposable schemas existed initially or remained afterward; fixtures drop only their own schemas. PostgreSQL was stopped/unregistered afterward: Running/Loaded/Schedulable all false, final readiness exit 2/no response.

Baseline snapshots/hashes of 157 files, verification scripts/results, and a task-only diff are under `/private/tmp/data-platform-task62`. `.env` was hashed without copying its contents. dbt artifacts stayed outside the repository. Existing uncommitted changes, raw archives, `.env`, and all 26 previously reported tracked artifacts were preserved; nothing was committed, removed, or untracked. Documentation links/anchors and `git diff --check` passed.

Created: `dbt/models/intermediate/int_game_platforms.sql`, `dbt/tests/int_game_platforms_unique_pair.sql`, and `tests/test_dbt_int_game_platforms.py`. Modified: `dbt/models/intermediate/schema.yml`, `tests/test_dbt_int_game_genres.py`, `tests/integration/test_dbt_postgres.py`, `docs/CURRENT_STATE.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/pipeline/DBT_TRANSFORMATIONS.md`, `docs/engineering/LOCAL_DEVELOPMENT.md`, `docs/engineering/DATA_QUALITY.md`, and this page. Only roadmap checkbox 6.2 changed; task 6.3 and later remain open.

Offline tests inspect contracts; PostgreSQL cases establish actual row behavior. The bounded sample does not establish full platform coverage, and zero bridge rows do not prove a game has no platform associations. Successful builds still do not validate unrelated staging scalar casts; existing explicit staging-read checks remain in place.

## Task 6.3 game-company relationship verification

Verified September 30, 2026. The grain was documented before implementation:
`int_game_companies` is a five-column view over `stg_involved_companies`, one row
per `involved_company_id`. Distinct records sharing a game/company pair remain
separate, including identical role values. Raw upserts handle versions of one ID;
this model does not deduplicate. Nullable references and independent nullable
BOOLEAN roles pass through; both true, both false, and unknown are valid. Only
record identity has `unique`/`not_null` tests. No reference-existence, reciprocal
array, positivity, required-reference, or role-exclusivity rule was added. See the
[complete contract](../pipeline/DBT_TRANSFORMATIONS.md#int_game_companies-task-63).

Two offline cases protect lineage/projection and complete YAML documentation with
record-grain tests. Twelve opt-in PostgreSQL cases cover three source-schema modes
(explicit, legacy, explicit-over-legacy) with independent disposable `DBT_SCHEMA`:
actual view types, exact values, all nine true/false/NULL role combinations,
repeated pairs with differing and identical roles, missing/JSON-null/partially
null references, large/zero/negative and castable string references, accepted
BOOLEAN strings, unmatched references, and records absent from games' arrays.
Malformed non-null references/roles raise on evaluation and corrected rows recover.
Deliberate duplicate/NULL output identifiers each produce exactly one specific dbt
test failure, then both tests pass after restoring the view. All earlier staging,
genre/platform, ingestion, and schema-precedence checks are retained. The only
changes to existing test logic are build/model/test counts for the added model.

Exact commands from the repository root, in validation order:

```bash
/opt/homebrew/bin/brew services run postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
# Baseline narrow offline: 16 passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_int_game_platforms.py tests/test_dbt_int_game_genres.py tests/test_dbt_stg_involved_companies.py tests/test_dbt_staging_tests.py tests/test_dbt_sources.py
# Read-only raw/history snapshot before database tests.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task63/snapshot_database.py
# Updated narrow offline: 18 passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_int_game_companies.py tests/test_dbt_int_game_platforms.py tests/test_dbt_int_game_genres.py tests/test_dbt_stg_involved_companies.py tests/test_dbt_staging_tests.py tests/test_dbt_sources.py
# New PostgreSQL cases: 12 passed, 66 deselected.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_dbt_postgres.py -k game_companies
# Full default: 435 passed, 93 skipped.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
# Full enabled: 528 passed.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
# Existing-data build, all staging/relationship comparisons, preservation, schema cleanup.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task63/verify_existing_dbt.py
/opt/homebrew/bin/brew services stop postgresql@17
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task63/check_docs.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task63/check_preservation.py
git diff --check
```

The existing-data harness loads `.env` without overrides, disables usage reporting,
and invokes dbt with external artifacts:

```bash
/private/tmp/data-platform-phase1-venv/bin/python -c 'from dbt.cli.main import cli; cli()' build --project-dir /Users/patrick/Desktop/Code/data_platform/dbt --profiles-dir /Users/patrick/Desktop/Code/data_platform/dbt --no-partial-parse --target-path /private/tmp/data-platform-task63/existing-dbt/target --log-path /private/tmp/data-platform-task63/existing-dbt/logs
```

Result: **eight views built and 28 dbt tests passed** (ten source, ten staging,
eight relationship). All eight model descriptions and 44 column descriptions
match the manifest and actual view columns. Every staging value still matches
its five stored source rows, and genre/platform outputs still match all 11/14
source-array pairs. The new model exactly matches these raw and staged records:

| involved_company_id | game_id | company_id | developer | publisher |
|---|---|---|---|---|
| 2 | 38 | 1 | false | true |
| 6 | 2 | 3 | true | false |
| 7 | 2 | 4 | false | true |
| 8 | 38 | 7 | true | false |
| 9 | 37 | 11 | true | false |

Records 2, 8, and 9 have unloaded game and/or company references and all survive.
Existing source/output schemas remain `analytics`. No ingestion, migration,
data clearing, watermark reset, or settings change was needed. Only the expected
unused marts configuration warning remains; no task 6.4 or later model was added.

All test runs passed on their first execution. The initial sandboxed service
start failed with launchctl bootstrap exit 5; the same command outside the sandbox
succeeded. The sandboxed readiness probe reported no response; the explicit
localhost check outside the sandbox confirmed accepting connections before database
work. Database checks/build ran outside the network sandbox. Hashes of all five
raw tables (five rows each) and the 21 ingestion-run records matched before tests,
before the existing-data build, and after it. No disposable schemas existed
initially or remained afterward. Fixtures drop only their own schemas, including
after deliberate failures. PostgreSQL was stopped/unregistered afterward:
Running/Loaded/Schedulable all false, readiness exit 2/no response.

Baseline hashes/copies of 160 files, verification scripts/results, and a task-only
diff are under `/private/tmp/data-platform-task63`; `.env` was hashed without
copying its contents. All unrelated baseline hashes match, including earlier
uncommitted changes, `.env`, raw archives, and the 26 previously reported tracked
artifacts. dbt targets/logs stayed outside the repository. Nothing was committed,
deleted, untracked, or migrated. Documentation link/anchor and whitespace checks
passed. Only roadmap checkbox 6.3 changed; 6.4 and later remain open.

Created: `dbt/models/intermediate/int_game_companies.sql` and
`tests/test_dbt_int_game_companies.py`. Modified:
`dbt/models/intermediate/schema.yml`, `tests/integration/test_dbt_postgres.py`,
`docs/CURRENT_STATE.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`,
`docs/pipeline/DBT_TRANSFORMATIONS.md`, `docs/engineering/LOCAL_DEVELOPMENT.md`,
`docs/engineering/DATA_QUALITY.md`, and this page. No prior relationship SQL or
source/staging contracts changed; no dependency was added.

Offline tests inspect contracts; PostgreSQL cases establish evaluated row
semantics. The local bounded sample has developer-only/publisher-only records;
synthetic fixtures verify repeated pairs and the other nullable role combinations.
Identifier tests and a view build do not validate every reference/role cast or
prove source completeness. Explicit output reads supply that value check here.

## Task 6.4 game catalog verification

The eleven-column catalog contract was documented before implementation in
[dbt transformations](../pipeline/DBT_TRANSFORMATIONS.md#mart_game_catalog-task-64).
`mart_game_catalog` follows the configured marts table materialization and has
exactly one row per staged game. Eight scalar columns pass through unchanged;
three ordered JSONB arrays expose observed genres, platforms, and company
relationship records with available names. Independent aggregation before left
joins prevents fanout. Bridge pairs retain their existing duplicate semantics;
company records retain identity, repeated pairs, nullable references, and all
independent nullable role combinations. No completeness, ranking, positivity,
reciprocal-array, required-reference, or role-exclusivity policy was introduced.

Three offline cases protect curated lineage/materialization, the exact documented
projection, identity-only column tests, and bidirectional game coverage. The 27
new PostgreSQL cases cover actual types/materialization/documentation, exact values,
all optional/null/empty cases, large counts, negative/zero IDs and epochs,
cast-normalized duplicates, duplicate labels, numeric ordering, incomplete lookups,
repeated company records, all nine nullable role combinations, non-reciprocal
record membership, fanout, table snapshot/rebuild behavior, and empty staged games.
Independent Python grouping compares every catalog value with staging and
relationship models. Four deliberate output defects (duplicate, NULL, missing,
extra game IDs) assert exact dbt failures and recover by rebuilding. Three malformed
projected inputs (rating, genre array, company role) fail materialization, retain
the previous table, and recover after source correction. All destructive fixture
operations are confined to disposable test schemas.

Existing staging/relationship SQL and tests remain intact. The shared build fixture
now expects nine models and 31 dbt tests. Staging corruption checks retain their
original twenty source/staging assertions with `--indirect-selection cautious`,
which excludes the new coverage test because its catalog parent is not selected.
Explicit, legacy, and explicit-over-legacy source precedence and independent
`DBT_SCHEMA` are exercised by every new database scenario.

Commands from the repository root, in execution order:

```bash
/opt/homebrew/bin/brew services run postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
# Baseline narrow offline: 19 passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_int_game_companies.py tests/test_dbt_int_game_platforms.py tests/test_dbt_int_game_genres.py tests/test_dbt_stg_games.py tests/test_dbt_staging_tests.py tests/test_dbt_sources.py
# Read-only raw/history hashes before database tests.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task64/snapshot_database.py
# Updated narrow offline: 22 passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_mart_game_catalog.py tests/test_dbt_int_game_companies.py tests/test_dbt_int_game_platforms.py tests/test_dbt_int_game_genres.py tests/test_dbt_stg_games.py tests/test_dbt_staging_tests.py tests/test_dbt_sources.py
# Narrow database: 33 passed, 72 deselected (27 catalog + six staging defect cases).
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_dbt_postgres.py -k 'game_catalog or staging_identifier'
# Full default: 438 passed, 120 skipped (ran while narrow database checks finished).
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
```

Remaining verification commands, after the narrow database run finished:

```bash
# Full enabled: 558 passed in 639.96 seconds.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
# Existing-data build, all model comparisons, raw/history preservation, schema cleanup.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task64/verify_existing_dbt.py
/opt/homebrew/bin/brew services stop postgresql@17
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task64/check_preservation.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task64/check_docs.py
git diff --check
```

The existing-data harness loads existing `.env` settings without overrides,
disables dbt usage reporting, and invokes:

```bash
/private/tmp/data-platform-phase1-venv/bin/python -c 'from dbt.cli.main import cli; cli()' build --project-dir /Users/patrick/Desktop/Code/data_platform/dbt --profiles-dir /Users/patrick/Desktop/Code/data_platform/dbt --no-partial-parse --target-path /private/tmp/data-platform-task64/existing-dbt/target --log-path /private/tmp/data-platform-task64/existing-dbt/logs
```

Result: **eight views, one table, and 31 passing dbt tests** (ten source, ten
staging, eight relationship, three catalog); no build warnings/errors/skips.
All nine models and 55 column descriptions match the manifest and actual database
columns. Every staging value still matches its five raw source rows; genre/platform
bridges match all 11/14 source-array pairs; all five company records match raw and
staged relationships. The catalog has exactly game IDs 1–5, with every scalar and
ordered JSONB object equal to independently grouped source-model values:

| game_id | Observed genre objects | Observed platform objects | Observed company record IDs |
|---|---|---|---|
| 1 | 3 | 1 | `[]` |
| 2 | 2 | 1 | `[6, 7]` |
| 3 | 3 | 2 | `[]` |
| 4 | 2 | 6 | `[]` |
| 5 | 1 | 4 | `[]` |

All eight unmatched genre and eight unmatched platform references survive with
JSON null names. Company records 2, 8, and 9 reference unloaded games and remain
in `int_game_companies`; they do not invent catalog games. Game 2 carries record
6/company 3/Looking Glass Studios (developer true, publisher false) and record
7/company 4/Eidos Interactive (developer false, publisher true). Empty company
arrays on the other four games reflect bounded observations only.

All test runs passed on their first execution. Service startup/readiness and
database tests/build ran outside the network sandbox, with startup succeeding
and readiness confirmed before database access. Existing raw/output schemas stay
`analytics`; no ingestion, migration, data clearing, watermark reset, or settings
change was needed. SHA-256 hashes of all five raw tables and ingestion history
matched before tests, before the existing-data build, and afterward. No disposable
schemas existed initially or remained after the suite/build. Fixtures cleaned
only their own schemas, including after deliberate failures. PostgreSQL was
restored to stopped/unregistered: Running/Loaded/Schedulable all false; final
readiness returned exit 2/no response.

Baseline hashes cover 162 files; 154 are unchanged and eight task files were
modified. The four new files are listed below. Existing `.env` (hashed without
copying), `.env.example`, `.gitignore`, raw archives, earlier relationship work,
and all 26 previously reported tracked generated/local artifacts were preserved.
Verification scripts, results, task-only diff, and baseline copies/hashes are under
`/private/tmp/data-platform-task64`; dbt artifacts stayed outside the repository.
Nothing was committed, deleted from the repository, or untracked. Documentation
links/anchors and whitespace checks passed. Only roadmap checkbox 6.4 changed.

Task-only files created:

- `dbt/models/marts/mart_game_catalog.sql`
- `dbt/models/marts/schema.yml`
- `dbt/tests/mart_game_catalog_game_coverage.sql`
- `tests/test_dbt_mart_game_catalog.py`

Task-only files modified: `tests/integration/test_dbt_postgres.py`,
`docs/CURRENT_STATE.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`,
`docs/pipeline/DBT_TRANSFORMATIONS.md`, `docs/engineering/LOCAL_DEVELOPMENT.md`,
`docs/engineering/DATA_QUALITY.md`, and this page. No source/staging/relationship
SQL or dependencies changed; at that point tasks 6.5 and later remained unimplemented.

The catalog is a table snapshot: rebuild after ingestion. Its arrays describe
observations in stored data and cannot prove complete IGDB coverage or real-world
absence. Company array lengths count relationship records, not distinct companies.
Nullable ratings/counts are descriptive values, without ranking thresholds.
The build evaluates catalog expressions, not every unused staging cast.

## Task 6.5 annual release trends verification

The two-column contract was documented before implementation in
[dbt transformations](../pipeline/DBT_TRANSFORMATIONS.md#mart_release_trends-task-65).
`mart_release_trends` uses the configured table materialization in independent
`DBT_SCHEMA`, directly over game-grain `stg_games`. Each row counts dated games
in one observed UTC calendar year of their game-level first release instant.
Explicit `AT TIME ZONE 'UTC'` prevents session-timezone drift. No relationship
joins, date cutoffs, platform/region expansion, or later-roadmap metrics were added.
NULL dates are excluded without implying unreleased games; unobserved years are
omitted without implying real-world absence. Summed counts plus undated games
reconcile to all staged games at the same snapshot. Zero/negative epochs retain
the existing staging cast behavior; malformed non-NULL timestamps fail evaluation.

Three offline cases protect lineage, UTC extraction, the two-column YAML contract,
materialization, and declared invariants. Thirty-nine new opt-in PostgreSQL cases
run under explicit, legacy, and explicit-over-legacy source-schema settings with
independent output schemas. They check exact types, manifest documentation, grain,
multiple games per year, multiple years, omitted intervening years, missing/JSON-null
dates, empty/all-undated input, zero/negative/castable-string epochs, future dates,
relationship multiplicities, table snapshot/rebuild behavior, and independent
Python UTC grouping/reconciliation. Each schema mode rebuilds under UTC,
America/Los_Angeles, and Asia/Tokyo sessions around UTC new-year boundaries.

Five dbt tests require unique/non-NULL year, non-NULL count, positive count, and
exact yearly reconciliation. Nine deliberate defects cover duplicate/NULL years,
NULL/zero/negative/wrong counts, missing/extra years, and a shifted year preserving
the total. Each asserts exact failed-test names and violation counts, then rebuilds
and requires all five tests to pass. Invalid non-NULL release input also fails
materialization, preserves the previous table, and recovers after source correction.
Only disposable schemas are modified by these negative cases.

Existing staging, relationship, and catalog SQL remains unchanged. The catalog's
offline test now locates its model by name in the shared YAML, retaining every
contract assertion. Shared database fixture totals now expect ten models and
36 dbt tests. Source precedence, independent output schema, cautious staging-test
selection, and all earlier assertions remain intact.

Exact commands from the repository root, in validation order:

```bash
/opt/homebrew/bin/brew services run postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
# Baseline narrow offline: 16 passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_mart_game_catalog.py tests/test_dbt_stg_games.py tests/test_dbt_staging_tests.py tests/test_dbt_sources.py
# Read-only baseline raw/history hashes; no disposable schemas initially.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task65/snapshot_database.py
# Updated narrow offline: 19 passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_mart_release_trends.py tests/test_dbt_mart_game_catalog.py tests/test_dbt_stg_games.py tests/test_dbt_staging_tests.py tests/test_dbt_sources.py
# Narrow PostgreSQL: 45 passed, 99 deselected in 366.11s (0:06:06) (39 release-trend + six staging defect cases).
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_dbt_postgres.py -k 'release_trends or staging_identifier' > /private/tmp/data-platform-task65/narrow-postgres.log 2>&1
# Full default, while narrow database checks ran: 441 passed, 159 skipped.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider
# Existing-data build and comparisons after narrow checks.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task65/verify_existing_dbt.py > /private/tmp/data-platform-task65/existing-build.log 2>&1
# Full enabled: 600 passed in 964.79s (0:16:04).
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider > /private/tmp/data-platform-task65/full-postgres.log 2>&1
```

The existing-data harness loads `.env` without overrides, disables dbt usage
reporting, and invokes:

```bash
/private/tmp/data-platform-phase1-venv/bin/python -c 'from dbt.cli.main import cli; cli()' build --project-dir /Users/patrick/Desktop/Code/data_platform/dbt --profiles-dir /Users/patrick/Desktop/Code/data_platform/dbt --no-partial-parse --target-path /private/tmp/data-platform-task65/existing-dbt/target --log-path /private/tmp/data-platform-task65/existing-dbt/logs
```

Result: **eight views, two tables, and 36 passing dbt tests** (ten source,
ten staging, eight relationship, three catalog, five release-trend), without
warnings/errors/skips. All ten models and 57 column descriptions match the manifest
and actual database columns. All existing staging/raw and relationship/source
comparisons pass; the five catalog games and every scalar/relationship object
still match. Independent Python UTC grouping of staging and catalog dates agrees
exactly with the new mart:

| release_year | release_count |
|---|---|
| 1998 | 2 |
| 2000 | 1 |
| 2004 | 1 |
| 2014 | 1 |

The stored sample has five dated games and zero undated games: 5 + 0 = 5 staged
and raw games. Other years are omitted. Existing raw/output schemas remain
`analytics`; no ingestion, migration, data clearing, watermark reset, or settings
change was needed.

All test runs passed on their first execution. Service startup/readiness and
database work ran outside the network sandbox. Raw/history SHA-256 hashes matched
before tests, before/after the existing-data build, and after the full suite.
No disposable schemas existed initially or remained afterward; fixtures dropped
only their own schemas, including after deliberate failures. PostgreSQL was
restored to stopped/unregistered: Running/Loaded/Schedulable all false and final
readiness exit 2/no response.

Final verification commands:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task65/final_database_check.py
/opt/homebrew/bin/brew services stop postgresql@17
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task65/check_preservation.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task65/check_docs.py
git diff --check
```

Baseline hashes cover 166 files: 156 unchanged and ten task files modified, plus
four new task files. Existing uncommitted work, `.env` (hashed without copying),
raw archives, and all 26 previously reported tracked generated/local artifacts
are preserved. No file was removed/untracked and nothing was committed.
Baseline copies/hashes, logs, verification scripts/results, and a task-only diff
are in `/private/tmp/data-platform-task65`; dbt artifacts stayed outside the
repository. Documentation links/anchors and whitespace checks pass.

Task-only files created:

- `dbt/models/marts/mart_release_trends.sql`
- `dbt/tests/mart_release_trends_positive_count.sql`
- `dbt/tests/mart_release_trends_yearly_reconciliation.sql`
- `tests/test_dbt_mart_release_trends.py`

Task-only files modified: `dbt/models/marts/schema.yml`,
`tests/test_dbt_mart_game_catalog.py`, `tests/integration/test_dbt_postgres.py`,
`docs/CURRENT_STATE.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`,
`docs/pipeline/DBT_TRANSFORMATIONS.md`, `docs/engineering/LOCAL_DEVELOPMENT.md`,
`docs/engineering/DATA_QUALITY.md`, and this page. Only checkbox 6.5 changed;
6.6 and later remain unchecked. No dependency was added.

The mart is a table snapshot: rebuild after ingestion before reconciling to current
staging. Counts describe stored observations, not complete IGDB coverage or verified
real-world releases/absence. Unknown release dates do not classify unreleased games.
The local sample's undated behavior is supplemented by synthetic missing/null and
all-undated cases. Identifier tests still do not validate unrelated staging casts.

## Task 6.6 genre/platform performance verification

The seven-column contracts, lineage and metric semantics were written before SQL
implementation in [dbt transformations](../pipeline/DBT_TRANSFORMATIONS.md#genreplatform-performance-task-66).
Two independent table marts group by observed dimension ID, deduplicate bridge
pairs before joining games, and attach labels afterward. Five descriptive metrics
cover observed games, non-NULL rating contributors, unweighted mean rating,
non-NULL rating-count contributors, and summed supplied rating counts. No weighting,
ranking, threshold, range filter, forecasting, or company-output work was added.
Unloaded/unnamed references survive; unobserved loaded dimensions are omitted.
Missing associations and labels have distinct meanings. NULL metrics remain
separate from supplied zero, and total_rating remains untouched in staging/catalog.

Six new offline cases protect lineage, independent aggregation, deduplication,
materialization, the exact documented projection, NULL policy, and reconciliation
of every column. Twenty-one new opt-in PostgreSQL cases exercise all three
source-schema modes and independent output schemas. They check actual column types,
manifest documentation, exact grain/metrics, multiple games and dimensions,
repeated source IDs/cast-normalized array IDs, duplicate labels, unmatched IDs,
missing/empty names, missing/null/zero/negative/decimal values, large IDs/counts,
empty/unassociated input, omitted dimensions, snapshot/rebuild behavior, and
source-array/bridge reconciliation. Python sets and Decimal arithmetic independently
check the evaluated metrics, including PostgreSQL's NUMERIC result precision.

Three dbt tests per mart declare unique/non-NULL ID and exact reconciliation.
The deliberate failure case corrupts each non-key column on its own observed row:
each of the five metrics is independently set to NULL, negative, zero, and wrong
positive values; two labels change to non-NULL values. It also deletes an observed
ID, adds an unobserved ID, adds a NULL ID, and duplicates a valid ID. Exact test
names/counts and the reconciliation query's returned IDs prove all independent
defects are detected: 25 reconciliation rows plus one unique and one not-null
violation per mart. Rebuild restores all six tests. A separate test doubles both
bridge views and proves every mart value is unchanged, then restores the views.
Invalid projected ratings/counts fail materialization, preserve previous tables,
and recover after correcting disposable fixture input. Cleanup runs on failures.

Existing tests retain their assertions. The shared build fixture now expects
12 models and 42 tests, and eight bridge-test invocations use
`--indirect-selection cautious` to isolate their three bridge invariants from the
new downstream reconciliation tests. Existing staging, relationship, catalog and
release SQL and contracts remain unchanged. Source precedence and independent DBT_SCHEMA behavior
are preserved. All dbt artifacts are external; no ingestion was needed.

Commands from the repository root, in validation order:

```bash
/opt/homebrew/bin/brew services run postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task66/snapshot_database.py
# Baseline narrow offline: 10 passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_mart_release_trends.py tests/test_dbt_mart_game_catalog.py tests/test_dbt_int_game_genres.py tests/test_dbt_int_game_platforms.py
# Updated narrow offline: 16 passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_mart_performance.py tests/test_dbt_mart_release_trends.py tests/test_dbt_mart_game_catalog.py tests/test_dbt_int_game_genres.py tests/test_dbt_int_game_platforms.py
# Narrow database: 27 passed, 138 deselected in 209.28s (0:03:29).
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_dbt_postgres.py -k 'performance or staging_identifier' > /private/tmp/data-platform-task66/narrow-postgres.log 2>&1
# Full default: 447 passed, 180 skipped in 1.94s (while narrow database checks ran).
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider > /private/tmp/data-platform-task66/full-default.log 2>&1
# Existing-data build and exact comparisons after narrow database checks.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task66/verify_existing_dbt.py > /private/tmp/data-platform-task66/existing-build.log 2>&1
# Initial full enabled run exposed bridge test selection: 10 failed, 39 passed;
# gracefully interrupted at 216.35s, preserving its log as full-postgres-initial.log.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider > /private/tmp/data-platform-task66/full-postgres.log 2>&1
# After adding cautious bridge selection: 10 narrow offline passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_mart_performance.py tests/test_dbt_int_game_genres.py tests/test_dbt_int_game_platforms.py
# Post-interruption check: raw/history hashes unchanged; no disposable schemas remain.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task66/final_database_check.py
# Affected bridge PostgreSQL checks: 30 passed, 135 deselected in 214.83s (0:03:34).
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_dbt_postgres.py -k 'game_genres or game_platforms' > /private/tmp/data-platform-task66/bridge-regression.log 2>&1
# Final full enabled: 627 passed in 1128.15s (0:18:48).
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider > /private/tmp/data-platform-task66/full-postgres.log 2>&1
```

The existing-data harness loads existing `.env` settings without overrides,
disables dbt usage reporting, and invokes:

```bash
/private/tmp/data-platform-phase1-venv/bin/python -c 'from dbt.cli.main import cli; cli()' build --project-dir /Users/patrick/Desktop/Code/data_platform/dbt --profiles-dir /Users/patrick/Desktop/Code/data_platform/dbt --no-partial-parse --target-path /private/tmp/data-platform-task66/existing-dbt/target --log-path /private/tmp/data-platform-task66/existing-dbt/logs
```

Result: **eight views, four tables, and 42 passing dbt tests** (ten source, ten
staging, eight relationship, three catalog, five release-trend, six performance).
All twelve models and 71 column descriptions match the manifest and actual
relations. Every earlier raw/staging/relationship/catalog/release comparison still
passes. Exact performance rows, including labels and all five metrics, match
independent Python grouping of staged values and distinct bridge pairs; bridge
pairs also match raw arrays. The local sample has four observed genres and nine
observed platforms. Summed game counts are 11 and 14 respectively across five
distinct games, demonstrating why these dimensions must not be summed as a game
population. Detailed rows follow; NULL names are retained for unloaded references.

`mart_genre_performance`:

| ID | name | game_count | rated_game_count | avg_rating | rating_count_game_count | rating_count_sum |
|---|---|---|---|---|---|---|
| 5 | Shooter | 3 | 3 | 79.1826865173220867 | 3 | 639 |
| 12 | NULL | 1 | 1 | 85.2566825387958900 | 1 | 353 |
| 13 | NULL | 3 | 3 | 84.6839715428176767 | 3 | 468 |
| 31 | NULL | 4 | 4 | 80.9887674409246850 | 4 | 815 |

`mart_platform_performance`:

| ID | name | game_count | rated_game_count | avg_rating | rating_count_game_count | rating_count_sum |
|---|---|---|---|---|---|---|
| 3 | Linux | 1 | 1 | 85.2566825387958900 | 1 | 353 |
| 6 | PC (Microsoft Windows) | 5 | 5 | 81.8423504604989260 | 5 | 1168 |
| 9 | NULL | 1 | 1 | 69.9031551352457100 | 1 | 347 |
| 11 | NULL | 1 | 1 | 81.7086974474386500 | 1 | 133 |
| 12 | NULL | 1 | 1 | 69.9031551352457100 | 1 | 347 |
| 14 | NULL | 2 | 2 | 77.5799188370208000 | 2 | 700 |
| 39 | NULL | 1 | 1 | 85.2566825387958900 | 1 | 353 |
| 48 | NULL | 1 | 1 | 69.9031551352457100 | 1 | 347 |
| 49 | NULL | 1 | 1 | 69.9031551352457100 | 1 | 347 |

The initial full run exposed a test-selection regression: dbt's eager indirect
selection added performance reconciliation to bridge-only test invocations,
violating their existing three-test assertions. Ten cases failed before a graceful
interrupt (39 passed). `--indirect-selection cautious` isolates the existing bridge
assertions, matching the established staging-test approach. The affected bridge
checks and final full suite pass after that repair; production model SQL was not
changed. Fixture cleanup completed after the interruption and hashes still matched.
Initial failure details are retained in `full-postgres-initial.log`.

Service startup/readiness and database work ran outside the network sandbox. Raw/history SHA-256 hashes matched
before tests, before/after the existing-data build, and after the full suite.
No disposable schemas existed initially or remained afterward. Fixtures dropped
only their own schemas. PostgreSQL was restored to stopped/unregistered:
Running/Loaded/Schedulable all false, and readiness exit 2/no response.

Final verification commands:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task66/final_database_check.py
/opt/homebrew/bin/brew services stop postgresql@17
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task66/check_preservation.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task66/check_docs.py
git diff --check
# Final offline run after documentation updates and PostgreSQL shutdown:
# 447 passed, 180 skipped in 1.85s.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider > /private/tmp/data-platform-task66/final-default.log 2>&1
```

Baseline hashes cover 170 files: 161 unchanged and nine task files modified,
plus five new task files. Existing uncommitted work, `.env` (hashed without copying),
raw archives, and all 26 previously reported tracked generated/local artifacts
are preserved. No migration, data clearing, watermark reset, deletion/untracking,
dependency addition, or commit occurred. Baseline copies, hashes, validation
scripts/results, external dbt targets/logs and a task-only diff are under
`/private/tmp/data-platform-task66`. Documentation links/anchors and whitespace
checks pass. Only roadmap checkbox 6.6 changed; 6.7 and later remain unchecked.

Created: `dbt/models/marts/mart_genre_performance.sql`,
`dbt/models/marts/mart_platform_performance.sql`,
`dbt/tests/mart_genre_performance_reconciliation.sql`,
`dbt/tests/mart_platform_performance_reconciliation.sql`, and
`tests/test_dbt_mart_performance.py`.

Modified: `dbt/models/marts/schema.yml`, `tests/integration/test_dbt_postgres.py`,
`docs/CURRENT_STATE.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`,
`docs/pipeline/DBT_TRANSFORMATIONS.md`, `docs/engineering/LOCAL_DEVELOPMENT.md`,
`docs/engineering/DATA_QUALITY.md`, and this page.

Marts are table snapshots: rebuild after ingestion before reconciliation. These
summaries describe bounded stored observations; missing associations/dimensions
are not verified real-world absence. A mean with few rated games is not equally
reliable as one with many; count context is descriptive and does not establish
representativeness. Count sums are not unique raters, and cross-dimension totals
repeat multi-associated games. Local-data missing-value coverage is supplemented
by synthetic fixtures. No unrelated staging cast validation is claimed.

## Task 6.7 company-output verification

The coverage decision and nine-column contract were documented before SQL in
[dbt transformations](../pipeline/DBT_TRANSFORMATIONS.md#mart_company_output-task-67).
Five existing relationship records reference five company IDs and three games;
two company IDs and two game IDs are unloaded. This supports bounded observed
output without additional ingestion. The table groups non-NULL company IDs,
retains unmatched references and missing/empty labels, distinguishes records from
distinct games, and exposes company/game loading context. Explicit true on any
record qualifies its non-NULL game for a role; NULL remains unknown. Role counts
can overlap, including across conflicting records. NULL-company records remain
upstream for reconciliation; loaded companies without observations are omitted.

Three offline cases protect lineage, materialization, grouping/join boundaries,
exact column documentation and independent reconciliation. Twenty-seven new opt-in
PostgreSQL cases exercise all three source-schema modes and independent DBT_SCHEMA.
Exact rows/types/manifest descriptions are checked alongside multiple games per
company, multiple companies per game, all nine nullable role combinations in
isolation and on repeated pairs, identical/differing role records, duplicate raw
record IDs and company labels, missing/empty names, NULL/unloaded references,
zero/negative/BIGINT-limit IDs, unobserved companies, empty/NULL-company input,
and table snapshot/rebuild behavior. Python sets independently reconcile every
mart value with raw, staged and relationship records.

The three dbt invariants are unique/non-NULL company ID and exact bidirectional
reconciliation of all nine columns. Deliberate corruption changes each of the six
count columns independently to NULL, negative, zero and a wrong positive value;
two label and two company-loaded defects are also isolated on separate observed
IDs. Missing/extra/NULL IDs and a duplicated ID prove population/key checks.
The tests assert every reconciliation violation (31 rows) and exact failed test
names/counts, then rebuild and require all three tests to pass. Doubled bridge
records and game/company lookups prove distinct-game metrics cannot inflate,
while upstream identifier checks still reject duplicates; restoration recovers.
Four malformed projected reference/role inputs fail materialization, preserve the
previous table, and recover after fixture correction. All mutations use disposable
schemas; existing raw data is never changed by fixtures.

Only shared fixture model/test totals and four existing company-bridge dbt test
invocations changed in earlier tests. Cautious indirect selection retains their
two original identity assertions without selecting downstream reconciliation.
Staging/genre/platform selection and every earlier model contract remain intact.
The first focused run was gracefully interrupted after five passing tests in
52.00 seconds to load that selection adjustment. Its log is retained; cleanup and
raw/history hashes passed before restarting. No test failure prompted this restart.

Exact commands from the repository root, in validation order:

```bash
/opt/homebrew/bin/brew services run postgresql@17
# Readiness: accepting connections before database work.
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
# Baseline narrow offline: 11 passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_int_game_companies.py tests/test_dbt_mart_performance.py tests/test_dbt_mart_game_catalog.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task67/snapshot_database.py
# Updated narrow offline: 14 passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_mart_company_output.py tests/test_dbt_int_game_companies.py tests/test_dbt_mart_performance.py tests/test_dbt_mart_game_catalog.py
# Focused PostgreSQL: 45 passed, 147 deselected in 370.08s (0:06:10) (27 new plus 12 company bridge and six staging cases).
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_dbt_postgres.py -k 'company_output or game_companies or staging_identifier' > /private/tmp/data-platform-task67/narrow-postgres.log 2>&1
# Full default: 450 passed, 207 skipped in 1.99s.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider > /private/tmp/data-platform-task67/full-default.log 2>&1
# Existing-data build, exact comparisons, preservation and schema-cleanup checks.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task67/verify_existing_dbt.py > /private/tmp/data-platform-task67/existing-build.log 2>&1
# Full enabled: 657 passed in 1417.90s (0:23:37).
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider > /private/tmp/data-platform-task67/full-postgres.log 2>&1
```

The existing-data harness loads `.env` without overrides, disables usage reporting,
and invokes:

```bash
/private/tmp/data-platform-phase1-venv/bin/python -c 'from dbt.cli.main import cli; cli()' build --project-dir /Users/patrick/Desktop/Code/data_platform/dbt --profiles-dir /Users/patrick/Desktop/Code/data_platform/dbt --no-partial-parse --target-path /private/tmp/data-platform-task67/existing-dbt/target --log-path /private/tmp/data-platform-task67/existing-dbt/logs
```

Result: **eight views, five mart tables and 45 passing dbt tests** (ten source,
ten staging, eight relationship, three catalog, five release-trend, six performance,
three company-output). Thirteen models and 80 columns have nonempty descriptions
matching the manifest and actual database columns. All earlier raw/staging,
relationship, catalog, release and performance comparisons pass. Every company
mart value matches independently grouped source records:

| company_id | name | company_loaded | relationship_record_count | null_game_relationship_count | game_count | loaded_game_count | developer_game_count | publisher_game_count |
|---|---|---|---|---|---|---|---|---|
| 1 | Electronic Arts | true | 1 | 0 | 1 | 0 | 0 | 1 |
| 3 | Looking Glass Studios | true | 1 | 0 | 1 | 1 | 1 | 0 |
| 4 | Eidos Interactive | true | 1 | 0 | 1 | 1 | 0 | 1 |
| 7 | NULL | false | 1 | 0 | 1 | 0 | 1 | 0 |
| 11 | NULL | false | 1 | 0 | 1 | 0 | 1 | 0 |

Five record counts plus zero NULL-company records reconcile to all five stored
relationships. Five summed game counts represent distinct company/game pairs,
not the three distinct game references across companies. Two summed loaded-game
counts both reference game 2. Loaded companies 2/5 have no observed relationships
and are omitted without asserting absence. No ingestion, migration, data clearing,
watermark reset, settings change or dependency addition was needed.

Final commands:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task67/final_database_check.py
/opt/homebrew/bin/brew services stop postgresql@17
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task67/check_preservation.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task67/check_docs.py
git diff --check
# Final default after documentation updates and shutdown: 450 passed, 207 skipped in 2.00s.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider > /private/tmp/data-platform-task67/final-default.log 2>&1
```

Service startup and database work ran outside the network sandbox. SHA-256 hashes
of all five raw tables and ingestion history matched before tests, before/after
the build, and after the full suite. No disposable schemas remained. PostgreSQL
was restored to stopped/unregistered: Running/Loaded/Schedulable all false and
readiness exit 2/no response. External dbt artifacts, logs, baseline copies/hashes,
verification scripts/results and a task-only diff are in
`/private/tmp/data-platform-task67`. Of 175 baseline files, 166 are unchanged and
nine task files modified; three files were created. Earlier uncommitted work,
`.env`, raw archives and all 26 previously reported tracked generated/local files
are preserved. Nothing was committed, deleted or untracked. Documentation links
and whitespace checks pass. Only roadmap checkbox 6.7 changed; 6.8 and later remain
unchecked.

Created: `dbt/models/marts/mart_company_output.sql`,
`dbt/tests/mart_company_output_reconciliation.sql`, and
`tests/test_dbt_mart_company_output.py`.
Modified: `dbt/models/marts/schema.yml`, `tests/integration/test_dbt_postgres.py`,
`docs/CURRENT_STATE.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`,
`docs/pipeline/DBT_TRANSFORMATIONS.md`, `docs/engineering/LOCAL_DEVELOPMENT.md`,
`docs/engineering/DATA_QUALITY.md`, and this page.

This is a rebuildable table snapshot of bounded observations. Omitted companies,
zero role counts, missing labels and unloaded references do not establish complete
catalogs or verified absence. Developer and publisher counts may overlap; neither
role nor cross-company counts should simply be summed as distinct games. Passing
these checks does not validate unrelated/unprojected staging casts or source
completeness. Local coverage is supplemented by synthetic role/null/duplicate cases.

## Test-harness optimization verification

Verified October 2, 2026 as an explicitly requested optimization before task 6.8.
No roadmap checkbox changed. Production Python, dbt SQL/YAML/profiles, warehouse
contracts, and all 45 dbt invariants are unchanged. No dependency was added.

The former function-scoped `built_staging` fixture ran a full 13-model/45-test
build before every dbt case. Its environment fixture multiplied all 64 behavior
scenarios by three schema modes: 192 initial full builds, or 2,496 model builds
and 8,640 dbt test executions before scenario-specific work. The recorded 6.7 full
suite took 1,417.90 seconds (23m 37s), with 657 passing cases.

The optimized setup separates fixture loading from model execution. Each behavior
case uses fresh source/output schemas, builds five staging views plus explicitly
marked model ancestors, and retains its original value/failure/recovery assertions.
Three dedicated full-project cases retain all prior full-build assertions and add
all-model column documentation checks, independent mart/source comparisons, and
fresh/cached manifest resolution parity. Every schema case runs all 45 dbt tests
both after a fresh build and on a subsequent cached invocation. Only repeated
commands within the same test can reuse parsing; no database or parse cache is
shared between scenarios. Existing opt-in, HTTP rejection, failure cleanup,
source-schema precedence and independent DBT_SCHEMA behavior remain intact.

A baseline-to-current AST/collection audit confirms that **all 38 existing test
function bodies and their non-schema parameter decorators are unchanged**, and
all 64 distinct behavior cases still collect. Only explicit model-dependency
markers were added to those functions. Their 128 repeated executions under the
two alternate schema modes were replaced by three complete configuration cases.
This intentionally removes the data-edge-case × schema-mode Cartesian product,
not any distinct edge case. The [coverage matrix](#postgresql-integration-tests)
maps every family. The 450 offline cases and 15 ingestion database cases remain
unchanged. Default collection is now 450 offline plus 82 opt-in cases; the full
enabled suite has 532 cases. Lower case counts reflect reduced repetition.

| Measurement | Before | After |
|---|---|---|
| Same 11 primary-schema company/staging scenarios | 91.07s | 66.79s (26.7% less time) |
| Full enabled suite | 657 passed in 1,417.90s | 532 passed in 358.87s (0:05:58) (74.7% less time) |
| Default suite | 450 passed, 207 skipped in about 2s | 450 passed, 82 skipped in 1.93s; final check: 450 passed, 82 skipped in 1.83s |
| Dedicated full-project schema cases | Repeated setup in all 192 cases | 3 passed in 15.94s |

The focused comparison was measured sequentially on the same local environment.
The full comparison uses the immediately preceding task's recorded run on this
machine; these are individual observations, not a performance guarantee. The
optimized full run records 167 dbt CLI calls taking 349.39 seconds in aggregate, with 100 confirmed parse-cache hits. Most remaining wall time is still
in dbt CLI invocations. No parallel execution or shared mutable fixture was added.
Failure-case consolidation was unnecessary for this first optimization; all
existing failure scenarios stay individually diagnosable.

Exact commands from the repository root:

```bash
/opt/homebrew/bin/brew services run postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-test-optimization/snapshot_database.py
# Baseline collection: 192 dbt cases; no database execution.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest --collect-only -q -p no:cacheprovider tests/integration/test_dbt_postgres.py > /private/tmp/data-platform-test-optimization/before-collection.txt
# Baseline representative run: 11 passed, 181 deselected in 91.07s.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_dbt_postgres.py -k 'explicit and not explicit_over_legacy and (company_output or staging_identifier)' --durations=20 --junitxml=/private/tmp/data-platform-test-optimization/before-narrow.xml > /private/tmp/data-platform-test-optimization/before-narrow.log 2>&1
# Updated collection: 67 dbt cases, with strict marker registration.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest --collect-only -q -p no:cacheprovider --strict-markers tests/integration/test_dbt_postgres.py > /private/tmp/data-platform-test-optimization/after-collection.txt
# Every existing behavior body/parameter combination retained.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-test-optimization/check_coverage.py
# Narrow offline: 20 passed.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_sources.py tests/test_dbt_staging_tests.py tests/test_dbt_mart_company_output.py tests/test_dbt_mart_performance.py
# Same representative scenarios after optimization: 11 passed, 56 deselected in 66.79s.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider --strict-markers tests/integration/test_dbt_postgres.py -k 'company_output or staging_identifier' --durations=20 --junitxml=/private/tmp/data-platform-test-optimization/after-narrow.xml > /private/tmp/data-platform-test-optimization/after-narrow.log 2>&1
# Dedicated full-build/configuration/cache checks: 3 passed, 64 deselected in 15.94s.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider --strict-markers tests/integration/test_dbt_postgres.py -k full_project_schema_modes --durations=10 > /private/tmp/data-platform-test-optimization/schema-modes.log 2>&1
# Full default: 450 passed, 82 skipped in 1.93s.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider --strict-markers > /private/tmp/data-platform-test-optimization/full-default.log 2>&1
# Full enabled, retaining per-test and per-dbt-command timing artifacts externally.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider --strict-markers --durations=25 --junitxml=/private/tmp/data-platform-test-optimization/full-postgres.xml --basetemp=/private/tmp/data-platform-test-optimization/full-pytest > /private/tmp/data-platform-test-optimization/full-postgres.log 2>&1
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-test-optimization/analyze_timings.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-test-optimization/final_database_check.py
/opt/homebrew/bin/brew services stop postgresql@17
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
# Final offline check after documentation updates and shutdown.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider --strict-markers > /private/tmp/data-platform-test-optimization/final-default.log 2>&1
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-test-optimization/check_preservation.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-test-optimization/check_docs.py
git diff --check
```

All test runs passed. Existing raw/history hashes match and no disposable schemas
remain. PostgreSQL is stopped/unregistered: Running/Loaded/Schedulable all false,
readiness exit 2/no response. No existing local mart needed rebuilding because
production models did not change. Database validation built the actual project
in isolated schemas; no live IGDB access, ingestion, migration, data clearing or
watermark reset occurred.

Modified only `tests/integration/test_dbt_postgres.py`,
`tests/integration/conftest.py`, `docs/CURRENT_STATE.md`,
`docs/engineering/TESTING.md`, `docs/engineering/LOCAL_DEVELOPMENT.md`, and
`docs/pipeline/DBT_TRANSFORMATIONS.md`. No repository file was created or removed.
Of 178 baseline files, 172 hashes remain unchanged and six task files changed.
Existing uncommitted work, `.env`, raw archives and the 26 previously reported
tracked artifacts are preserved. Nothing was committed or untracked. Baseline
copies/hashes, coverage mapping, logs/XML, invocation timings, verification scripts
and a task-only diff are under `/private/tmp/data-platform-test-optimization`.
Documentation links and whitespace checks pass. Task 6.8 remains unchecked.

## Task 6.8 mart contract audit verification

Verified October 2, 2026. The [coverage matrix](DATA_QUALITY.md#mart-contract-coverage-matrix-task-68)
links all five marts' documented grain, population and metrics to declared dbt
invariants, independent integration value checks and unsupported completeness
claims. All 36 mart columns (80 across all 13 models) retain documented types,
nullability and meaning. Shared refresh/snapshot and denominator semantics are
explicit. No production model SQL violated its contract or needed modification.

Existing release/performance/company reconciliations already check every metric,
label and observed group; their deliberate failures and recovery remain sufficient.
The catalog's exact scalar/object values, ordering, role/null/reference semantics
and fanout already have independent integration coverage. One justified gap was
closed: dbt now checks its three required JSON array containers. The new singular
`mart_game_catalog_relationship_arrays` test returns one row per invalid game/column,
using NULL-safe JSON type checking without constraining nullable object values.

One new primary-schema scenario corrupts each container with SQL NULL, JSON null,
an object and a scalar. It asserts the exact 12 returned game/column pairs, the
sole failed test name and count, three other passing catalog tests, then recovery
of all four catalog tests and every source-derived value after rebuilding. Existing
NULL/extra catalog-row defects now also assert three container violations; all
previous failure assertions remain. The check depends only on the catalog, so no
source/staging/relationship selection or cautious-selection change was needed.

The optimized fixtures/cache handling are unchanged. AST comparison confirms all
existing functions and parameter decorators remain; only catalog expectations and
full-project totals changed. The suite retains 64 earlier behavior scenarios,
adds one, keeps three dedicated full-project schema-mode checks, and retains 15
ingestion cases: **68 dbt / 83 total database cases**, without three-way behavior
parametrization or unrelated full-project setup. No dependency was added.

Exact commands from the repository root, in validation order (logs/artifacts external):

```bash
# Baseline and updated narrow offline runs: 15 passed each, 0.08s each.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dbt_mart_game_catalog.py tests/test_dbt_mart_release_trends.py tests/test_dbt_mart_performance.py tests/test_dbt_mart_company_output.py
/opt/homebrew/bin/brew services run postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
# Accepting connections before snapshot/tests; startup/database work outside network sandbox.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task68/snapshot_database.py
# Narrow database: 15 passed, 53 deselected in 86.14s.
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider --strict-markers tests/integration/test_dbt_postgres.py -k 'game_catalog or staging_identifier or full_project_schema_modes' > /private/tmp/data-platform-task68/narrow-postgres.log 2>&1
# Full default: 450 passed, 83 skipped in 1.81s.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider --strict-markers > /private/tmp/data-platform-task68/full-default.log 2>&1
# Full enabled: 533 passed in 373.86s (0:06:13).
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider --strict-markers --durations=25 --junitxml=/private/tmp/data-platform-task68/full-postgres.xml --basetemp=/private/tmp/data-platform-task68/full-pytest > /private/tmp/data-platform-task68/full-postgres.log 2>&1
# AST audit passed; collection: 68 dbt cases.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task68/check_coverage.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest --collect-only -q -p no:cacheprovider --strict-markers tests/integration/test_dbt_postgres.py > /private/tmp/data-platform-task68/collection.txt
# Existing-data build and all independent comparisons passed.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task68/verify_existing_dbt.py > /private/tmp/data-platform-task68/existing-build.log 2>&1
```

The reused existing-data script loads `.env` without overrides and disables dbt
usage reporting. It runs this exact build, with all targets/logs external:

```bash
/private/tmp/data-platform-phase1-venv/bin/python -c 'from dbt.cli.main import cli; cli()' build --project-dir /Users/patrick/Desktop/Code/data_platform/dbt --profiles-dir /Users/patrick/Desktop/Code/data_platform/dbt --no-partial-parse --target-path /private/tmp/data-platform-task68/existing-dbt/target --log-path /private/tmp/data-platform-task68/existing-dbt/logs
```

Result: **eight views, five tables, 46 passing dbt tests** (10 source, 10 staging,
8 relationship, 4 catalog, 5 release, 6 performance, 3 company-output). All 13 model
and 80 column descriptions match the manifest and actual database columns. Reused
Python grouping/set/Decimal helpers independently compare every mart column with
source models, alongside raw/staging/relationship comparisons:

| Existing mart | Verified result |
|---|---|
| Catalog | Five games; all scalar/ordered object values match; 11 genre, 14 platform and two company-record objects |
| Release trends | 1998: 2; 2000/2004/2014: 1 each; five dated plus zero undated equals five staged games |
| Genre performance | Four rows; every metric/label matches; summed game counts 11 across five games |
| Platform performance | Nine rows; every metric/label matches; summed game counts 14 across five games |
| Company output | Five rows; all nine columns match; two unloaded companies and two distinct unloaded game references retained |

No ingestion was necessary. Raw/output schemas stay on the existing configuration;
no migration, raw clearing, watermark reset, settings edit or dependency change
occurred. Every test run passed on its first execution. The 6:13 full-suite run
retains the optimized harness's approximate six-minute runtime; it is a single
measurement, not a performance guarantee.

Final verification commands:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/patrick/Desktop/Code/data_platform PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task68/final_database_check.py
/opt/homebrew/bin/brew services stop postgresql@17
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task68/check_preservation.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task68/check_docs.py
git diff --check
# Final default after documentation updates and shutdown: 450 passed, 83 skipped.
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider --strict-markers > /private/tmp/data-platform-task68/final-default.log 2>&1
```

All five raw-table and ingestion-history hashes match the pre-test snapshot;
no disposable schemas remain. PostgreSQL is stopped/unregistered:
Running/Loaded/Schedulable all false; readiness exit 2/no response. `.env`, local
raw archives, previous uncommitted changes and all 26 previously reported tracked
generated/local artifacts are preserved. Nothing was deleted, untracked or committed.
The working-tree baseline (copies/hashes plus Git status/diff) is saved under
`/private/tmp/data-platform-task68-baseline*`; private-file hashes, scripts, logs,
results, dbt artifacts and `task-only.diff` are in `/private/tmp/data-platform-task68`.

Created: `dbt/tests/mart_game_catalog_relationship_arrays.sql`.
Modified: `dbt/models/marts/schema.yml`, `tests/integration/test_dbt_postgres.py`,
`docs/CURRENT_STATE.md`, `docs/ROADMAP.md`, `docs/pipeline/DBT_TRANSFORMATIONS.md`,
`docs/engineering/DATA_QUALITY.md`, `docs/engineering/LOCAL_DEVELOPMENT.md`, and this
page. Only roadmap 6.8 is newly checked; Phase 6 is complete and Phase 7/later remain
unchecked. Architecture and production model SQL are unchanged. The coverage
matrix records the remaining limits: catalog element values/order are protected
by integration checks, reconciliation needs refreshed snapshots/stable sources,
and bounded observations cannot establish source completeness or real-world absence.

## Task 7.1 Docker PostgreSQL validation

October 2, 2026 initial attempt: configuration verified; runtime was blocked.
The [Colima follow-up](#task-71-colima-runtime-follow-up) records resolution and
subsequent runtime results.
The audit found only `docker/.gitkeep`, no Docker/Compose executables on PATH,
no Docker Desktop/Colima/Podman/OrbStack installation in standard locations, and
no standard Docker socket. Native Homebrew PostgreSQL was stopped/unregistered
(Running/Loaded/Schedulable false, readiness exit 2) and was never started.

A working-tree baseline, copies of tracked/untracked source files, Git diffs,
and hashes of `.env`, local raw archives, generated/private files and the stopped
native cluster were saved under `/private/tmp/data-platform-task71-8mo40vcm`.
Secrets were hashed only. The 26 previously reported tracked generated/local
artifacts remain untouched. No Python, dbt, dependency, test-harness, `.env`, or
index changes were made.

For daemon-independent checks, the official standalone [Compose v5.6.0](https://github.com/docker/compose/releases/tag/v5.6.0) ARM64
binary was downloaded to that temporary directory and verified against the GitHub
release asset SHA-256. No engine or system package was installed. The external
`check_compose.py` invokes real Compose with `--env-file /dev/null`, a distinct
project name, and synthetic credentials held in process memory:

```bash
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task71-8mo40vcm/check_compose.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider --strict-markers --basetemp=/private/tmp/data-platform-task71-8mo40vcm/default-pytest > /private/tmp/data-platform-task71-8mo40vcm/default.log 2>&1
git diff --check
```

Results: quiet config validation passed; six unset/empty database/user/password
cases were rejected; default/overridden host ports and literal secret rendering
passed; changing the project name selected a distinct volume. No resolved
credentials were printed or saved. The first checker run incorrectly expected
unescaped dollar signs in serialized JSON; adjusting the checker for Compose's
`$$` serialization made all ten checks pass without changing the service.
The default suite passed **450, with 83 skipped, in 1.78s**; whitespace checks passed.
No static configuration-text test or new dependency was added. Runtime persistence
is the meaningful acceptance test and remains pending below.

Read-only Docker Hub registry inspection of `postgres:17.11-bookworm` verified
Linux ARM64 support, `PG_MAJOR=17`, `PG_VERSION=17.11-1.pgdg12+2`,
`PGDATA=/var/lib/postgresql/data`, the matching declared volume, port 5432,
`docker-entrypoint.sh`, `postgres`, and `SIGINT`. The observed manifest-list digest
was `sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652`;
the ARM64 manifest was `sha256:75731e2765e7d0c8bb7dea960ef3bdcde68d16314991ab2057a2a74ea0fff257`.
Metadata is retained in `image-metadata.json`; no image layers were downloaded.
The committed tag is version-specific, not digest-pinned. See the linked official
image sources in [local development](LOCAL_DEVELOPMENT.md#docker-postgresql-task-71).

With synthetic database/user/password exports, `POSTGRES_PORT=55471`, and
`DOCKER_HOST=unix:///var/run/docker.sock`, the actual startup attempt was:

```bash
/private/tmp/data-platform-task71-8mo40vcm/docker-compose --env-file /dev/null -p data-platform-task71-8mo40vcm -f /Users/patrick/Desktop/Code/data_platform/compose.yaml up -d --wait --wait-timeout 120 postgres
```

It exited **1**: the Docker API socket did not exist. No container, network, volume,
or disposable schema was created, so no Docker resource cleanup was needed.
**Health transitions, authenticated SQL access, marker persistence across container
removal/recreation, shutdown behavior, and the full enabled integration suite were
not verified.** The earlier task 6.8 result of 533 passes is not Docker evidence.
No IGDB calls or native database writes occurred.

Final preservation checks:

```bash
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task71-8mo40vcm/check_preservation.py
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h 127.0.0.1 -p 5432
git diff --check
```

Of 1,503 baseline file hashes, 1,497 remain identical and only six authorized
documentation files changed; `compose.yaml` is the sole new repository file.
The native cluster files, `.env`, raw archives, integration harness, model files,
private/generated artifacts, Git index and roadmap checkboxes are unchanged.
Native service flags remain false; readiness returns exit 2/no response.
The operation examples parse with `bash -n` and their relative links resolve.
The baseline comparison is saved as `task-only.diff` beside scripts and logs.
Nothing was committed, deleted or untracked.

### Repeatable isolated runtime procedure

Run only after Docker is available. This procedure uses an independently named
disposable project and high host port, never the normal project volume or native
cluster. Execute from the repository root in a dedicated Bash shell. Stop if the
chosen port is occupied and choose a free port; do not stop an unrelated service.
The trap removes only resources owned by this fresh validation project, including
its disposable volume. Normal development uses `down` **without** `--volumes`.

```bash
set -e
docker info > /dev/null
TASK71_DIR=$(mktemp -d /private/tmp/data-platform-task71-runtime.XXXXXX)
TASK71_PROJECT="data-platform-task71-$(uuidgen | tr '[:upper:]' '[:lower:]')"
export POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55471
export POSTGRES_DB=task71_validation POSTGRES_USER=task71_validation
export POSTGRES_RAW_SCHEMA=raw DBT_SCHEMA=analytics
export PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5
TASK71_PYTHON=/private/tmp/data-platform-phase1-venv/bin/python
POSTGRES_PASSWORD=$("$TASK71_PYTHON" -c 'import secrets; print(secrets.token_hex(32))')
export POSTGRES_PASSWORD
dc71() { docker compose --env-file /dev/null -p "$TASK71_PROJECT" -f compose.yaml "$@"; }
test -z "$(dc71 ps --all --quiet)"
if docker volume inspect "${TASK71_PROJECT}_postgres_data" > /dev/null 2>&1; then
    echo 'Validation volume already exists; choose another project.'
    exit 1
fi
trap 'dc71 down --volumes; unset POSTGRES_PASSWORD' EXIT
dc71 config --quiet
dc71 up -d --wait --wait-timeout 120 postgres
dc71 ps

cat > "$TASK71_DIR/probe.py" <<'PY'
import os
import sys
import psycopg

with psycopg.connect(host=os.environ['POSTGRES_HOST'], port=os.environ['POSTGRES_PORT'],
                     dbname=os.environ['POSTGRES_DB'], user=os.environ['POSTGRES_USER'],
                     password=os.environ['POSTGRES_PASSWORD'], connect_timeout=5) as conn:
    assert conn.execute('SELECT current_database(), current_user').fetchone() == (
        os.environ['POSTGRES_DB'], os.environ['POSTGRES_USER'])
    if sys.argv[1] == 'seed':
        conn.execute('CREATE SCHEMA task71_probe')
        conn.execute('CREATE TABLE task71_probe.marker (value text PRIMARY KEY)')
        conn.execute('INSERT INTO task71_probe.marker VALUES (%s)', ('task71-persistent-marker',))
    else:
        assert conn.execute('SELECT value FROM task71_probe.marker').fetchall() == [
            ('task71-persistent-marker',)]
        if sys.argv[1] == 'cleanup':
            assert not conn.execute(
                "SELECT nspname FROM pg_namespace WHERE starts_with(nspname, 'test_dp_')"
            ).fetchall(), 'Integration schemas remain; inspect before cleanup'
            conn.execute('DROP SCHEMA task71_probe CASCADE')
print('Authenticated database/marker check passed:', sys.argv[1])
PY

"$TASK71_PYTHON" "$TASK71_DIR/probe.py" seed
TASK71_OLD_CONTAINER=$(dc71 ps --quiet postgres)
test -n "$TASK71_OLD_CONTAINER"
dc71 down
test -z "$(dc71 ps --all --quiet)"
docker volume inspect --format '{{.Name}}' "${TASK71_PROJECT}_postgres_data"
dc71 up -d --wait --wait-timeout 120 postgres
TASK71_NEW_CONTAINER=$(dc71 ps --quiet postgres)
test -n "$TASK71_NEW_CONTAINER"
test "$TASK71_OLD_CONTAINER" != "$TASK71_NEW_CONTAINER"
"$TASK71_PYTHON" "$TASK71_DIR/probe.py" read
# Also exercise stop/start; this alone would not prove replacement persistence.
dc71 stop postgres
test -z "$(dc71 ps --status running --quiet)"
dc71 up -d --wait --wait-timeout 120 postgres
"$TASK71_PYTHON" "$TASK71_DIR/probe.py" read

RUN_POSTGRES_INTEGRATION=0 "$TASK71_PYTHON" -m pytest -q -p no:cacheprovider --strict-markers --basetemp="$TASK71_DIR/default"
RUN_POSTGRES_INTEGRATION=1 "$TASK71_PYTHON" -m pytest -q -p no:cacheprovider --strict-markers --durations=25 --basetemp="$TASK71_DIR/enabled"
"$TASK71_PYTHON" "$TASK71_DIR/probe.py" cleanup
dc71 down --volumes
test -z "$(dc71 ps --all --quiet)"
if docker volume inspect "${TASK71_PROJECT}_postgres_data" > /dev/null 2>&1; then
    echo 'Disposable volume cleanup failed.'
    exit 1
fi
trap - EXIT
unset POSTGRES_PASSWORD
/opt/homebrew/bin/brew services info postgresql@17
# Expect exit 2/no response; native PostgreSQL must remain stopped/unregistered.
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h 127.0.0.1 -p 5432 || test "$?" -eq 2
```

Record the two different container IDs, retained volume, successful marker reads,
suite results and final cleanup before checking off 7.1. The optimized
harness must retain its structure: 65 behavior scenarios, three full-project schema
checks, and 15 ingestion cases. It creates/cleans its own schemas, writes dbt
artifacts beneath the external pytest directory, and rejects live HTTP requests.
The marker uses its own schema and is committed before container removal. None
of this procedure initializes or migrates the project's real raw data/history.

### Task 7.1 Colima runtime follow-up

The user selected Colima and requested the engine fix and proper testing.
Installed ARM Homebrew packages without upgrading existing formulae, dependent
packages, or invoking automatic cleanup:

```bash
HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_CLEANUP=1 HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK=1 /opt/homebrew/bin/brew install --dry-run colima docker docker-compose
HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_CLEANUP=1 HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK=1 HOMEBREW_NO_INSTALL_UPGRADE=1 /opt/homebrew/bin/brew install --no-ask colima docker docker-compose
```

Installed Colima 0.10.3, Lima 2.2.0, Docker CLI 29.8.1 and Compose 5.5.1.
Created a new private `~/.config/data-platform/docker/config.json` with the
Homebrew Compose plugin directory; the existing Docker configuration/credentials
were retained byte-for-byte. No Docker Desktop helper or global socket change was
needed. The named VM was created with:

```bash
PATH="/opt/homebrew/bin:$PATH" DOCKER_CONFIG=/Users/patrick/.config/data-platform/docker /opt/homebrew/bin/colima start data-platform --vm-type vz --runtime docker --cpus 2 --memory 2 --disk 10 --mount none --ssh-config=false --activate=false
```

The engine listens at `~/.colima/data-platform/docker.sock`. Validation explicitly
selects it with `DOCKER_HOST` and the separate `DOCKER_CONFIG`; it does not depend
on a default Docker context or `/var/run/docker.sock`. No host directory is mounted
into this VM. No Homebrew service/login startup was enabled. See [daily shell
setup and shutdown](LOCAL_DEVELOPMENT.md#colima-on-this-mac).

The first Docker run passed health, correct-password access, incorrect-password
rejection, marker persistence after container removal/recreation, stop/start,
and the default suite (**450 passed, 83 skipped in 1.85s**). The full enabled run
reported **532 passed, 1 failed in 370.69s**. The failure was the timezone test's
secondary connection: `ConnectionInfo.dsn` omits the password, so it raised
`fe_sendauth: no password supplied`. This matches [Psycopg's documented contract](https://www.psycopg.org/psycopg3/docs/api/objects.html#psycopg.ConnectionInfo.dsn).
The test now passes `connection.info.password` explicitly when reconnecting.
This is the only test change; production Python/model SQL, scenario counts,
optimized setup and schema-mode coverage are unchanged. The original task baseline
preserves the earlier uncommitted test edits. No password is written to logs.

The failing run cleaned its disposable project/volume in `finally`. A fresh retry
project repeats lifecycle validation, runs the affected case first, then runs both
full suites. Scripts, logs, dbt artifacts, and structured evidence remain external:

```bash
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task71-runtime-k5bp26ak/check_compose.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task71-runtime-k5bp26ak/validate_runtime.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task71-runtime-k5bp26ak/retry/validate_runtime.py
```

The installed Compose passes all ten narrow configuration checks. The corrected
timezone test passes (**1 passed in 8.28s**), and the retry default suite passes
**450 with 83 skipped in 1.85s**. The full enabled suite passes **533 in 374.61s
(6:14)**. Each of the three full-project schema checks built all 13 models with
80 documented columns and passed all 46 dbt tests. All 65 behavior scenarios and
15 ingestion cases remain; no per-scenario full-project setup or three-way behavior
parametrization was introduced.

The retry script supplies explicit host `127.0.0.1`, port `55471`, database/user
`task71_validation`, raw/output schemas `raw`/`analytics`, and a generated password
held only in memory. With those connection exports, its exact pytest invocations
were:

```bash
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider --strict-markers --durations=25 --basetemp=/private/tmp/data-platform-task71-runtime-k5bp26ak/retry/narrow-pytest tests/integration/test_dbt_postgres.py::test_release_trends_values_utc_grain_and_reconciliation
RUN_POSTGRES_INTEGRATION=0 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider --strict-markers --durations=25 --basetemp=/private/tmp/data-platform-task71-runtime-k5bp26ak/retry/default-pytest
RUN_POSTGRES_INTEGRATION=1 PYTHONDONTWRITEBYTECODE=1 PGCONNECT_TIMEOUT=5 /private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider --strict-markers --durations=25 --basetemp=/private/tmp/data-platform-task71-runtime-k5bp26ak/retry/enabled-pytest
```

Persistence evidence for project `data-platform-task71-k5bp26ak-retry`:

- Server: PostgreSQL `17.11 (Debian 17.11-1.pgdg12+2)`, Docker Engine 29.5.2.
- Container `26026f53b23c` became healthy, accepted the intended login/database,
  rejected an incorrect password, and committed a synthetic marker.
- `compose down` removed that container; inspecting its old ID failed as expected.
  The volume `data-platform-task71-k5bp26ak-retry_postgres_data` remained.
- `compose up -d --wait --wait-timeout 120 postgres` created a different container,
  `b5136777208c`. Its only mount was that named volume at `/var/lib/postgresql/data`.
  The authenticated host connection read back the exact committed marker.
- `compose stop postgres` left no running project container; a subsequent `up`
  became healthy and retained the marker again. This supplements the actual
  removal/recreation proof.
- After the suites, no integration schemas remained. The probe schema was dropped,
  then project-scoped `down --volumes` removed only the retry resources. Checks
  confirmed no project container, network, or volume remained. The failed first
  run likewise removed its own project resources.

Full IDs, exact Compose commands, return codes, mounts, and SQL/persistence assertions
are recorded in `retry/runtime-evidence.json`. All artifacts remain beneath
`/private/tmp/data-platform-task71-runtime-k5bp26ak`. No live IGDB request, real-data
ingestion, native database write, migration, watermark reset, or model change occurred.

Final shutdown and preservation commands:

```bash
PATH="/opt/homebrew/bin:$PATH" DOCKER_CONFIG=/Users/patrick/.config/data-platform/docker /opt/homebrew/bin/colima stop data-platform
PATH="/opt/homebrew/bin:$PATH" DOCKER_CONFIG=/Users/patrick/.config/data-platform/docker /opt/homebrew/bin/colima list
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/bin/brew services info colima
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h 127.0.0.1 -p 5432
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task71-runtime-k5bp26ak/check_completion.py
git diff --check
```

Colima is stopped, and both Homebrew services remain stopped/unregistered. The
native PostgreSQL readiness check returns exit 2/no response. Of 1,503 original
baseline file hashes, 1,496 are unchanged; six documentation files and the single
integration-test correction account for all differences. `.env`, native cluster
files, raw archives/history, generated/private artifacts and the Git index are
preserved. The original Docker client config hash also matches. All other integration
test bodies and fixtures are identical to the saved baseline. Installed tools and
the stopped VM/cached image remain available for future sessions.

Task-only repository changes: new `compose.yaml`; modified `docs/CURRENT_STATE.md`,
`docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/engineering/LOCAL_DEVELOPMENT.md`,
this page, `docs/pipeline/RAW_STORAGE.md`, and `tests/integration/test_dbt_postgres.py`.
The cumulative review diff is `task-only.diff` in the runtime work directory;
the original before-task copies remain in `/private/tmp/data-platform-task71-8mo40vcm`.
Only **7.1** is newly checked; **7.2 and later remain unchecked**. No commit was made.

## Task 7.2 shared-image validation

Verified October 2, 2026. Only image packaging, its context checks and documentation
changed. Production Python, model SQL/YAML, `requirements.txt`, `compose.yaml`,
all existing tests and the optimized harness remain byte-for-byte unchanged from
the task baseline. Task-only additions: `.dockerignore`, `docker/Dockerfile`,
`docker/validate_image.py`. Modified documentation: `CURRENT_STATE.md`,
`ARCHITECTURE.md`, `ROADMAP.md`, `LOCAL_DEVELOPMENT.md`, this page and
`pipeline/DBT_TRANSFORMATIONS.md`. Only roadmap item **7.2** is newly checked.

Evidence and before-task copies are in
`/private/tmp/data-platform-task72-0ipfun00` (private directory). `baseline.diff`,
`baseline-status.txt`, `baseline/`, and file-hash manifests preserve the prior
uncommitted work. `task-only.diff` compares against that working-tree baseline,
not HEAD. No commit or index cleanup was performed; the previously reported
26 tracked generated/raw artifacts remain intact.

The official Python tag manifest includes ARM64 and AMD64. Registry inspection:

```bash
export PATH="/opt/homebrew/bin:$PATH"
export DOCKER_CONFIG="$HOME/.config/data-platform/docker"
export DOCKER_HOST="unix://$HOME/.colima/data-platform/docker.sock"
unset DOCKER_CONTEXT
colima start data-platform --activate=false
docker manifest inspect python:3.11.16-slim-bookworm
docker build -f docker/Dockerfile -t data-platform-runtime:task72 .
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python docker/validate_image.py data-platform-runtime:task72
```

The final build succeeds. Base index digest:
`sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b`;
ARM64 manifest: `sha256:bbc491ed39611eede47b1058ad4afb9ea957fb3bf4a7f1b442c6a5628ab93bdc`.
Final runtime image ID:
`sha256:c02c6ae1dc6f9161c998e44556cde467b2a66cba6cfde0352c04e01f15d3dfc0`.
The [official Python Dockerfile](https://github.com/docker-library/python/blob/master/3.11/slim-bookworm/Dockerfile)
uses Debian Bookworm slim. The repository selects the version tag rather than
pinning an immutable digest, consistent with the existing database image policy.
Actual execution was Linux ARM64; AMD64 execution was not tested.

No dependency specification changed and no upgrade command was used. Fresh
installation resolves the existing bounded ranges; `dependencies.log` records
all resolved packages. Verified: Python 3.11.16, dbt Core 1.12.5,
dbt-postgres 1.11.0, Psycopg 3.3.6, pytest 8.4.2, requests 2.34.2 and
python-dotenv 1.2.4. Some patch/transitive versions differ from the older host
venv (for example python-dotenv 1.2.3); the project still has no dependency lock.
No compiler or additional OS package was needed. `pip check` reports no broken
requirements. The installed Docker CLI lacks buildx, so `docker build` used its
working legacy builder and emitted a deprecation notice. No tooling installation
or configuration change was needed; this simple Dockerfile uses no builder-specific
features.

The committed `docker/validate_image.py` suite passes **3 checks**: nested synthetic
exclusion sentinels, the actual repository build context plus byte-for-byte image
source parity/non-root execution, and offline default CLI help. Its scratch probe
images/containers are uniquely named and removed in cleanup. Initial checks exposed
extra placeholder files, then missing nested source files while tightening patterns;
the final `.dockerignore` passes both synthetic and real-context assertions.
The final context contains 94 intended project files. Existing `.env`, Git,
virtual environments, raw archives, private docs, caches and generated dbt files
are excluded before copying, not deleted in a later image layer.

An additional external layer audit passes for **11 layers / 14,633 files**,
including all 94 project files. Every project file matches its source; excluded
project paths are absent, actual IGDB credential values are absent from every
layer and image configuration, and the image sets no source/database credentials.
The audit never prints secret values and removes its temporary image archive.
No build arguments or build secrets were supplied.

These exact offline smoke commands also pass:

```bash
docker run --rm --network none data-platform-runtime:task72 python --version
docker run --rm --network none data-platform-runtime:task72 dbt --version
docker run --rm --network none data-platform-runtime:task72 python -m pip check
docker run --rm --network none data-platform-runtime:task72 dbt parse --no-partial-parse
```

The runtime driver also runs explicit `python -m src.ingestion.run_ingestion
--help`, `dbt --help`, and package metadata checks without network access. The dbt
version command reports installed versions and an expected inability to query
PyPI for the latest release when networking is disabled.

The full validation driver was executed with:

```bash
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task72-0ipfun00/validate_runtime.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task72-0ipfun00/audit_layers.py
```

It creates only network `data-platform-task72-0ipfun00-net` (`--internal`) and a
named disposable `postgres:17.11-bookworm` container, alias `postgres`, with
`--tmpfs /var/lib/postgresql/data:rw`. It creates no persistent volume, exposes
no host port and mounts no host path. Database/user are `task72_validation`;
the random password lives in driver memory and runtime container environment.
It is passed using `-e POSTGRES_PASSWORD`, never a literal command argument or log.
Authenticated connections use explicit `postgres:5432`, database/user, password,
`POSTGRES_RAW_SCHEMA=raw`, and `DBT_SCHEMA=analytics`.

Exact test commands (the driver supplies those exported values):

```bash
docker run --name data-platform-task72-0ipfun00-default --network none \
  -e PYTHONDONTWRITEBYTECODE=1 -e PGCONNECT_TIMEOUT=5 -e RUN_POSTGRES_INTEGRATION=0 \
  data-platform-runtime:task72 python -m pytest -q -p no:cacheprovider \
  --strict-markers --durations=25 --basetemp=/tmp/default

docker run --name data-platform-task72-0ipfun00-narrow --network data-platform-task72-0ipfun00-net \
  -e PYTHONDONTWRITEBYTECODE=1 -e PGCONNECT_TIMEOUT=5 -e RUN_POSTGRES_INTEGRATION=1 \
  -e POSTGRES_HOST -e POSTGRES_PORT -e POSTGRES_DB -e POSTGRES_USER \
  -e POSTGRES_PASSWORD -e POSTGRES_RAW_SCHEMA -e DBT_SCHEMA \
  data-platform-runtime:task72 python -m pytest -q -p no:cacheprovider \
  --strict-markers --durations=25 --basetemp=/tmp/narrow \
  tests/integration/test_dbt_postgres.py::test_release_trends_values_utc_grain_and_reconciliation

docker run --name data-platform-task72-0ipfun00-enabled --network data-platform-task72-0ipfun00-net \
  -e PYTHONDONTWRITEBYTECODE=1 -e PGCONNECT_TIMEOUT=5 -e RUN_POSTGRES_INTEGRATION=1 \
  -e POSTGRES_HOST -e POSTGRES_PORT -e POSTGRES_DB -e POSTGRES_USER \
  -e POSTGRES_PASSWORD -e POSTGRES_RAW_SCHEMA -e DBT_SCHEMA \
  data-platform-runtime:task72 python -m pytest -q -p no:cacheprovider \
  --strict-markers --durations=25 --basetemp=/tmp/enabled
```

Results: default **450 passed / 83 skipped in 1.31s**; narrow **1 passed in 5.98s**;
full enabled **533 passed in 275.40s (4:35)**. All 65 dbt behavior scenarios,
three full-project schema checks and 15 ingestion integration cases remain.
Each schema mode verifies thirteen models, 80 documented columns and all 46 dbt
tests, including fresh/cached parsing. No test contacted IGDB: the default suite
had no network, the enabled suite had only the internal database network, the
existing HTTP rejection fixture remained enabled, and dbt telemetry was disabled.
This is synthetic-fixture integration validation, not task 7.5's live pipeline run.

`docker cp` retained each suite's `/tmp/<suite>` beneath the external evidence
directory before removing its container. `commands.json` records every driver
command without password values. PostgreSQL reports no remaining `test_dp_%`
schemas after the suite. Cleanup removes only the named task containers/internal
network; scratch probes and the superseded first runtime image were removed.
The final shared image and base/build cache remain available. There were no
existing Docker containers or volumes at baseline, and none remain after cleanup;
only Docker's built-in networks remain. No blanket pruning was used.

Shutdown and preservation verification:

```bash
colima stop data-platform
colima list
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/bin/brew services info colima
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h 127.0.0.1 -p 5432
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task72-0ipfun00/check_completion.py
git diff --check
```

Colima is stopped. Both Homebrew services report Running/Loaded/Schedulable false;
native PostgreSQL readiness returns exit 2/no response. All 1,330 external file
hashes match (native cluster, original `~/.docker` files and Git index).
Of 203 baseline repository files, only the six intended documentation files
changed; `.env`, archives, tracked artifacts, production/test code and earlier
uncommitted work are preserved. The three new task files account for all additions.
All dbt artifacts remain outside the repository. Tasks **7.3–7.5 remain unchecked**;
no runtime Compose service, bootstrap, live ingestion, Airflow or Streamlit was added.

## Task 7.3 Compose runtime validation

Verified October 2, 2026. Task-only changes: `compose.yaml`,
`docker/Dockerfile` (initial ownership of `/tmp/dbt`), `.env.example`, new
`docker/validate_compose.py`, and six documentation pages (`CURRENT_STATE.md`,
`ARCHITECTURE.md`, `ROADMAP.md`, `LOCAL_DEVELOPMENT.md`, this page and
`pipeline/DBT_TRANSFORMATIONS.md`). No production Python, dependency, model,
existing test or optimized-harness changes were needed.

The private evidence directory is `/private/tmp/data-platform-task73-37of6xpo`.
It contains before-task copies of 206 repository files, the original Git diff/status,
and 1,330 external file hashes (native PostgreSQL cluster, original `~/.docker`,
and Git index). `task-only.diff` compares against that working tree, including
previously uncommitted content. No `.env` was edited or loaded into validation.
The previously reported tracked generated/raw files remain untouched.

Narrow configuration checks run without an engine, with a sanitized subprocess
environment, an explicit `/dev/null` env file, and synthetic settings only:

```bash
export PATH="/opt/homebrew/bin:$PATH"
export DOCKER_CONFIG="$HOME/.config/data-platform/docker"
export DOCKER_HOST="unix://$HOME/.colima/data-platform/docker.sock"
unset DOCKER_CONTEXT
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python docker/validate_compose.py
```

All **6 checks pass**: default/profile service selection, missing/empty required
settings, loopback host-port overrides versus fixed `postgres:5432`, environment
allowlist and unset values, env-file/shell schema precedence (including empty versus
absent), and PostgreSQL/named-storage contracts. Resolved environments are captured
in memory rather than printed. The first run corrected a test expectation because
Compose represents an inherited command/entrypoint as JSON null.

After starting the existing Colima profile without login registration, actual
validation used these commands:

```bash
colima start data-platform --activate=false
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task73-37of6xpo/validate_runtime.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task73-37of6xpo/audit_image.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task73-37of6xpo/validate_dependency.py
```

The runtime driver selects project `data-platform-task73-37of6xpo`, database/user
`task73_validation`, host port `55473`, and a generated in-memory password. Every
Compose call supplies `--env-file /dev/null`, absolute `-f` files and explicit `-p`.
Only the task override marks the default network `internal: true`; normal Compose
retains networking needed for future deliberate ingestion. A second override
sets runtime `networks: !reset []` and `network_mode: none` for offline checks.
No host paths, repository data, native cluster or existing database are mounted.
The regular project-scoped PostgreSQL volume is disposable in this task project.

For the following command transcript, `dc73` and `offline73` abbreviate these
exact argument prefixes; connection values above are supplied by the driver:

```bash
dc73() { docker compose --env-file /dev/null -p data-platform-task73-37of6xpo \
  -f /Users/patrick/Desktop/Code/data_platform/compose.yaml \
  -f /private/tmp/data-platform-task73-37of6xpo/internal.yaml "$@"; }
offline73() { docker compose --env-file /dev/null -p data-platform-task73-37of6xpo \
  -f /Users/patrick/Desktop/Code/data_platform/compose.yaml \
  -f /private/tmp/data-platform-task73-37of6xpo/internal.yaml \
  -f /private/tmp/data-platform-task73-37of6xpo/offline.yaml "$@"; }
DOCKER_BUILDKIT=0 COMPOSE_BAKE=false dc73 build runtime
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python docker/validate_image.py data-platform-task73-37of6xpo-runtime:latest
offline73 run --no-deps -T --name data-platform-task73-37of6xpo-python-version --rm runtime python --version
offline73 run --no-deps -T --name data-platform-task73-37of6xpo-dbt-version --rm runtime dbt --version
offline73 run --no-deps -T --name data-platform-task73-37of6xpo-pip-check --rm runtime python -m pip check
offline73 run --no-deps -T --name data-platform-task73-37of6xpo-default-help --rm runtime
offline73 run --no-deps -T --name data-platform-task73-37of6xpo-cli-help --rm runtime python -m src.ingestion.run_ingestion --help
offline73 run --no-deps -T --name data-platform-task73-37of6xpo-dbt-help --rm runtime dbt --help
offline73 run --no-deps -T --name data-platform-task73-37of6xpo-default-suite \
  -e RUN_POSTGRES_INTEGRATION runtime python -m pytest -q -p no:cacheprovider \
  --strict-markers --durations=25 --basetemp=/tmp/default
dc73 up -d --wait --wait-timeout 120
dc73 run --no-deps -T --name data-platform-task73-37of6xpo-narrow-suite --rm \
  -e RUN_POSTGRES_INTEGRATION -e POSTGRES_RAW_SCHEMA -e DBT_SCHEMA -e PGCONNECT_TIMEOUT \
  runtime python -m pytest -q -p no:cacheprovider --strict-markers --durations=25 \
  --basetemp=/tmp/narrow tests/integration/test_dbt_postgres.py::test_release_trends_values_utc_grain_and_reconciliation
dc73 run --no-deps -T --name data-platform-task73-37of6xpo-enabled-suite \
  -e RUN_POSTGRES_INTEGRATION -e POSTGRES_RAW_SCHEMA -e DBT_SCHEMA -e PGCONNECT_TIMEOUT \
  runtime python -m pytest -q -p no:cacheprovider --strict-markers --durations=25 \
  --basetemp=/tmp/enabled
```

The driver sets `RUN_POSTGRES_INTEGRATION=0` for default and `1` for narrow/enabled;
these last two also receive explicit `POSTGRES_RAW_SCHEMA=raw`,
`DBT_SCHEMA=analytics`, and `PGCONNECT_TIMEOUT=5`. Python bytecode is disabled by
the image. `commands.json` records all exact argument arrays/return codes without
credential values, including assertions supplied through Python stdin.

The actual Compose build succeeds through the existing legacy builder; no buildx
installation, tooling upgrade or dependency change was needed. Image ID:
`sha256:d3ce29218a40` (short prefix). Python **3.11.16**, dbt Core **1.12.5**,
dbt-postgres **1.11.0**, Psycopg **3.3.6**, and `pip check` pass. Version/help
commands run without networking; dbt's version check cannot query the package
index, as expected. All three existing context/image checks pass. The additional
layer audit checks **11 layers / 14,633 files / 94 project files**, confirms exact
allowlisted project contents, and finds no credential environment settings in the
image. No credentials are supplied as build arguments or copied into image layers.

Four independent offline runtime checks call `dbtRunner().invoke(['parse',
'--no-partial-parse'])` and inspect the manifest: default `raw`, explicit,
legacy-only, and conflicting explicit/legacy source schemas. Python `Settings`
and all five dbt sources agree, while `DBT_SCHEMA` remains independent. All thirteen
models and 80 documented columns remain present. Runtime commands run as UID 10001
in `/app`, without `/app/.env`; missing source credentials fail locally through the
existing auth helper, without invoking ingestion or HTTP.

Ordinary `up` starts exactly `postgres`. Runtime SQL authenticates the intended
database/user on server port 5432. Wrong and empty runtime passwords are rejected.
Missing Compose credentials are rejected before container creation by the narrow
checks; the first driver attempt incorrectly expected an empty Compose password
to reach runtime, then was corrected to test an empty password inside the probe.
That attempt cleaned its project, and its evidence is retained in `first-attempt/`.
The separate `-dependency` project uses host port 55474 and the same built image
with generated credentials: explicit `run --rm runtime python -c ...` starts the
healthy PostgreSQL dependency, authenticates and exits, leaving only PostgreSQL
running until scoped cleanup.

Final results: **450 passed / 83 skipped in 1.33s** by default; **1 passed in
6.18s** for the narrow PostgreSQL regression; **533 passed in 276.61s** with
integration enabled. All 65 dbt behavior scenarios, three full-project schema
checks and 15 ingestion cases remain unchanged. Each full-project mode retains
thirteen models, 80 documented columns and **46 passing dbt tests**.

No validation contacted IGDB: offline commands/default tests used `network_mode:
none`; database tests used only the internal Docker network with unchanged HTTP
rejection fixtures and disabled dbt telemetry. A TCP attempt to the documentation
address `192.0.2.1:443` failed from that network; no source endpoint was probed.
This exercises synthetic fixtures, not task 7.5's live clean-volume pipeline.

The driver writes synthetic markers into both runtime volumes as UID 10001,
removes containers/network with `down`, then creates a fresh runtime that reads
and rewrites both markers. Offline dbt manifest/log files also survive. `docker cp`
exports both volumes to the external evidence directory; copied marker content is
verified. No actual archives are loaded. Pytest directories are copied from stopped
containers before removal; all generated dbt artifacts remain outside the repository.

Authenticated SQL confirms no `test_dp_%` schemas remain after the enabled suite.
Only the two task-owned projects' containers/networks/volumes are removed, plus
the uniquely named context probes and the task-built runtime image. The earlier
`data-platform-runtime:task72` image is retained. There is no blanket cleanup.
Compose warnings about orphaned stopped test containers refer to the task's
retained artifact containers; each is explicitly removed after export. Final
inventory has no containers/volumes and only the original built-in networks.

Final commands:

```bash
docker image rm data-platform-task73-37of6xpo-runtime:latest
colima stop data-platform
colima list
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/bin/brew services info colima
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h 127.0.0.1 -p 5432
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task73-37of6xpo/check_completion.py
git diff --check
```

Colima is stopped; native PostgreSQL and both Homebrew services remain
stopped/unregistered. The native readiness check returns exit 2/no response.
All 1,330 external hashes match. Of 206 baseline repository files, 197 are unchanged;
only the nine intended files changed, and `docker/validate_compose.py` is the only
addition. `.env`, archives, tracked artifacts, private files, requirements,
production/test code, native data and previous work are preserved; the Git index
is unchanged and nothing was committed. Only **7.3** is newly checked; **7.4–7.5
and later remain unchecked**.

Remaining limits: Compose needs explicit database settings even for offline help;
Docker administrators can inspect runtime environment credentials; existing volumes
with incompatible ownership are not repaired automatically; concurrent direct dbt
commands need separate artifact paths. Dependency ranges remain unlocked. No
bootstrap automation, live ingestion, migration or clean-volume pipeline exercise
was added.

## Task 7.4 startup documentation verification

Verified October 2, 2026. Documentation only: `README.md`, `CURRENT_STATE.md`,
`ROADMAP.md`, `engineering/LOCAL_DEVELOPMENT.md`, this page and
`pipeline/DBT_TRANSFORMATIONS.md`. The canonical
[first-use/session workflow](LOCAL_DEVELOPMENT.md#compose-first-use-and-subsequent-sessions-task-74)
reuses the existing image, schema, storage/export and Colima references. Redundant
operation command blocks and stale README startup claims were consolidated; prior
validation history remains intact. No production/configuration/test files changed.

Evidence is saved outside the repository in
`/private/tmp/data-platform-task74.6w6JB2`: working-tree copies, initial status/diff,
repository/external fingerprints, help logs, `commands.json`, dbt/pytest output,
review helpers and `task-only.diff`. The diff compares against the initial working
tree, preserving the existing uncommitted 7.1–7.3 work.

Executed configuration check (no running engine needed):

```bash
env -i HOME="$HOME" PATH="/opt/homebrew/bin:/usr/bin:/bin" \
  DOCKER_CONFIG="$HOME/.config/data-platform/docker" PYTHONDONTWRITEBYTECODE=1 \
  /private/tmp/data-platform-phase1-venv/bin/python docker/validate_compose.py
```

**6 checks passed.** The existing checker supplies synthetic settings and
`--env-file /dev/null`; its env-file precedence case uses only a temporary synthetic
file. Resolved configurations are captured privately and never printed.

Executed the temporary validation driver:

```bash
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task74.6w6JB2/verify_commands.py
```

It uses an explicit subprocess environment: no inherited project/source credentials,
`PYTHONDONTWRITEBYTECODE=1`, `PYTHON_DOTENV_DISABLED=1`, disabled dbt telemetry,
`RUN_POSTGRES_INTEGRATION=0`, synthetic database/user/password `task74_synthetic`,
host `127.0.0.1`, port `55474`, raw schema `raw` and output schema `analytics`.
The installed dotenv implementation was checked to honor the disable flag.
Repository credentials were not loaded. Every Compose invocation uses this prefix:

```bash
docker compose --env-file /dev/null -p data-platform-task74-check \
  -f /Users/patrick/Desktop/Code/data_platform/compose.yaml
```

The exact argument arrays and return codes are in `commands.json`. All exited 0:

- Ingestion `--help` through the required host interpreter; confirmed entity and
  bounded batch options against the implemented CLI.
- Compose `build/up/run/config/ps/logs/stop/down --help`; confirmed `--wait`,
  `--wait-timeout`, `--rm`, `--no-deps`, `--name` and `--quiet`.
- Docker `cp/rm/version --help`, Colima `start/stop --help` (including `--activate`),
  and host dbt `parse/debug/build --help`.
- Compose `config --quiet` and `config --services`; ordinary service selection
  returns exactly `postgres`.

The driver executed these dbt/test commands with that sanitized environment:

```bash
/private/tmp/data-platform-phase1-venv/bin/dbt parse --no-partial-parse \
  --project-dir /private/tmp/data-platform-task74.6w6JB2/dbt-project \
  --profiles-dir /private/tmp/data-platform-task74.6w6JB2/dbt-project
/private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_config.py tests/test_run_ingestion.py tests/test_dbt_sources.py \
  --basetemp=/private/tmp/data-platform-task74.6w6JB2/pytest-narrow
/private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider \
  --basetemp=/private/tmp/data-platform-task74.6w6JB2/pytest-default
```

Parsing used an external copy of the dbt definitions, with `DBT_TARGET_PATH` and
`DBT_LOG_PATH` set to `dbt-target`/`dbt-logs` in the evidence directory. It discovered
**13 models, five raw sources and 46 tests**, with independent output schema
`analytics`. No database connection was made and no dbt tests were executed.
Focused Python tests: **55 passed in 0.38s**; full default suite: **450 passed,
83 skipped in 1.77s**. The 533 enabled cases and three full-project schema-mode
builds remain task 7.3 evidence; they were not rerun for this documentation task.

Documentation/preservation checks and service inspection:

```bash
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task74.6w6JB2/review_docs.py
git diff --check
env -i HOME="$HOME" PATH="/opt/homebrew/bin:/usr/bin:/bin" \
  DOCKER_CONFIG="$HOME/.config/data-platform/docker" /opt/homebrew/bin/colima list
/opt/homebrew/bin/brew services info postgresql@17
/opt/homebrew/bin/brew services info colima
```

The review checks relative links/anchors, `bash -n` for README/Local Development
Bash blocks, whitespace, the single 7.4 checkbox transition, and file fingerprints.
Only the six intended documentation files differ; all other repository files and
1,331 external/index fingerprints match (native PostgreSQL data, original and
project Docker client configurations, Git index). The previously reported 26 tracked
artifacts remain untouched. No files were deleted/untracked and nothing was committed.
Colima reports `Stopped`; both Homebrew services report Running/Loaded/Schedulable
false. Neither service was started, so existing Docker resources were not changed.

**Documented but not executed:** image build, Compose startup/readiness, authenticated
`dbt debug`, live ingestion, `dbt build`, artifact export and shutdown/restart.
These operation forms were checked against configuration/help and prior 7.1–7.3
verification. Task 7.4 introduces no bootstrap automation or live validation claim.
Only **7.4** is newly complete; **7.5 and all later tasks remain unchecked**.

## Task 7.5 clean-volume live workflow verification

Verified October 2, 2026. This is new live clean-volume evidence, separate from
7.4's documentation-only checks and 7.3's synthetic runtime checks. No production,
Compose, Dockerfile, test or dependency changes were necessary. The only workflow
fix changes the Compose authentication probe to `dbt debug --connection`: plain
`dbt debug` successfully authenticated but exited 1 because its dependency check
requires Git, absent from the slim image. The connection-only command exited 0.
The first attempt's logs and dbt artifacts are retained under `first-attempt/`;
no ingestion occurred in that attempt, and its volumes were removed before retry.

Evidence directory: `/private/tmp/data-platform-task75-20261002-a7c9`.
It contains initial working-tree copies/diff/status, repository and external/index
fingerprints, `commands.json` (exact argument arrays, return codes and durations),
`host-commands.json`, redacted logs, verification helpers, full database snapshots,
`database.sql`, `exported-archives/`, `exported-dbt/`, integration artifacts,
`reconciliation.json`, `schema-modes.json`, `runtime-complete.json` and
`task-only.diff`. Evidence is external and temporary; retain it elsewhere if needed
beyond `/private/tmp`'s lifetime. Source credentials/passwords are not recorded.

Isolation: project `data-platform-task75-20261002-a7c9`, unused loopback port
`55475`, database/user `task75_validation`, generated in-memory password, source
schema `raw`, output schema `analytics`. Initial Docker inventories contained no
project resources; all three named volumes were new. The driver uses an explicit
subprocess environment and reads only the two source credential values from `.env`
into the environment of each live CLI process. It neither sources `.env` wholesale
nor uses its database settings. Every Compose invocation uses `--env-file /dev/null`.
Colima has no host directory mounts; no repository/native data is mounted or copied
into the image. The existing toolchain/configuration is reused without upgrades.

Exact host and driver entry commands, from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task75-20261002-a7c9/host_checks.py
env -i HOME="$HOME" PATH="/opt/homebrew/bin:/usr/bin:/bin" \
  DOCKER_CONFIG="$HOME/.config/data-platform/docker" \
  DOCKER_HOST="unix://$HOME/.colima/data-platform/docker.sock" \
  colima start data-platform --activate=false
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task75-20261002-a7c9/validate_live.py
```

The host driver disables dotenv loading, bytecode writes and dbt telemetry, opts
out of database tests and supplies no source credentials. It runs five existing
Compose checks. The sixth existing check, which intentionally selects a temporary
synthetic env file, was omitted to honor this task's `/dev/null` constraint; its
prior task-7.4 result is not claimed as a new check. No schema-resolution behavior
changed; the enabled suite freshly verifies all three full-project schema modes.
The narrow/default host commands are:

```bash
/private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_config.py tests/test_run_ingestion.py tests/test_dbt_sources.py \
  --basetemp=/private/tmp/data-platform-task75-20261002-a7c9/host-narrow
/private/tmp/data-platform-phase1-venv/bin/python -m pytest -q -p no:cacheprovider \
  --basetemp=/private/tmp/data-platform-task75-20261002-a7c9/host-default
```

Initial results: **55 passed in 0.48s**, then **450 passed / 83 skipped in 1.82s**.
The same narrow/default checks were repeated after documentation edits; final
results are recorded below. No new unit tests were added for the documentation fix;
the actual corrected runtime command was exercised against the new database.

`dc75` below abbreviates the driver's exact Compose prefix, with the explicit
private environment described above. Do not substitute an existing project for
this disposable validation:

```bash
dc75() { docker compose --env-file /dev/null -p data-platform-task75-20261002-a7c9 \
  -f /Users/patrick/Desktop/Code/data_platform/compose.yaml "$@"; }
DOCKER_BUILDKIT=0 COMPOSE_BAKE=false dc75 build runtime
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python \
  docker/validate_image.py data-platform-task75-20261002-a7c9-runtime:latest
dc75 up -d --wait --wait-timeout 120
dc75 ps --services --status running
dc75 run -T --name data-platform-task75-20261002-a7c9-dbt-debug --rm runtime dbt debug --connection
# Executed once with each name, using source credentials only for these commands:
for iteration in 1 2; do
  dc75 run -T --name "data-platform-task75-20261002-a7c9-live-$iteration" --rm \
    runtime python -m src.ingestion.run_ingestion --entity all --batch-size 5 --max-batches 1
done
dc75 run -T --name data-platform-task75-20261002-a7c9-live-dbt-build --rm runtime dbt build
```

The current image built through the legacy builder without installing buildx.
All three existing image/context checks passed, including packaged source parity,
non-root execution and private/generated-file exclusions. `pip check`, actual CLI
help and `dbt parse --no-partial-parse` passed in runtime containers with an external
`offline.yaml` override setting `network_mode: none`; parse found 13 models, five
sources and 46 tests. The image uses Python 3.11.16, dbt Core 1.12.5 and adapter
1.11.0. Normal `up` selected only PostgreSQL. Initialization logs show the fresh
cluster/database creation; health reports `healthy` and only `127.0.0.1:55475` is
published. Runtime SQL authenticated `task75_validation` on `postgres:5432` as
UID 10001. Before ingestion, there were **zero application tables/views** and no
JSONL archives. Python and dbt subsequently created their own relations.

| Entity | IDs observed in both requests | Raw rows after each run | Archives / successful run records after repeat |
|---|---|---|---|
| games | 1, 2, 3, 4, 5 | 5 / 5 | 2 / 2 |
| genres | 2, 4, 5, 7, 8 | 5 / 5 | 2 / 2 |
| platforms | 3, 4, 5, 6, 7 | 5 / 5 | 2 / 2 |
| companies | 1, 2, 3, 4, 5 | 5 / 5 | 2 / 2 |
| involved_companies | 2, 6, 7, 8, 9 | 5 / 5 | 2 / 2 |

Each invocation returned five fetched/loaded records per entity: 25 processed
records per command, 50 across both, and 25 distinct stored raw records. All ten
metadata records are `succeeded`, have matching 5/5 counts, valid completion
timestamps, NULL errors and **NULL watermark starts and ends**. Every JSONL object
matches the corresponding stored payload; extracted name/slug fields match too.
All 25 overlapping IDs refreshed `fetched_at`, no duplicates appeared, and prior
run records/archives were retained. The verifier folds both archives by ID in
request order, compares the union to stored rows and checks the latest payload,
so changed source responses would be accounted for. This time there were zero
changed IDs/payloads. Archives retain both observations; raw tables retain one
latest-upsert version, not source history.

`dbt build` exited 0: **13 models succeeded, 46 tests passed; zero warnings,
errors or skips** (59 total nodes). The relation inventory is eight views and
five tables. All staging fields were queried and compared to raw payloads and
fetch times; existing independent Python reconciliation helpers then compared
all catalog scalars/arrays, raw-derived bridge pairs and all five marts:

| Models | Verified row counts |
|---|---|
| Five `stg_*` views | 5 each |
| `int_game_genres`, `int_game_platforms`, `int_game_companies` | 11, 14, 5 |
| `mart_game_catalog`, `mart_release_trends` | 5, 4 |
| `mart_genre_performance`, `mart_platform_performance`, `mart_company_output` | 4, 9, 5 |

Representative queried output: game 1 is *Thief II: The Metal Age*, released
2000-03-21 UTC, with observed genre IDs 5/13/31 and platform 6. Genre IDs 13/31
have NULL labels because those dimensions were not loaded. Release counts are
1998: 2 and 2000/2004/2014: 1 each; their sum is five, with zero undated games.
Genre/platform game-count sums are 11/14, matching distinct raw-array pairs.
Company IDs 1/3/4/7/11 each contribute one relationship record and game reference;
7/11 are unloaded companies, and three records reference unloaded games.
The complete queried values, including metrics and nullable roles, are exported.
These are observations from this new bounded load, even where they match earlier
native-data samples.

Persistence used `dc75 down` followed by
`dc75 up -d --wait --wait-timeout 120 postgres`. The PostgreSQL container ID changed;
all raw rows, ten run records and thirteen model outputs matched exactly, as did
all archive/dbt file hashes. Fresh runtime containers could read the volumes as
UID 10001. Reconciliation passed again without ingestion or dbt rebuild.

Before cleanup, the following command exported database SQL without role passwords:

```bash
dc75 exec -T postgres pg_dump -U task75_validation -d task75_validation --no-owner --no-privileges
``` A stopped task-owned `evidence-export` runtime container exposed both
volumes to `docker cp`: `/app/data/raw/.` → `exported-archives/`, `/tmp/dbt/.` →
`exported-dbt/`. Every copied file matched its recorded hash; there are ten JSONL
files and retained dbt manifest/run-results/logs. The SQL dump was exported but
not restore-tested. Exact export/probe commands and stdin helpers are retained.

Then, with `RUN_POSTGRES_INTEGRATION=1` supplied by name, the driver ran narrow
synthetic ingestion tests before the full applicable suite:

```bash
dc75 run -T --name data-platform-task75-20261002-a7c9-narrow-integration \
  -e RUN_POSTGRES_INTEGRATION runtime python -m pytest -q -p no:cacheprovider \
  --strict-markers --durations=25 --basetemp=/tmp/narrow-integration \
  tests/integration/test_ingestion_postgres.py
dc75 run -T --name data-platform-task75-20261002-a7c9-full-enabled \
  -e RUN_POSTGRES_INTEGRATION runtime python -m pytest -q -p no:cacheprovider \
  --strict-markers --durations=25 --basetemp=/tmp/full-enabled
```

Results: **15 passed in 0.99s**; **533 passed in 273.11s (0:04:33)**. The 65 dbt behavior scenarios,
three full-project schema checks and 15 ingestion scenarios remain intact. Each
schema mode freshly retained thirteen models and 46 passing tests. Integration
fixtures used unique synthetic schemas and blocked HTTP requests; source credentials
were absent. All disposable schemas were gone afterward, and another snapshot
proved live raw/history/model data and volume files unchanged by the test suite.
Test artifacts were copied from stopped containers before their removal.

Final task cleanup used `dc75 --profile tools down --volumes`, then
`docker image rm data-platform-task75-20261002-a7c9-runtime:latest`. Enabling the
profile is necessary to include both runtime volumes: initial first-attempt
`down --volumes` without it left those volumes; the preflight detected this and
only those exact task-owned volumes were then removed before retry. No blanket
cleanup occurred. Final container/volume/network/image inventories exactly match
the original inventory, including the retained task-7.2 image. Build-cache layers
may remain; no cache pruning was performed.

Colima was stopped with `colima stop data-platform`. `colima list` reports Stopped;
`brew services info postgresql@17` and `brew services info colima` report
Running/Loaded/Schedulable false; native `pg_isready -h 127.0.0.1 -p 5432` reports
no response (expected exit 2). No native PostgreSQL startup or login registration
occurred. Preservation/review commands:

```bash
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task75-20261002-a7c9/host_checks.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python /private/tmp/data-platform-task75-20261002-a7c9/review_docs.py
git diff --check
```

Final host results: **55 passed in 0.46s**, then **450 passed / 83 skipped in
1.82s**. All **210 relative links/anchors and 24 Bash blocks** pass review.
Source credentials are absent from all 3,152 scanned evidence files; values were
compared privately and never printed. Documentation links/anchors, Bash syntax,
roadmap scope and whitespace checks pass. Only seven existing documentation files
differ from the saved working tree; all other 12,854 repository files and all
1,331 external/index fingerprints match, including `.env`, prior edits, archives,
tracked generated artifacts, private files, native cluster data and both Docker
client configurations. The previously reported 26 tracked artifacts were preserved.
No files were added/deleted/untracked and the Git index is unchanged.

Only **7.5** is newly checked. **Phase 7 is complete:** the documented Docker
workflow created a database and ran the core pipeline from new volumes. Phase 8
and later stay unchecked. This verifies bounded startup on this existing Mac/
Colima toolchain, not task 10.7's clean-clone/new-machine reproducibility, full
source/reference coverage, uncapped incremental bootstrap/checkpoint publication,
or source snapshot isolation. Dependency ranges/base tags remain mutable. No
startup automation, migration, watermark reset, data deletion from existing
installations, repository artifact removal or commit was introduced.
