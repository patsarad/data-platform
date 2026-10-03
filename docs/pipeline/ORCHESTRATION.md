# Orchestration

## Purpose

Airflow coordinates already-runnable pipeline components. It should not become the only place where ingestion or transformation logic works.

## Current state

`dags/igdb_ingestion.py` defines one manual DAG with two command tasks:
`ingest_all` → `dbt_build`. The existing ingestion CLI must succeed before dbt runs.

## Local infrastructure (task 8.1)

Compose provides opt-in Airflow infrastructure, with bundled examples disabled.
The image extends `apache/airflow:3.3.2-python3.11` with a local initialization
helper and tasks 8.2–8.3 command packaging described below. The standalone tools image
and application `requirements.txt` retain their dependencies.
Official [version support](https://airflow.apache.org/docs/apache-airflow/stable/installation/supported-versions.html)
identifies Airflow 3 as maintained (2 is EOL), and the pinned release's
[prerequisites](https://airflow.apache.org/docs/apache-airflow/3.3.2/installation/prerequisites.html)
include Python 3.11 and PostgreSQL 17. Version tags are explicit but not immutable
digests. Recheck support and migrations before upgrading.

| Service | Responsibility |
|---|---|
| `airflow-api-server` | UI, authenticated public API and internal execution API; one API worker; only loopback UI/API publication |
| `airflow-scheduler` | Scheduling infrastructure and LocalExecutor; at most one task process |
| `airflow-dag-processor` | Separate Airflow 3 DAG parsing process; one parser, baked ingestion DAG |
| `airflow-postgres` | Dedicated PostgreSQL 17.11 metadata cluster/database/login and persistent volume; no host port |
| `airflow-init` | Explicit one-off secret/account initialization and `airflow db migrate`, separately profiled |

[LocalExecutor](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/executor/local.html)
runs task subprocesses on the scheduler, requiring no broker or distributed worker.
Its positive `parallelism=1` limits local resource use; this is an executor capacity
setting, not a DAG dependency/retry policy. PostgreSQL supplies concurrent metadata
access. A triggerer is unnecessary until deferrable operators are introduced.
The [official Docker example](https://airflow.apache.org/docs/apache-airflow/3.3.2/howto/docker-compose/index.html)
uses a larger Celery topology; this project keeps only components needed for local
command tasks. It recommends at least 4 GB RAM, ideally 8 GB. Task 8.1's idle smoke
on the existing 2 GiB VM does not validate capacity for ingestion/dbt execution.

[SimpleAuthManager](https://airflow.apache.org/docs/apache-airflow/3.3.2/core-concepts/auth-manager/simple/index.html)
provides local-development authentication for the fixed `admin` account. A private
password file is seeded before API startup, preventing automatic password logging.
Anonymous-admin mode is disabled. Fernet and JWT keys persist in `airflow_config`;
all components share the signing key. Metadata, configuration and logs use three
Airflow-only named volumes. Only the scheduler receives warehouse/source settings
for LocalExecutor command execution; API, processor and init do not receive them.
Only initialization accepts the admin password; subsequent sessions reuse the file.
Initialization is explicit, serial, repeatable and fails on conflicting passwords.

Health checks follow the [official health guide](https://airflow.apache.org/docs/apache-airflow/3.3.2/administration-and-deployment/logging-monitoring/check-health.html):
API version endpoint, scheduler's independent HTTP health server, DAG-processor job
heartbeat and PostgreSQL TCP readiness. Aggregate health requires inspecting each
JSON status, not just HTTP 200. Authentication is verified separately.
See [first use, credentials, health, exports and subsequent sessions](../engineering/LOCAL_DEVELOPMENT.md#local-airflow-task-81).

### Ingestion command DAG (task 8.2)

`igdb_ingestion` uses the Airflow 3 public [`airflow.sdk.DAG`](https://airflow.apache.org/docs/apache-airflow/3.3.2/public-airflow-interface.html)
and standard-provider [`BashOperator`](https://airflow.apache.org/docs/apache-airflow-providers-standard/stable/_api/airflow/providers/standard/operators/bash/index.html).
The verified base bundles standard provider 1.19.0; no provider installation or
Airflow dependency is added to application requirements. The command is fixed:

```text
exec /opt/airflow/app-venv/bin/python -m src.ingestion.run_ingestion --entity all
```

The task works in `/opt/airflow/app`, preserving imports and default archive paths.
`exec` propagates the CLI exit status; `skip_on_exit_code=None` treats every nonzero
exit as failure, including 99. XCom output is disabled. The DAG uses `schedule=None`
and starts paused. No start date is necessary for this manual-only DAG; recurring
schedule/start-date/catchup policy remains task 8.5. Task 8.4 adds the built-in
whole-command retry policy below. No backfill policy or arbitrary run-config
command input is added.
The CLI still runs games → genres → platforms → companies → involved companies,
with its existing fail-fast behavior and separate per-entity commits/checkpoints.

LocalExecutor runs inside the scheduler. The image packages `src/`, the DAG and
requests, python-dotenv, Psycopg and dbt-postgres (including their dependencies) in
`/opt/airflow/app-venv`, without system site packages. These constraints match the
standalone requirements. The historical `requirements-ingestion.txt` filename now
contains both application commands’ dependencies. Airflow keeps its own interpreter
and dependencies; Airflow and pytest are absent from the application virtual environment. The root build
context allowlist supports the existing legacy builder; only explicit copies enter
the image. The old `docker/airflow/.dockerignore` is unused by this root-context build.
Rebuild and recreate all Airflow components together to deploy DAG/source changes.
No host mount, Docker socket, root process or separate command service is needed.

Only the scheduler receives warehouse/source settings. `postgres:5432` is fixed;
source schema precedence remains `POSTGRES_RAW_SCHEMA` → `POSTGRES_SCHEMA` → `raw`.
`DBT_SCHEMA` independently selects outputs in the tools runtime and scheduler.
The scheduler waits for warehouse health and writes to `airflow_raw_archives` at
`/opt/airflow/app/data/raw`, initialized for UID 50000. This separate volume avoids
changing ownership of existing UID-10001 tools archives. Both archive stores persist
across container replacement and normal `down`; host archives are separate again.

Task 8.2 validation executes the exact command through Airflow with a temporary
HTTP-boundary double and real PostgreSQL on a new internal-only validation network.
This verifies orchestration, synthetic raw loading/archives and failure propagation;
it does not establish live IGDB ingestion or real workload capacity. See
[validation](../engineering/TESTING.md#task-82-ingestion-dag-verification).

### dbt build after ingestion (task 8.3)

The second BashOperator invokes the existing project without duplicating SQL:

```text
exec /opt/airflow/app-venv/bin/dbt build --project-dir /opt/airflow/app/dbt --profiles-dir /opt/airflow/app/dbt
```

It uses the same working directory, nonzero-exit failure handling and disabled
XCom output as ingestion. `ingest_all >> dbt_build` explicitly uses Airflow 3.3.2's
[`all_success` trigger rule](https://airflow.apache.org/docs/apache-airflow/3.3.2/core-concepts/dags.html#trigger-rules).
After ingestion exhausts its retries, dbt becomes `upstream_failed` without
executing. After dbt exhausts its retries, its task and the DAG run fail. Task 8.4
configures the bounded policy below; tasks 8.5–8.6 remain separate work.

The shared Airflow image bakes the existing `dbt/` project/profile alongside source
and DAGs. The absolute dbt executable belongs to the isolated app environment.
Only the scheduler receives `DBT_SCHEMA`, disabled usage reporting, and artifact
settings: `DBT_TARGET_PATH=/opt/airflow/dbt-artifacts/target` and
`DBT_LOG_PATH=/opt/airflow/dbt-artifacts/logs`. The dedicated
`airflow_dbt_artifacts` volume inherits UID-50000 write permissions and survives
container replacement. UID-10001 tools volumes remain separate.

[`dbt build`](https://docs.getdbt.com/reference/commands/build) builds the existing
13 models and runs 46 tests; failing upstream dbt tests can skip downstream models.
Manifest/run results are written to the target directory and dbt logs to the log
directory. Sequential runs overwrite target filenames and append logs; export
artifacts before another build if per-run evidence is needed. This task adds no
per-run retention policy. LocalExecutor parallelism one serializes task commands;
operators should still avoid overlapping manual/tools runs against the same schemas.
All five raw tables must exist. dbt failure does not roll back ingestion, its
watermarks, or already completed dbt relations. See [build contract](DBT_TRANSFORMATIONS.md#build-contract)
and [synthetic task-8.3 validation](../engineering/TESTING.md#task-83-dbt-task-verification).

## Dependencies, retries and failure behavior (task 8.4)

Both tasks inherit the same explicit DAG `default_args`: `retries=1`,
`retry_delay=timedelta(minutes=1)`, `retry_exponential_backoff=False`, and
`trigger_rule="all_success"`. That allows **two total attempts per task**, with
retry eligibility 60 seconds after the failed attempt ends; scheduler capacity
can delay execution further. A shared policy is sufficient because either command
can encounter a brief database/service interruption. One retry bounds repeated
source reads and full-project builds; one minute allows a brief outage to recover.
Permanent credentials, configuration or data-quality errors can fail both attempts
and need operator correction. No error classification or custom retry framework
is added to the shell operator.

Airflow's [task lifecycle and retry behavior](https://airflow.apache.org/docs/apache-airflow/3.3.2/core-concepts/tasks.html)
keeps a failed first attempt `up_for_retry` and the DAG running. Ingestion's
success dependency keeps dbt unstarted during that wait. Exhausted ingestion
becomes `failed`, dbt becomes `upstream_failed`, and the DAG fails. When ingestion
succeeds, dbt may start; its exhausted retries likewise fail the DAG through its failed leaf task
([Airflow 3.3.2 DAG-run status](https://airflow.apache.org/docs/apache-airflow/3.3.2/core-concepts/dag-run.html#dag-run-status)). There are
no cleanup/always-success leaf tasks to mask failure, callbacks, or alerts.
All nonzero command exits still fail an attempt (including 99); neither task
pushes command output through XCom. Task attempt logs preserve command output
and errors in Airflow's existing log volume.

A retry restarts the **entire unchanged command**:

- Ingestion repeats `--entity all`, beginning with games, then genres, platforms,
  companies and involved companies. It does not resume at the failed entity.
  Primary-key raw upserts remain duplicate-safe, but each started entity gets a
  new history UUID and archive attempt. Earlier committed raw rows, succeeded
  history and eligible per-entity cutoffs survive a later entity's failure.
  Each retry reads durable history and computes fresh windows; it does not reuse
  a frozen window from the prior command. Genres/platforms remain unfiltered.
  Failed/running history supplies no checkpoint; a durable success can survive
  a lost acknowledgment. There is no group transaction, rollback or stale-run
  cleanup. See [transactions](RAW_STORAGE.md#transactions) and
  [checkpoint failure semantics](WATERMARKS.md#failure-and-transaction-contract).
- dbt repeats the complete existing `dbt build`, including its tests. It does
  not rerun ingestion or select only failed models. Failed builds leave committed
  ingestion and completed dbt relations intact, so consumers can see a partial
  refresh until recovery. dbt targets are overwritten by the next attempt and
  logs append; export first-attempt evidence during the retry wait if needed.
  No automatic per-run artifact retention is implemented.

These Airflow retries are separate from `IGDBClient` request retries. The existing
client can attempt a request up to three times within one command, with its
existing backoff/authentication handling. Airflow sees only the final command
exit, then may start that whole command once more. HTTP retries stay in Python;
none are duplicated in DAG logic. dbt's existing profile connection retry setting
also remains unchanged and is distinct from a whole-build retry.

`schedule=None` and initial pausing remain unchanged. Scheduling, start-date,
catchup/backfill policy and broader end-to-end validation remain tasks 8.5–8.6.
Avoid overlapping manual/tools runs against the same schemas: executor parallelism
one limits simultaneous Airflow tasks, but is not a cross-command transaction or
lock across DAG runs and standalone tools.

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
