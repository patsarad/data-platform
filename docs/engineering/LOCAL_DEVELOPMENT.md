# Local Development

## Current prerequisites

Before Docker is implemented, the current project expects:

- Python 3.11 (verified baseline; newer versions have not been validated)
- package-index access for dependency installation
- a reachable PostgreSQL instance and IGDB/Twitch application credentials **only for live ingestion**

Unit tests and `dbt parse` require no external services or credentials.

## Environment variables

Use `.env.example` as the template. Required source credentials:

```text
igdb_client_id
igdb_client_secret
```

PostgreSQL settings:

```text
POSTGRES_HOST
POSTGRES_PORT
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_SCHEMA
```

Logging:

```text
LOG_LEVEL
```

Copy `.env.example` to `.env` only if `.env` does not already exist, then edit it for your environment. Never commit `.env`. Python loads it from the repository root without overriding already exported variables. dbt reads exported environment variables and does not load `.env` itself.

## Local PostgreSQL on Apple Silicon

Verified September 26, 2026 with native Homebrew PostgreSQL 17.11. Use the ARM Homebrew installation at `/opt/homebrew`; the older Intel/Rosetta installation at `/usr/local` failed while building OpenSSL with an unsupported `westmere` compiler option on this machine.

With native Homebrew installed, the one-time install and repeatable startup/readiness commands are:

```bash
/opt/homebrew/bin/brew install postgresql@17
/opt/homebrew/bin/brew services run postgresql@17
/opt/homebrew/opt/postgresql@17/bin/pg_isready -h localhost -p 5432
```

Use `services run` to start PostgreSQL for project work without registering it to start at login. It remains running after closing a terminal/editor, so stop it explicitly when finished:

```bash
/opt/homebrew/bin/brew services stop postgresql@17
```

`services stop` stops the server and unregisters any login startup. Avoid `services start` or `services restart` for this workflow because those register automatic startup. Check state with:

```bash
/opt/homebrew/bin/brew services info postgresql@17
```

