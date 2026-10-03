# Local Development

## Compose first use and subsequent sessions (task 7.4)

Use this workflow from the repository root in a dedicated **Bash** shell.
Task 7.5 verified this workflow with new project-owned volumes, two bounded live
ingestions, a full dbt build and container-replacement persistence. See the
[commands, results and limits](TESTING.md#task-75-clean-volume-live-workflow-verification).
Nothing runs the pipeline automatically; the sample does not establish complete
source coverage or an uncapped incremental bootstrap.

### Select the environment

Prerequisites: Docker CLI, a running Docker engine, Compose with `up --wait` and
`--wait-timeout`, and registry/package-index access for the first image build.
Host Python/PostgreSQL are not needed for this container workflow. IGDB/Twitch
application credentials and internet access are needed only when ingesting.
On this Mac, use the existing [Colima shell setup](#colima-on-this-mac); it selects
the dedicated engine/config without changing `~/.docker`, mounts no host
directories and starts no login service. Elsewhere, select your intended engine
before continuing. Check `docker version` (client **and server**) and
`docker compose version`.

Choose a stable, distinct project name for a new environment; reuse that exact
name for every later session. The example below selects `data-platform-dev`,
separate from the earlier `data-platform-postgres` project. If resuming an existing
project, use its name, database/user/password and schema settings instead of these
new-environment examples. A new project name selects separate volumes; it does
not copy native data or another project's ingestion history.

```bash
unset COMPOSE_PROFILES COMPOSE_FILE POSTGRES_SCHEMA
unset igdb_client_id igdb_client_secret
export COMPOSE_PROJECT_NAME=data-platform-dev
export POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433
export POSTGRES_DB=gaming_analytics POSTGRES_USER=postgres
export POSTGRES_RAW_SCHEMA=raw DBT_SCHEMA=analytics LOG_LEVEL=INFO
read -r -s -p 'Docker PostgreSQL password: ' POSTGRES_PASSWORD
echo
export POSTGRES_PASSWORD
dc() { docker compose --env-file /dev/null -p "$COMPOSE_PROJECT_NAME" -f compose.yaml "$@"; }
dc config --quiet
```

Enter a nonempty password privately and retain it securely for subsequent sessions.
`POSTGRES_DB`, `POSTGRES_USER` and `POSTGRES_PASSWORD` are required even for
Compose help/parse invocations. Do not source the repository `.env` in this shell:
`--env-file /dev/null` bypasses it, while exported values feed the explicit
[runtime allowlist and schema settings](#on-demand-compose-runtime-task-73).
Use `config --quiet`; plain `config`/`config --environment`, shell tracing and
unfiltered container inspection can reveal credentials.

Host clients address `127.0.0.1:5433`; use another unused `POSTGRES_PORT` if
necessary. The runtime always addresses **`postgres:5432`** on the Compose
network, independent of the host port. Native PostgreSQL's port 5432 and storage
remain separate; see [coexistence](#coexistence-with-homebrew-postgresql).
Python and dbt source schemas resolve as `POSTGRES_RAW_SCHEMA` → `POSTGRES_SCHEMA`
→ `raw`; `DBT_SCHEMA` independently defaults to `analytics`. Unset differs from
empty: do not export empty schema names. Keep an existing installation's selections
unless deliberately migrating its tables **and** history; changing a setting
does not migrate anything. See [schema compatibility](#schema-names-and-existing-analytics-installations).

### Build, start and check readiness

```bash
# Build once; repeat after source/dbt/requirements/Dockerfile changes.
# These flags use the existing legacy builder on this Mac without installing buildx.
DOCKER_BUILDKIT=0 COMPOSE_BAKE=false dc build runtime
dc up -d --wait --wait-timeout 120 postgres
dc ps
# Authenticate from the runtime without ingesting or building models:
dc run --rm runtime dbt debug --connection
```

Building downloads image/dependency content and packages the current source; there
is no repository bind mount, so edits require rebuilding. Credentials and local
data are excluded from the [image context](#shared-pythondbt-image-task-72).
Ordinary Compose startup selects only PostgreSQL. `runtime` is behind the `tools`
profile; explicit `dc run runtime ...` selects it and waits for healthy PostgreSQL
without needing `--profile tools`. One-off commands exit when finished.

The TCP health check waits past PostgreSQL's temporary initialization server.
Health alone does not authenticate the supplied password. `dbt debug --connection`
checks the configured database connection and writes logs, but creates no pipeline
tables. Use `--connection` in the slim runtime: plain `dbt debug` also checks for
Git, which is not installed in the image.
If startup times out, inspect `dc ps` and `dc logs postgres` locally before
continuing. If authentication fails on an existing volume, check its original
credentials; do not delete the volume to repair a settings mismatch.

Initialization has three separate owners:

| Owner | When and what it creates |
|---|---|
| PostgreSQL image | First startup with an **empty** `postgres_data` volume initializes the cluster and requested database/user. The configured user is a local-development superuser. Existing-volume startup reopens the cluster; changed environment values do not rename databases/users or rotate stored passwords. |
| Python ingestion | Against an existing database, creates the selected raw schema, `ingestion_runs` and each selected entity's `raw_<entity>` table, archives payloads and upserts rows. It does not create the database/login. |
| dbt | Reads the five existing raw tables, creates its output schema/models and runs tests. Source declarations and `dbt parse` create no raw tables. |

The warehouse has no custom initialization scripts, migrations or automatic
raw/dbt bootstrap steps. Optional Airflow has a separate explicit metadata
initialization command, described [below](#local-airflow-task-81).

### Run commands on demand

Inspect/parse without IGDB or database access (parse writes dbt artifacts):

```bash
dc run --rm --no-deps runtime python -m src.ingestion.run_ingestion --help
dc run --rm --no-deps runtime dbt parse --no-partial-parse
```

`--no-deps` skips PostgreSQL startup; it does not disable the container network.
For network-disabled direct-image checks and Python tests, see the
[shared image commands](#shared-pythondbt-image-task-72) and
[testing guide](TESTING.md#postgresql-integration-tests).

The following is a **live, data-changing** sequence, verified with bounded runs
in task 7.5 (task 7.4 only documented it). Enter the source
credentials only when ready to contact Twitch/IGDB and write archives, raw rows
and run metadata in the selected environment:

```bash
read -r -s -p 'IGDB client ID: ' igdb_client_id
echo
read -r -s -p 'IGDB client secret: ' igdb_client_secret
echo
export igdb_client_id igdb_client_secret
# Bounded first-use sample: at most five records per entity, 25 total.
# Build only if all entity ingestions succeed.
dc run --rm runtime python -m src.ingestion.run_ingestion \
  --entity all --batch-size 5 --max-batches 1 &&
dc run --rm runtime dbt build
unset igdb_client_id igdb_client_secret
```

Ingestion runs games → genres → platforms → companies → involved_companies,
with separate archives/metadata and idempotent raw upserts. Failure stops later
entities but retains earlier commits. A capped run never advances watermarks;
it also cannot establish complete source/reference coverage. Before a deliberate
uncapped run, read the [ingestion modes](../pipeline/INGESTION.md#explicit-refresh-and-backfill-task-47)
and [watermark policy](../pipeline/WATERMARKS.md). An uncapped normal run with no
eligible history bootstraps the endpoint; it is not a required startup step.

`dbt build` makes no IGDB calls, but **creates/replaces analytics relations** and
runs database tests. It requires all five raw tables in the selected source
schema; starting PostgreSQL alone or ingesting only games is insufficient for
the full project. The current build contains eight views, five mart tables and
46 tests. After later ingestion, rebuild to refresh the marts' stored snapshots;
see the [dbt build contract](../pipeline/DBT_TRANSFORMATIONS.md#build-contract).

### Preserve, export, shut down and resume

The project retains three named volumes: `postgres_data` (database, raw rows,
history and dbt models), `raw_archives` (`/app/data/raw`) and `dbt_artifacts`
(`/tmp/dbt`). The latter two are writable as `app`, UID 10001. All survive
one-off `--rm`, `dc down` and Colima shutdown. They are separate from host files.
Use the [artifact export procedure](#compose-archive-and-artifact-persistence)
before shutdown when you need local copies; it uses `docker cp` without host
mounts. Those raw/dbt exports are not a database backup.

Wait for active one-off commands to finish, then choose either shutdown form:

```bash
dc stop postgres  # Keep the stopped container and all volumes.
# Or remove this project's containers/network while retaining all volumes:
dc down
unset POSTGRES_PASSWORD igdb_client_id igdb_client_secret
# On this Mac, after all intended project containers have stopped:
colima stop data-platform
```

Do not use `down --volumes`, volume pruning or `colima delete` for routine
shutdown. Closing a terminal does not stop PostgreSQL/Colima; there is no automatic
restart or login service. In the next session, repeat environment/engine selection
with the **same project name and stored credentials/schema settings**, then:

```bash
dc up -d --wait --wait-timeout 120 postgres
dc run --rm runtime dbt debug --connection
```

Reuse the image unless its inputs changed. Existing database tables, rows,
watermarks and volumes reopen; no ingestion, restore, migration or dbt rebuild is
required merely to resume. Run ingestion/build only when you intend to refresh data.

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

The verified result was `('gaming_analytics', 'postgres')`. The pipeline creates its configured schema and tables. Two bounded genres smoke runs then passed; see [Testing](TESTING.md#task-31-live-smoke-completion). Task 3.2 also passed two bounded platforms runs using this existing cluster, then stopped/unregistered PostgreSQL; see [platforms verification](TESTING.md#task-32-verification). Task 3.3 passed two bounded companies runs against the existing database and left PostgreSQL stopped/unregistered; see [companies verification](TESTING.md#task-33-verification). Task 3.4 passed two bounded involved-companies runs and again left PostgreSQL stopped/unregistered; see [relationship verification](TESTING.md#task-34-verification). Task 3.5 passed two bounded games runs exercising genre/platform/involved-company references and again left PostgreSQL stopped/unregistered; see [games verification](TESTING.md#task-35-verification). Task 3.6 passed two actual all-entity CLI runs and left PostgreSQL stopped/unregistered; see [CLI verification](TESTING.md#task-36-verification). Wait for `pg_isready` to report accepting connections after startup before connecting. These instructions operate the native cluster; the separate Docker workflow is documented above.

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

`requirements.txt` contains the current runtime and test dependencies: requests, python-dotenv, psycopg (binary), dbt-postgres, and pytest. Airflow uses its own optional container image; Streamlit remains future work. Dependency ranges are bounded but not locked; installation does not guarantee identical transitive versions on every date. No dependency changes were needed for the Phase 1 validation.

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

`compose.yaml` defines PostgreSQL and an on-demand runtime. **Task 7.1 is verified:**
Colima resolved the initial missing-engine blocker on October 2, 2026. Health,
authenticated SQL, container-replacement persistence, shutdown and all 533 enabled
tests passed. For the current procedure, use [first use and subsequent sessions](#compose-first-use-and-subsequent-sessions-task-74);
task 7.5 also verified bounded clean-volume ingestion and dbt build. This section
retains the database configuration details.

The image is `postgres:17.11-bookworm`, matching the native PostgreSQL 17.11 major
and minor version. The official [tag listing](https://github.com/docker-library/official-images/blob/master/library/postgres)
includes ARM64 and AMD64. Its [image configuration](https://github.com/docker-library/postgres/blob/2603e26e245e558218728ee14e0a42dcb020dc7f/17/bookworm/Dockerfile)
sets `PGDATA` and the volume mount to `/var/lib/postgresql/data`. The named
`postgres_data` volume uses that exact path. PostgreSQL 18+ images use a different
layout; changing major versions requires an explicit upgrade plan. The version
tag avoids automatic minor upgrades but is not an immutable image digest.

The TCP health check runs `pg_isready` inside the container every 5s, with a 5s
timeout, 12 retries and a 10s startup grace period. `$$` defers variable expansion
to the container. TCP avoids accepting the entrypoint's temporary socket-only
initialization server. The [startup workflow](#build-start-and-check-readiness)
distinguishes readiness, authenticated access and first-empty-volume initialization.

The image requests PostgreSQL fast shutdown; Compose allows 30s before forced
termination. There is no automatic restart policy. `stop` and `down` retain the
project's `postgres_data` volume. The [task 7.1 validation record](TESTING.md#task-71-docker-postgresql-validation)
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
the Mac. Then use the [environment selection and `dc` commands](#select-the-environment) above. Once project
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

Task 7.2 validated synthetic database fixtures only. Task 7.3 adds the Compose
runtime below; bootstrap automation, live ingestion validation, Airflow and
Streamlit remain outside this change.

## On-demand Compose runtime (task 7.3)

`runtime` uses the shared Dockerfile and the `tools` profile. Ordinary `dc up`
starts only PostgreSQL. Explicit `dc run runtime ...` selects the runtime without
requiring `--profile tools`, waits for the PostgreSQL health dependency, executes
the supplied command, and exits. Its inherited default is ingestion CLI help.
No ingestion, migrations, or dbt build runs automatically. The profile is intended
for one-off commands; there is no long-running application or restart policy.

Use the [first-use/session workflow](#compose-first-use-and-subsequent-sessions-task-74)
for environment selection, building, readiness and command order. The default runtime
command is ingestion CLI help. `dc run --rm --no-deps runtime ...` skips the database
dependency for help/parsing, but still needs the three required Compose database
settings. It does not disable networking. Direct image commands remain available
for entirely unconfigured offline checks.

Only the database settings, two source credential names, source/output schema
settings and `LOG_LEVEL` pass from Compose's environment to the runtime. The
service has no `env_file` bulk injection, build arguments, credential mount or
repository mount. Variables exported in the shell override values in an explicitly
selected Compose env file. With plain `docker compose` and no `--env-file`, Compose
can load the repository `.env` for interpolation, including the allowlisted bare
keys. Prefer the explicit file/dedicated shell to avoid selecting native settings
accidentally. dbt receives these variables directly; Python's packaged `/app`
contains no `.env` to load. Docker administrators can inspect container credentials.
Use `dc config --quiet` to validate without printing resolved secrets.

| Setting | Compose runtime behavior |
|---|---|
| `POSTGRES_HOST` | Fixed to service name `postgres`, regardless of host setting |
| `POSTGRES_PORT` | Fixed to container port `5432`; external value only controls PostgreSQL's loopback host publication, default `5433` |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Required externally, shared with the selected PostgreSQL service |
| `POSTGRES_RAW_SCHEMA`, `POSTGRES_SCHEMA` | Passed only when set; Python/dbt retain explicit → legacy → `raw` precedence |
| `DBT_SCHEMA` | Passed only when set; independent output default `analytics` |
| `igdb_client_id`, `igdb_client_secret`, `LOG_LEVEL` | Passed only when set; needed source credentials are checked by existing ingestion code |

Unset and empty schema values differ: empty is explicitly set and is not a fallback.
Do not export empty schema names. No variable change migrates native tables or
watermarks. A changed password in the environment does not rotate a password in an
already initialized PostgreSQL volume; incorrect credentials fail at authentication.
The TCP readiness check alone does not authenticate the runtime.

### Compose archive and artifact persistence

The runtime stays `app` (UID 10001) in `/app`. Docker initializes these project-scoped
named volumes from empty image directories owned by that user:

| Volume | Container path | Contents |
|---|---|---|
| `raw_archives` | `/app/data/raw` | Existing default timestamped per-entity JSONL output |
| `dbt_artifacts` | `/tmp/dbt` | Default `target/` and `logs/` for direct dbt commands |

Archives and direct dbt artifacts survive `run --rm`, container replacement,
`dc down` and Colima shutdown. They are separate from host `data/raw` and existing
host dbt artifacts. Named volumes work with this Colima profile's lack of host
mounts. The Dockerfile supplies initial directory ownership; there is no root
entrypoint or permission/bootstrap service. An externally supplied volume with
incompatible ownership is not repaired automatically.

Changing the Compose project name selects different volumes. Normal `down` retains
all three volumes, including `postgres_data`; do not use `down --volumes` for data
you need. An ingestion `--output-path` outside `/app/data/raw`, overridden dbt paths
outside `/tmp/dbt`, and pytest's ordinary `/tmp` output are ephemeral unless copied
before removing the container. Sequential direct dbt commands share/overwrite
normal target filenames and append logs. Concurrent commands should use distinct
`--target-path` and `--log-path` subdirectories beneath `/tmp/dbt`.

To export files without any host bind mount, create a stopped container holding
the volumes, then copy to a new external directory (use an unused container name):

```bash
export_dir=$(mktemp -d /private/tmp/data-platform-export.XXXXXX)
dc run --no-deps --name data-platform-export runtime true
docker cp data-platform-export:/app/data/raw/. "$export_dir/raw"
docker cp data-platform-export:/tmp/dbt/. "$export_dir/dbt"
docker rm data-platform-export
```

The copy preserves volume data; inspect the export before any intentional removal.
Task 7.3 verified this using synthetic files and offline dbt artifacts only. The
full enabled suite used an isolated internal network with generated credentials;
see [exact validation](TESTING.md#task-73-compose-runtime-validation). The
[first-use workflow](#compose-first-use-and-subsequent-sessions-task-74) documents
command order; [task 7.5](TESTING.md#task-75-clean-volume-live-workflow-verification)
verified real bounded archives, raw/history/model persistence and artifact export
from new volumes. Disposable validation cleanup enabled `--profile tools` before
`down --volumes` to include the runtime volumes; this is destructive and is not
the normal session shutdown command.

## Local Airflow (task 8.1)

Airflow is optional. Plain `dc up` remains PostgreSQL-only; `tools` commands need
no Airflow credentials. The `airflow` profile selects the API/UI server, scheduler,
DAG processor and a separate metadata PostgreSQL service. `airflow-init` is a
separate one-off profile so ordinary Airflow startup does not migrate a database.
The manual ingestion → dbt DAG is described below. See [topology and command execution](../pipeline/ORCHESTRATION.md#local-infrastructure-task-81).

Airflow recommends **at least 4 GB memory** (the Docker guide prefers 8 GB).
Use that as the baseline for future ingestion/dbt workloads, with at least two
CPUs for this local configuration. The existing 2 CPU/2 GiB Colima profile passed
idle infrastructure checks with one API worker, one parsing process and
LocalExecutor parallelism 1; this is not a pipeline capacity test. Do not resize
or recreate that profile implicitly. If it exhausts memory, stop the task services,
inspect `docker stats` and container OOM state, and obtain approval for a resource
change. No broker, distributed worker or triggerer is needed for ordinary command
tasks. Deferrable operators would require revisiting the triggerer decision.

### First use

Prepare the existing [Docker shell](#colima-on-this-mac) and
[project/database environment](#select-the-environment), including the `dc`
function that always supplies `--env-file /dev/null`. Do not source `.env` or load
IGDB credentials for infrastructure setup. Choose a new project for validation;
reuse the same project and credentials for later sessions. In that shell:

```bash
unset igdb_client_id igdb_client_secret COMPOSE_PROFILES
export AIRFLOW_PORT=8080  # Choose an unused loopback port.
read -r -s -p 'Separate Airflow metadata DB password: ' AIRFLOW_DB_PASSWORD
echo
read -r -s -p 'Airflow admin password: ' AIRFLOW_ADMIN_PASSWORD
echo
export AIRFLOW_DB_PASSWORD AIRFLOW_ADMIN_PASSWORD
dc --profile airflow config --quiet
DOCKER_BUILDKIT=0 COMPOSE_BAKE=false dc build airflow-init
# Explicit first-use operation; starts only its metadata DB dependency.
dc run --rm -T airflow-init
unset AIRFLOW_ADMIN_PASSWORD
# Also selects the ordinary warehouse PostgreSQL service.
dc --profile airflow up -d --wait --wait-timeout 240
dc --profile airflow ps
```

Retain both passwords privately. The image pins `apache/airflow:3.3.2-python3.11`
and packages the initialization helper, ingestion source, existing dbt project/profile,
one DAG and an isolated ingestion/dbt virtual environment. No host Airflow
installation is needed. The root allowlisted build context excludes repository data/credentials; the image copies
only the files needed for ingestion, dbt and Airflow initialization. Airflow runs as
UID 50000/GID 0, following the official image's non-root permission model. GID 0
does not make the process root. Named volumes inherit writable image directories;
there are no host mounts, privileged containers or Docker socket mounts.

The dedicated `airflow-postgres:5432/airflow` database uses its own password and
`airflow_postgres_data` volume, with no host port. Its image-created `airflow` role
is a local-development superuser **only in that separate metadata cluster**;
it has no account in the warehouse. Only the scheduler receives `POSTGRES_*`
and source/dbt settings for command execution; API, processor and init do not. The warehouse remains `postgres:5432` with
its unchanged raw/output schema behavior. Empty Airflow passwords fail on Airflow
startup; they do not prevent PostgreSQL/tools configuration or use.

First initialization privately writes the `admin` password, a random Fernet key
and a shared JWT signing secret into `airflow_config`, then runs `airflow db migrate`
against the fixed metadata target. Password URI characters are encoded. File mode
is 0600; nothing prints the passwords or keys. Do not run initialization concurrently.
With services stopped, repeating it preserves all files and safely reruns the
migration; the admin password can be omitted afterward. A supplied different
admin password or missing retained keys fails instead of rotating state. On a
migration error, preserve volumes, inspect logs, correct the cause and rerun.
Never use this procedure to migrate an existing unrelated database.

### Authentication, health and logs

Open `http://127.0.0.1:8080` (or the selected `AIRFLOW_PORT`) and log in as `admin`
with the password supplied at initialization. SimpleAuthManager is explicitly
enabled, with anonymous-admin mode disabled. It is Airflow's development/testing
auth manager, appropriate only for this loopback local deployment. The password
file is private plaintext; protect exported backups and Docker access.

The API uses a JWT from `POST /auth/token`, not HTTP Basic authentication.
This optional probe prompts privately and prints only statuses/counts:

```bash
python - <<'PY'
import getpass, json, os, urllib.request
base = 'http://127.0.0.1:' + os.environ.get('AIRFLOW_PORT', '8080')
body = json.dumps({'username': 'admin', 'password': getpass.getpass('Airflow password: ')}).encode()
request = urllib.request.Request(base + '/auth/token', data=body, headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(request) as response:
    token = json.load(response)['access_token']
request = urllib.request.Request(base + '/api/v2/dags', headers={'Authorization': 'Bearer ' + token})
with urllib.request.urlopen(request) as response:
    print('Authenticated; DAG count:', json.load(response)['total_entries'])
PY
```

Expect exactly `igdb_ingestion` after task 8.2, initially paused. The API container health check calls `/api/v2/version`;
the scheduler has its own `/health` server on internal port 8974; the DAG processor
uses `airflow jobs check --job-type DagProcessorJob --local`. PostgreSQL readiness
uses TCP. Verify authenticated metadata access and inspect aggregate health:

```bash
dc exec -T airflow-scheduler airflow db check
curl --fail --silent "http://127.0.0.1:${AIRFLOW_PORT:-8080}/api/v2/monitor/health"
dc --profile airflow logs --tail 100 airflow-api-server airflow-scheduler airflow-dag-processor airflow-postgres
```

Read the health JSON: `metadatabase`, `scheduler`, and `dag_processor` must each
be `healthy`; an HTTP 200 alone does not prove that. `triggerer` is null by design.
Only API/UI port 8080 is published, bound to loopback. Scheduler log/health ports
remain internal. Service logs go to Docker stdout; task/processor file logs persist
in `airflow_logs`, including both `ingest_all` and `dbt_build` command output and failures.
Do not print resolved Compose configuration, unfiltered environments, keys or tokens.

### Manual ingestion and dbt DAG (tasks 8.2–8.3)

Rebuild after DAG/source/dbt/dependency changes and recreate all Airflow components:

```bash
DOCKER_BUILDKIT=0 COMPOSE_BAKE=false dc build airflow-init
dc --profile airflow up -d --force-recreate --wait --wait-timeout 240
dc exec -T airflow-scheduler airflow dags list-import-errors -o json
dc exec -T airflow-scheduler airflow dags list -o json
```

Expect no import errors and only `igdb_ingestion`. Startup/discovery never ingests.
The DAG has exactly `ingest_all` → `dbt_build` and `schedule=None`, initially paused.
A manual trigger uses the existing **uncapped** normal `--entity all` command; it may bootstrap
whole endpoints. Select the intended warehouse/source schema and supply source
credentials only when deliberately ready for live ingestion, then recreate the
scheduler to receive them. Unpause and trigger `igdb_ingestion` in the UI to run it;
inspect both task statuses and logs. Successful ingestion now runs the existing
full dbt build (13 models/46 tests) against the selected warehouse. An ingestion
failure prevents dbt execution until ingestion succeeds. Each task has one
automatic retry after a fixed one-minute delay (two total attempts). Exhausted
ingestion leaves dbt unstarted; exhausted dbt fails the DAG and can leave some
relations updated. Inspect `up_for_retry` and both attempt logs before diagnosing
a final failure. A retry repeats the entire all-entity CLI or dbt build; earlier
commits remain. See [retry and failure policy](../pipeline/ORCHESTRATION.md#dependencies-retries-and-failure-behavior-task-84).
There are no runtime command parameters or recurring schedule. Validation uses
synthetic HTTP responses; live-source Airflow execution and real workload capacity
remain unverified.

Archives live in the separate persistent `airflow_raw_archives` volume at
`/opt/airflow/app/data/raw`, writable by scheduler UID 50000. Tools archives remain
in `raw_archives` under UID 10001; neither store is automatically copied to the other.
Both commands use the same warehouse/schema selections and existing ingestion
history. Avoid concurrent manual/tools ingestions against these schemas; task retries
do not provide a lock across runs or standalone commands. `DBT_SCHEMA` independently
selects outputs for both the tools runtime
and the Airflow scheduler; export it before creating the scheduler. The existing
explicit → legacy → `raw` source-schema precedence applies to both commands.

`dbt_build` executes `/opt/airflow/app-venv/bin/dbt build` with explicit
`--project-dir /opt/airflow/app/dbt --profiles-dir /opt/airflow/app/dbt`. Scheduler-only
settings disable dbt telemetry and write targets/logs under `/opt/airflow/dbt-artifacts`
in the dedicated `airflow_dbt_artifacts` volume, writable as UID 50000. The tools'
UID-10001 `dbt_artifacts` volume remains independent. Normal shutdown retains both.
Sequential dbt runs overwrite target filenames and append logs; export before the
next build or automatic retry when retaining invocation evidence. The retry wait
is at least 60 seconds; no automatic per-run artifact retention is added.

Export Airflow archives and dbt artifacts before deleting disposable validation volumes:

```bash
airflow_container=$(dc ps -q airflow-scheduler)
export_dir=$(mktemp -d /private/tmp/data-platform-airflow-archives.XXXXXX)
chmod 700 "$export_dir"
docker cp "$airflow_container:/opt/airflow/app/data/raw/." "$export_dir/raw"
docker cp "$airflow_container:/opt/airflow/dbt-artifacts/." "$export_dir/dbt"
```

### Preserve, shut down and resume

For a private export outside the repository, use `docker cp` from the running
scheduler plus a metadata dump (the latter does not contain login-role passwords):

```bash
export_dir=$(mktemp -d /private/tmp/data-platform-airflow-export.XXXXXX)
chmod 700 "$export_dir"
airflow_container=$(dc ps -q airflow-scheduler)
docker cp "$airflow_container:/opt/airflow/config/." "$export_dir/config"
docker cp "$airflow_container:/opt/airflow/logs/." "$export_dir/logs"
dc exec -T airflow-postgres pg_dump -U airflow -d airflow --no-owner --no-privileges > "$export_dir/metadata.sql"
# Stop/remove this project's containers; keep ALL named volumes.
dc --profile airflow --profile airflow-init --profile tools down
unset AIRFLOW_DB_PASSWORD AIRFLOW_ADMIN_PASSWORD POSTGRES_PASSWORD
colima stop data-platform  # This Mac; only after intended containers are stopped.
```

Keep metadata, configuration/keys and logs together. Exports above are not a tested
restore procedure. Routine shutdown must not use `--volumes`. On a subsequent
session, start the existing engine, select the same project, re-export warehouse
settings and the original `AIRFLOW_DB_PASSWORD`, then run
`dc --profile airflow up -d --wait --wait-timeout 240`. No admin password input or
migration is required merely to resume. Rebuild after image/helper changes; review
release migration guidance before changing the Airflow pin. Changing environment
passwords does not rotate PostgreSQL credentials in existing volumes.

Only for a verified disposable project, after exporting evidence, cleanup includes
all profiles: `dc --profile airflow --profile airflow-init --profile tools down --volumes`.
Never prune other projects or delete retained volumes to fix authentication errors.
