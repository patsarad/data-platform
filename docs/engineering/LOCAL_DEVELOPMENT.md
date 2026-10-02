# Local Development

## Current prerequisites

The current host-based Python/dbt workflow expects:

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
POSTGRES_RAW_SCHEMA
DBT_SCHEMA
```

Logging:

```text
LOG_LEVEL
```

Copy `.env.example` to `.env` only if `.env` does not already exist, then edit it for your environment. Never commit `.env`. Python loads it from the repository root without overriding already exported variables. dbt reads exported environment variables and does not load `.env` itself.

### Schema names and existing `analytics` installations

New installations use `POSTGRES_RAW_SCHEMA=raw` for all five Python-owned raw tables and `ingestion_runs`, and `DBT_SCHEMA=analytics` for dbt-managed outputs. These are independent settings. Python and dbt both accept the older `POSTGRES_SCHEMA` as a fallback only when `POSTGRES_RAW_SCHEMA` is unset; if neither exists, both use `raw`. `DBT_SCHEMA` controls output independently and never selects raw sources. An existing `.env` with `POSTGRES_SCHEMA=analytics` therefore keeps Python pointed at its existing raw tables and ingestion history unless the new variable is explicitly set. Exported variables still take precedence over `.env` for Python; dbt requires export.

Changing a variable or default does **not** move data or preserve a watermark in a different schema. Before the next ingestion run on an installation with raw tables in `analytics`, either keep `POSTGRES_SCHEMA=analytics` (or explicitly set `POSTGRES_RAW_SCHEMA=analytics`) to continue using those tables and history, or perform a deliberate transition: stop ingestion, back up the database, create/authorize `raw`, move all five `raw_<entity>` tables **and** `ingestion_runs` with their rows and constraints to `raw`, verify table counts and per-entity successful watermark ends, then set `POSTGRES_RAW_SCHEMA=raw` and remove the old setting. Do not run an uncapped incremental command against an empty `raw.ingestion_runs` expecting it to resume from `analytics.ingestion_runs`; it will bootstrap. Export the same source-schema settings for dbt that Python loads from `.env`; legacy `POSTGRES_SCHEMA=analytics` now works for both. An explicit `POSTGRES_RAW_SCHEMA` wins for both consumers. Source declarations do not move data.

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

Use `python -m pytest` from the repository root so the active interpreter can import `src` without installing the project or setting `PYTHONPATH`. The default run uses fake HTTP sessions and database connections and skips database integration checks. With PostgreSQL running and configured through `.env` or exported settings, run `RUN_POSTGRES_INTEGRATION=1 python -m pytest -q tests/integration`. These checks use disposable schemas, clean up after failures, and never call IGDB. See [integration requirements and coverage](TESTING.md#postgresql-integration-tests).

For focused dbt development, select the affected behavior family, for example:

```bash
RUN_POSTGRES_INTEGRATION=1 python -m pytest -q tests/integration/test_dbt_postgres.py -k company_output --durations=10
RUN_POSTGRES_INTEGRATION=1 python -m pytest -q tests/integration/test_dbt_postgres.py -k full_project_schema_modes
```

The optimized harness retains all 64 original data-behavior scenarios, adds one
task 6.8 catalog-container scenario, and keeps three full-project schema checks. Each scenario has fresh disposable schemas; setup builds staging
and only its explicitly requested model dependencies. Repeated commands reuse
parsing only within that scenario. The full schema checks force fresh parsing
and verify all models/tests under explicit, legacy, and precedence settings.
Run the full applicable suite before completion, as required by AGENTS.md.
`--durations=25` reports slow setup/call phases, and `dbt-invocations.jsonl` in each
pytest temporary directory records individual dbt command times. Artifacts stay
outside the repository. See [coverage and timing evidence](TESTING.md#test-harness-optimization-verification).

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

The first command requests at most 500 games and validates authentication, API access, JSONL output, and PostgreSQL loading. The configured database user must be able to create the schema/table and insert/update rows. The output is `data/raw/raw_games_<timestamp>.jsonl` and `<POSTGRES_RAW_SCHEMA>.raw_games`, using `raw` as the default schema. Reruns upsert matching IGDB IDs. The all-entity command requests at most five records per entity, sequentially in games → genres → platforms → companies → involved_companies order, with separate archives and run metadata. Fetch limits apply per entity. Failure stops later entities; earlier completed loads remain committed. `--output-path` is allowed for a single entity and rejected with `all`. Repeat the bounded all-entity command to check upserts, then stop PostgreSQL and verify its service flags are all false. Task 3.6 executed that CLI twice successfully; [Testing](TESTING.md#task-36-verification) records exact validation and cleanup commands.

Since task 4.5, these bounded smoke commands still load data but always leave `source_watermark_end` NULL. Normal uncapped CLI runs use per-entity persisted cutoffs for games/companies/involved companies: the first eligible run reads the whole endpoint, then later runs use a frozen overlap window. Genres/platforms always read unfiltered. Checkpoint behavior now also has repeatable real-PostgreSQL integration coverage with controlled source responses. The September 29 reassessment separately verified bounded live normal/refresh runs and backfill filters; uncapped live bootstrap remains unverified. See the [watermark policy](../pipeline/WATERMARKS.md).

## dbt

The project and profile are both in `dbt/`. Parse the five source declarations and the `stg_games` / `stg_genres` / `stg_platforms` / `stg_companies` / `stg_involved_companies` / `int_game_genres` / `int_game_platforms` / `int_game_companies` / `mart_game_catalog` / `mart_release_trends` / `mart_genre_performance` / `mart_platform_performance` / `mart_company_output` models, then list them without connecting to PostgreSQL:

```bash
dbt parse --project-dir dbt --profiles-dir dbt
dbt ls --project-dir dbt --profiles-dir dbt --resource-type source
dbt ls --project-dir dbt --profiles-dir dbt --resource-type model
```

Task 6.4 uses the marts configuration, so the unused marts warning no longer applies. The model listing contains `stg_games`, `stg_genres`, `stg_platforms`, `stg_companies`, `stg_involved_companies`, `int_game_genres`, `int_game_platforms`, `int_game_companies`, `mart_game_catalog`, `mart_release_trends`, `mart_genre_performance`, `mart_platform_performance`, and `mart_company_output`. Source and staging primary keys have declared tests, but parsing and listing do not execute them or build the relations. Generated targets/logs are local artifacts. To keep them outside this repository, pass `--target-path /private/tmp/dbt-target --log-path /private/tmp/dbt-logs` to each dbt command.

To validate database connectivity, export the `POSTGRES_*` values to your shell first. For a trusted, shell-compatible `.env` on macOS/Linux (quote values containing spaces or shell metacharacters):

```bash
set -a
. ./.env
set +a
dbt debug --project-dir dbt --profiles-dir dbt
```

This shell step assigns the values from `.env`, including any already exported values. In PowerShell, set the corresponding `$env:POSTGRES_*` variables before running `dbt debug`. Connection checks require a reachable PostgreSQL database; they were not run during Phase 1.

Run `dbt build --project-dir dbt --profiles-dir dbt` after exporting the settings above. It has passed on the existing local configuration, creating `analytics.stg_games`, `analytics.stg_genres`, `analytics.stg_platforms`, `analytics.stg_companies`, and `analytics.stg_involved_companies` over their legacy `analytics` raw sources and passing all ten source tests and ten staging identifier tests. The five existing rows for each of games, genres, platforms, companies, and involved companies were also queried and compared with raw records, including timestamps and fetch times. A view build alone does not evaluate row values; use the integration checks for that contract. Task 5.8 required no new ingestion, schema migration, or `.env` change; PostgreSQL was restored to stopped/unregistered afterward. All five staging models exist; tasks 6.1–6.3 add the relationship views described below. Task 6.4 adds the catalog table described below. Strict relationship tests remain deferred for incomplete bounded samples. See [task 5.8 verification](TESTING.md#task-58-dbt-tests-verification) for deliberate failing-data tests, exact commands, preservation checks, and cleanup.

Task 5.9 additionally documents all five views and 35 columns in `dbt/models/staging/schema.yml`. The verified build retains those descriptions in the manifest; coverage compares documentation with SQL projections and actual database columns. The existing-data build and full suites passed again with no ingestion or settings changes, and PostgreSQL was restored to stopped/unregistered. See [task 5.9 commands and results](TESTING.md#task-59-model-documentation-and-build-verification). Keep using external target/log paths for local validation.

Task 6.1 adds `int_game_genres` to the same build, for six views and 23 dbt tests. It expands existing staged genre arrays into distinct game/genre pairs, preserving references missing from the bounded genre sample. No ingestion or schema migration is needed when stored game arrays already exist. Continue to use external dbt artifact paths and stop/unregister PostgreSQL after validation. See [task 6.1 commands and results](TESTING.md#task-61-game-genre-relationship-verification).

Task 6.2 adds `int_game_platforms`, bringing the build to seven views and 26 dbt tests. Its distinct game/platform pairs preserve unmatched platform IDs and follow the genre bridge's null/duplicate/error policy. Existing local arrays supplied the validation sample without ingestion. See [task 6.2 commands and results](TESTING.md#task-62-game-platform-relationship-verification).

Task 6.3 adds `int_game_companies`, bringing the build to eight views, 44 documented columns, and 28 dbt tests. It retains one row per involved-company record, including repeated pairs, nullable references, independent nullable roles, and unloaded game/company IDs. All five existing relationship records matched raw and staging data without ingestion. The full enabled suite passed 528 tests; raw/history hashes matched, disposable schemas were removed, and PostgreSQL was stopped/unregistered. See [task 6.3 exact commands and results](TESTING.md#task-63-game-company-relationship-verification).

Task 6.4 adds the eleven-column `mart_game_catalog` table: eight views plus one
table, nine documented models/55 columns, and 31 dbt tests. A successful build
refreshes the table snapshot; rerun after ingestion before exploring changed data.
Five local games and every catalog scalar/relationship object matched source
models without ingestion. The full enabled suite passed 558 tests, disposable
schemas were removed, raw/history hashes matched, and PostgreSQL was restored to
stopped/unregistered. Empty relationship arrays describe missing observations,
not proven absence. See [task 6.4 commands and results](TESTING.md#task-64-game-catalog-verification).

Task 6.5 adds the two-column `mart_release_trends` table directly over staged
games: eight views plus two tables, ten models/57 documented columns, and 36 dbt
tests. It counts dated games by observed UTC first-release year. Rebuild after
ingestion; a standalone test compares the stored table with current staging.
NULL dates are excluded, and missing years are omitted rather than zero-filled.
Neither implies unreleased games or verified real-world absence. The existing
five-game sample reconciles exactly: 1998 has two games, 2000/2004/2014 each have
one, and zero games are undated. No ingestion or settings change was needed.
See [task 6.5 commands and results](TESTING.md#task-65-annual-release-trends-verification).

Task 6.6 adds separate `mart_genre_performance` and `mart_platform_performance`
tables: eight views plus four tables, twelve models/71 documented columns, and
42 dbt tests. Grouping by observed IDs retains unloaded/unnamed dimensions while
independent pair aggregation prevents fanout. Five metrics provide game counts,
unweighted ratings and non-NULL denominators, and supplied rating-count context.
Rebuild after ingestion before reconciliation; NULL and zero remain distinct.
The local build matches every metric for four genre and nine platform rows,
without ingestion or schema-setting changes. The enabled suite passes 627 tests;
raw/history hashes match, disposable schemas are removed, and PostgreSQL is
stopped/unregistered. See [task 6.6 commands and results](TESTING.md#task-66-genreplatform-performance-verification).

Task 6.7 adds `mart_company_output`: eight views plus five tables, thirteen
models/80 documented columns and 45 dbt tests. It counts observed relationship
records and distinct game references by non-NULL company ID, including unloaded
games/companies. NULL games only count as records, and independent explicit role
counts can overlap. Loaded unobserved companies are omitted without claiming
absence. Rebuild after ingestion before reconciliation. All five local company
rows match independent source grouping without ingestion or settings changes;
full enabled tests pass 657, raw/history hashes match, disposable schemas are
removed and PostgreSQL is stopped/unregistered. See [task 6.7 commands and
results](TESTING.md#task-67-company-output-verification).

Task 6.8 audits all five mart contracts and adds one catalog array-container
invariant, bringing the build to 46 dbt tests without changing model SQL.
See the [contract coverage matrix](DATA_QUALITY.md#mart-contract-coverage-matrix-task-68)
and [validation record](TESTING.md#task-68-mart-contract-audit-verification).

## Docker PostgreSQL (task 7.1)

`compose.yaml` defines only PostgreSQL. **Task 7.1 is verified:** Colima resolved
the initial missing-engine blocker on October 2, 2026. Health, authenticated SQL,
container-replacement persistence, shutdown and all 533 enabled tests passed.
Python/dbt can also use the shared image described below (task 7.2).
Application Compose wiring and the clean-volume pipeline workflow remain tasks 7.3–7.5.

The image is `postgres:17.11-bookworm`, matching the native PostgreSQL 17.11 major
and minor version. The official [tag listing](https://github.com/docker-library/official-images/blob/master/library/postgres)
includes ARM64 and AMD64. Its [image configuration](https://github.com/docker-library/postgres/blob/2603e26e245e558218728ee14e0a42dcb020dc7f/17/bookworm/Dockerfile)
sets `PGDATA` and the volume mount to `/var/lib/postgresql/data`. The named
`postgres_data` volume uses that exact path. PostgreSQL 18+ images use a different
layout; changing major versions requires an explicit upgrade plan. The version
tag avoids automatic minor upgrades but is not an immutable image digest.

Install/start a Docker engine with current Compose supporting `up --wait` and
`--wait-timeout`. On this Mac, first use the [Colima shell setup below](#colima-on-this-mac).
From the repository root, in that dedicated **Bash** shell:

```bash
docker version
docker compose version
export POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433
export POSTGRES_DB=gaming_analytics POSTGRES_USER=postgres
read -r -s -p 'Docker PostgreSQL password: ' POSTGRES_PASSWORD
echo
export POSTGRES_PASSWORD
dc() { docker compose --env-file /dev/null -p data-platform-postgres -f compose.yaml "$@"; }
dc config --quiet
dc up -d --wait --wait-timeout 120 postgres
dc ps
```

Supply a nonempty password privately; do not paste it into commands, logs, or Git.
`--env-file /dev/null` prevents Compose from implicitly reading the existing `.env`.
Only the three named initialization variables enter the container. Database, user,
and password are required with no committed defaults. Exported connection settings
also override Python's `.env`; dbt reads exports directly. Do not source the native
`.env` afterward, which would replace those settings. Alternatively, explicitly
select a private external env file for Compose and export matching client settings.
Use `config --quiet`: plain `config`, `config --environment`, shell tracing, and
unfiltered container inspection can expose resolved secrets.

The health check runs TCP `pg_isready` inside the container every 5s, with a 5s
timeout, 12 retries, and a 10s startup grace period. `$$` defers variable expansion
to the container. TCP avoids accepting the [entrypoint's temporary socket-only
initialization server](https://github.com/docker-library/postgres/blob/2603e26e245e558218728ee14e0a42dcb020dc7f/docker-entrypoint.sh).
Readiness does not prove credentials or database access;
verify them from the host with the existing Python environment:

```bash
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python - <<'PY'
import os
import psycopg
with psycopg.connect(host=os.environ['POSTGRES_HOST'], port=os.environ['POSTGRES_PORT'],
                     dbname=os.environ['POSTGRES_DB'], user=os.environ['POSTGRES_USER'],
                     password=os.environ['POSTGRES_PASSWORD'], connect_timeout=5) as conn:
    assert conn.execute('SELECT current_database(), current_user').fetchone() == (
        os.environ['POSTGRES_DB'], os.environ['POSTGRES_USER'])
    print('Authenticated connection to the intended database passed')