When finished, expect `Running: false`, `Loaded: false`, and `Schedulable: false`; `pg_isready` should report `no response`. The service was left in that stopped/unregistered state after verification on September 26, 2026. These commands follow the [Homebrew service documentation](https://docs.brew.sh/Manpage#services-subcommand).

Stopping PostgreSQL preserves databases, tables, rows, indexes, and roles in `/opt/homebrew/var/postgresql@17`. Starting it again opens the existing data; there is no need to recreate tables, restore JSONL, or call IGDB each session. A manual restart check retained all five genres and two ingestion-run records. At that check, the project database occupied 7798 kB (about 7.6 MB) and the full cluster directory occupied about 47 MB, excluding installed software. Stopped PostgreSQL consumes disk space for those files but has no running database processes consuming CPU or process memory. Compression/restoration between sessions is unnecessary at this size. Normal unit tests do not need the service running.

Readiness should report `accepting connections`; this alone does not validate a project login or database. On this machine, the fresh cluster initially contained the macOS user's administrative role, but lacked the configured `postgres` login and `gaming_analytics` database. They were created using the existing environment-backed settings: the project role can log in and owns its database, but is not a superuser and cannot create other databases or roles. Its password was supplied from settings as a SCRAM verifier without printing it. No `.env` changes were needed. Existing roles/databases were not replaced.

Check the actual project connection from the repository root with the Python environment activated:

```bash
PYTHONDONTWRITEBYTECODE=1 python - <<'PY'
from src.storage.raw_games import create_connection
with create_connection() as connection:
    print(connection.execute("SELECT current_database(), current_user").fetchone())
PY
```

The verified result was `('gaming_analytics', 'postgres')`. The pipeline creates its configured schema and tables. Two bounded genres smoke runs then passed; see [Testing](TESTING.md#task-31-live-smoke-completion). Task 3.2 also passed two bounded platforms runs using this existing cluster, then stopped/unregistered PostgreSQL; see [platforms verification](TESTING.md#task-32-verification). Task 3.3 passed two bounded companies runs against the existing database and left PostgreSQL stopped/unregistered; see [companies verification](TESTING.md#task-33-verification). Task 3.4 passed two bounded involved-companies runs and again left PostgreSQL stopped/unregistered; see [relationship verification](TESTING.md#task-34-verification). Task 3.5 passed two bounded games runs exercising genre/platform/involved-company references and again left PostgreSQL stopped/unregistered; see [games verification](TESTING.md#task-35-verification). Task 3.6 passed two actual all-entity CLI runs and left PostgreSQL stopped/unregistered; see [CLI verification](TESTING.md#task-36-verification). Wait for `pg_isready` to report accepting connections after startup before connecting. These instructions establish the current local service, not the future Docker milestone.

## Python setup

From the repository root on macOS/Linux:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python --version
python -m pip install -r requirements.txt
python -m pip check
```

Confirm `python --version` reports 3.11 before installing. A system `python3` or an old `.venv` may point to an older interpreter. For a fresh setup alongside an existing environment, use the also-ignored `venv/` directory if unused and activate that environment instead; do not delete an environment you still need.

On Windows PowerShell, create the environment with `py -3.11 -m venv .venv` and activate it with `.venv\Scripts\Activate.ps1`, then use the same `python -m ...` commands. The verified platform is macOS with Python 3.11.0; Windows has not been exercised.

`requirements.txt` contains the current runtime and test dependencies: requests, python-dotenv, psycopg (binary), dbt-postgres, and pytest. Airflow and Streamlit remain future milestones. Dependency ranges are bounded but not locked; installation does not guarantee identical transitive versions on every date. No dependency changes were needed for the Phase 1 validation.

## Tests

```bash
python -m pytest -q
```

Use `python -m pytest` from the repository root so the active interpreter can import `src` without installing the project or setting `PYTHONPATH`. Tests use fake HTTP sessions and database connections; live integration tests are a future milestone.

## Current ingestion smoke run

Inspect the command without calling IGDB or PostgreSQL:

```bash
python -m src.ingestion.run_ingestion --help
```

With PostgreSQL running, the target database already created, and `.env` configured:

```bash
python -m src.ingestion.run_ingestion --max-batches 1
python -m src.ingestion.run_ingestion --entity genres --batch-size 5 --max-batches 1
python -m src.ingestion.run_ingestion --entity all --batch-size 5 --max-batches 1
```

The first command requests at most 500 games and validates authentication, API access, JSONL output, and PostgreSQL loading. The configured database user must be able to create the schema/table and insert/update rows. The output is `data/raw/raw_games_<timestamp>.jsonl` and `<POSTGRES_SCHEMA>.raw_games`, using `analytics` as the default schema. Reruns upsert matching IGDB IDs. The all-entity command requests at most five records per entity, sequentially in games → genres → platforms → companies → involved_companies order, with separate archives and run metadata. Fetch limits apply per entity. Failure stops later entities; earlier completed loads remain committed. `--output-path` is allowed for a single entity and rejected with `all`. Repeat the bounded all-entity command to check upserts, then stop PostgreSQL and verify its service flags are all false. Task 3.6 executed that CLI twice successfully; [Testing](TESTING.md#task-36-verification) records exact validation and cleanup commands.

Since task 4.5, these bounded smoke commands still load data but always leave `source_watermark_end` NULL. Normal uncapped CLI runs use per-entity persisted cutoffs for games/companies/involved companies: the first eligible run reads the whole endpoint, then later runs use a frozen overlap window. Genres/platforms always read unfiltered. This runtime checkpoint behavior has offline tests only; no live PostgreSQL or IGDB validation was performed for task 4.5. See the [watermark policy](../pipeline/WATERMARKS.md).

## dbt

The project and profile are both in `dbt/`. Validate the scaffold without connecting to PostgreSQL:

```bash
dbt parse --project-dir dbt --profiles-dir dbt
```

Warnings about unused staging/intermediate/marts configuration are expected because no models exist. Generated targets/logs are local artifacts.

To validate database connectivity, export the `POSTGRES_*` values to your shell first. For a trusted, shell-compatible `.env` on macOS/Linux (quote values containing spaces or shell metacharacters):

```bash
set -a
. ./.env
set +a
dbt debug --project-dir dbt --profiles-dir dbt
```

This shell step assigns the values from `.env`, including any already exported values. In PowerShell, set the corresponding `$env:POSTGRES_*` variables before running `dbt debug`. Connection checks require a reachable PostgreSQL database; they were not run during Phase 1.

Once models exist, the build command will be `dbt build --project-dir dbt --profiles-dir dbt`. Until then it does not validate the intended analytics pipeline.

## Target Docker workflow

After the Docker milestone, this page should be updated so Docker Compose becomes the preferred onboarding path. Manual Python/PostgreSQL setup can remain as a debugging/development alternative.
