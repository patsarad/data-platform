"""Offline DAG wiring checks; real Airflow discovery/execution runs in its image."""

from datetime import timedelta
from pathlib import Path
import runpy
import sys
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]


def test_manual_dag_builds_only_after_the_existing_ingestion_cli(monkeypatch):
    """Capture the public constructor contract without installing Airflow on host."""
    dags, tasks, edges = [], [], []

    class DAG:
        def __init__(self, **kwargs):
            dags.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class BashOperator:
        def __init__(self, **kwargs):
            self.task_id = kwargs["task_id"]
            tasks.append(kwargs)

        def __rshift__(self, other):
            edges.append((self.task_id, other.task_id))
            return other

    sdk = ModuleType("airflow.sdk")
    sdk.DAG = DAG
    bash = ModuleType("airflow.providers.standard.operators.bash")
    bash.BashOperator = BashOperator
    monkeypatch.setitem(sys.modules, "airflow.sdk", sdk)
    monkeypatch.setitem(sys.modules, "airflow.providers.standard.operators.bash", bash)
    runpy.run_path(str(ROOT / "dags/igdb_ingestion.py"))
    assert dags == [{
        "dag_id": "igdb_ingestion", "schedule": None, "is_paused_upon_creation": True,
        "default_args": {
            "retries": 1, "retry_delay": timedelta(minutes=1),
            "retry_exponential_backoff": False, "trigger_rule": "all_success",
        },
    }]
    assert tasks == [{
        "task_id": "ingest_all",
        "bash_command": "exec /opt/airflow/app-venv/bin/python -m src.ingestion.run_ingestion --entity all",
        "cwd": "/opt/airflow/app", "skip_on_exit_code": None, "do_xcom_push": False,
    }, {
        "task_id": "dbt_build",
        "bash_command": "exec /opt/airflow/app-venv/bin/dbt build --project-dir /opt/airflow/app/dbt --profiles-dir /opt/airflow/app/dbt",
        "cwd": "/opt/airflow/app", "skip_on_exit_code": None, "do_xcom_push": False,
    }]
    assert edges == [("ingest_all", "dbt_build")]
    assert {p.name for p in (ROOT / "dags").glob("*.py")} == {"igdb_ingestion.py"}


def test_application_dependencies_remain_a_subset_of_standalone_requirements():
    """Prevent drift or accidental Airflow/pytest installation into the app venv."""
    requirements = {
        line for line in (ROOT / "docker/airflow/requirements-ingestion.txt").read_text().splitlines()
        if line and not line.startswith("#")
    }
    assert requirements == {"dbt-postgres>=1.8,<2.0", "psycopg[binary]>=3.1,<4.0", "python-dotenv>=1.0,<2.0", "requests>=2.31,<3.0"}
    assert requirements <= set((ROOT / "requirements.txt").read_text().splitlines())