PY
```

The temporary interpreter path is specific to this machine; use your activated
Python 3.11 environment elsewhere. The image's entrypoint creates the requested
database and a **superuser** only on first startup with an empty volume. This is
a local development service; it does not reproduce the native cluster's restricted
project role. Changing initialization variables later does not rename the database
or rotate its stored password. No custom initialization scripts, raw tables,
schemas, ingestion runs, or dbt models are provisioned by Compose.

For normal shutdown and later startup:

```bash
dc stop postgres
dc up -d --wait --wait-timeout 120 postgres
# Remove the container/network while keeping database files:
dc down
# Recreate the container against the same named volume:
dc up -d --wait --wait-timeout 120 postgres
# End the session:
dc down
unset POSTGRES_PASSWORD
```

The image requests PostgreSQL fast shutdown; Compose allows 30s before forced
termination. There is no automatic restart policy. Both `stop` and `down` retain
`data-platform-postgres_postgres_data`; reuse the same project name to reopen it.
Changing `-p` selects another volume and therefore a separate database. Never use
`down --volumes`, `docker volume prune`, or blanket cleanup on data you need.
The [disposable validation procedure](TESTING.md#task-71-docker-postgresql-validation)
checks a committed marker across actual container removal/recreation.

### Coexistence with Homebrew PostgreSQL

Docker publishes only `127.0.0.1:5433` by default; PostgreSQL inside the container
listens on 5432. Native Homebrew continues using 5432, so both can run at once.
Set `POSTGRES_PORT` to another unused host port if 5433 is occupied. Selecting
5432 conflicts if native PostgreSQL is running: either keep distinct ports or
explicitly stop native PostgreSQL using the commands above. Docker does not start,
stop, or register the Homebrew service. Its verified initial state remains stopped
and unregistered.

The Docker-managed volume and `/opt/homebrew/var/postgresql@17` are **separate
clusters** even with identical database/user names. Never mount the Homebrew data
directory into Docker. No data or watermark history is copied automatically;
selecting the Docker port will not expose native raw tables or marts. Preserve
the existing `.env` and native cluster. Close the dedicated shell when finished
so exported Docker connection settings do not affect later native work.

### Colima on this Mac

Installed October 2, 2026 through ARM Homebrew: Colima 0.10.3, Lima 2.2.0,
Docker CLI 29.8.1, and Compose 5.5.1. The `data-platform` profile uses Apple's
virtualization framework, 2 CPUs, 2 GiB RAM and a 10 GiB data disk. Its root disk
has a separate 20 GiB capacity; disk images grow as used. No host directories are
mounted into the VM, and no login startup service is registered.

The existing `~/.docker/config.json` references an old Docker Desktop credential
helper. It was preserved. A separate client config at
`~/.config/data-platform/docker/config.json` contains only
`cliPluginsExtraDirs: ["/opt/homebrew/lib/docker/cli-plugins"]`, allowing
`docker compose` to discover the Homebrew plugin without using the old helper.
Colima's context metadata is stored alongside that config.

Prepare each work shell and start the existing VM on demand:

```bash
export PATH="/opt/homebrew/bin:$PATH"
export DOCKER_CONFIG="$HOME/.config/data-platform/docker"
unset DOCKER_CONTEXT
export DOCKER_HOST="unix://$HOME/.colima/data-platform/docker.sock"
colima start data-platform --activate=false
docker version
docker compose version
```

`docker version` must report both client and server. The explicit socket prevents
accidental use of another engine; `/var/run/docker.sock` does not need to exist on
the Mac. Use the PostgreSQL exports and `dc` commands above afterward. Once project
containers have been stopped, stop the VM to release its CPU/RAM:

```bash
colima stop data-platform
```

Stopping the VM preserves its images and named volumes. Avoid `colima delete` for
routine shutdown. Colima's [Docker usage](https://github.com/abiosoft/colima#docker)
and [socket documentation](https://github.com/abiosoft/colima/blob/main/docs/FAQ.md#docker-socket-location)
describe the engine/client boundary. The installation fixes the missing engine;
agent execution still needs access to the socket and localhost database port.
Validation here uses scoped execution permission for the disposable project,
without changing socket permissions or disabling isolation globally.

## Shared Python/dbt image (task 7.2)

From the repository root, with the Docker shell above prepared:

```bash
docker build -f docker/Dockerfile -t data-platform-runtime:local .
docker run --rm --network none data-platform-runtime:local
docker run --rm --network none data-platform-runtime:local python --version
docker run --rm --network none data-platform-runtime:local python -m pip check
docker run --rm --network none data-platform-runtime:local dbt --version
docker run --rm --network none data-platform-runtime:local dbt parse --no-partial-parse
docker run --rm --network none data-platform-runtime:local python -m pytest -q -p no:cacheprovider
```

The default command is `python -m src.ingestion.run_ingestion --help`, which
requires no credentials or services. Override the command after the image name
to invoke existing Python modules, dbt, or pytest directly; there is no entrypoint
wrapper. `dbt --version` attempts a package-index version check; with `--network
none` it still reports installed versions but cannot report the latest release.

The base is the official `python:3.11.16-slim-bookworm`, verified for Linux ARM64
and published for AMD64 in the [official image list](https://github.com/docker-library/official-images/blob/master/library/python).
Debian Bookworm keeps the distro explicit, and the slim image installs the unchanged
`requirements.txt` without a compiler or extra OS packages. The verified runtime
uses Python 3.11.16, dbt Core 1.12.5, dbt-postgres 1.11.0 and Psycopg 3.3.6.
The version tag can be republished; dependency ranges remain unlocked. A fresh
build can resolve different compatible packages. See [recorded versions and
validation](TESTING.md#task-72-shared-image-validation).

The image works in `/app` and contains `requirements.txt`, `src/`, `dbt/` and the
existing `tests/`. Dependencies install before source copying for build-cache reuse.
Commands run as user `app` (UID 10001); `/app/data/raw` is an empty writable directory.
Python ingestion and dbt transformations retain their existing ownership and logic.
dbt project/profile paths default to `/app/dbt`, targets/logs to `/tmp/dbt/target`
and `/tmp/dbt/logs`. Python bytecode and dbt telemetry are disabled. No database
connection settings or source credentials are baked in.

`.dockerignore` allows the source/test trees and selected dbt definitions, then
excludes hidden files, credentials/secrets, environments, caches, local data and
generated artifacts even inside allowed trees. Git, `.env` (including examples),
all documentation including `docs/portfolio/`, archives and existing generated dbt
files never enter the context. The Dockerfile copies only the runtime trees.
Docker's [context filtering rules](https://docs.docker.com/build/concepts/context/#dockerignore-files)
are exercised by `docker/validate_image.py` using synthetic sentinels and an actual
context export. Run it with the host Python 3.11 environment:

```bash
PYTHONDONTWRITEBYTECODE=1 /private/tmp/data-platform-phase1-venv/bin/python docker/validate_image.py data-platform-runtime:local
```

For direct dbt commands against an **already running** task-7.1 PostgreSQL service,
export the intended database/user/password and existing schema selections in the
shell, then pass them by name. This example assumes its default Compose project
name; use the actual network name if a different project was selected:

```bash
docker run --rm --network data-platform-postgres_default \
  -e POSTGRES_HOST=postgres -e POSTGRES_PORT=5432 \
  -e POSTGRES_DB -e POSTGRES_USER -e POSTGRES_PASSWORD \
  -e POSTGRES_RAW_SCHEMA -e POSTGRES_SCHEMA -e DBT_SCHEMA \
  data-platform-runtime:local dbt build
```

Container-to-container connections use `postgres:5432`, not the host's loopback
port 5433. An unset `-e NAME` leaves that variable absent and retains the existing
schema fallback behavior; export the same selections as the Python runtime.
Runtime environment values are visible to Docker administrators; never provide
credentials through Dockerfile instructions, build arguments, or logged commands.
No `.env` or repository bind mount is required.

The same `docker run` options support `python -m src.ingestion.run_ingestion ...`;
actual ingestion additionally needs `-e igdb_client_id -e igdb_client_secret` and
persistent archive storage mounted at `/app/data/raw`, writable by UID 10001.
Without an explicit mount, archives and `/tmp` dbt output disappear with `--rm`.
Use `docker cp` from a stopped container before removing it to retain validation
artifacts, or explicitly supply external writable artifact paths/mounts. The Colima
profile here mounts no host directories; ordinary host bind mounts are therefore
not assumed. Never mount the native PostgreSQL cluster into any container.

Task 7.2 validates synthetic database fixtures only. There is no runtime Compose
service, bootstrap automation, live ingestion, Airflow or Streamlit in this change.
