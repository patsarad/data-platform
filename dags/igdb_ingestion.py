"""Manually ingest all entities, then build the existing dbt project."""

from datetime import timedelta

from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator


with DAG(
    dag_id="igdb_ingestion",
    schedule=None,
    is_paused_upon_creation=True,
    # Retry the entire command once; committed ingestion/models are not rolled back.
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=1),
        "retry_exponential_backoff": False,
        "trigger_rule": "all_success",
    },
) as dag:
    ingest_all = BashOperator(
        task_id="ingest_all",
        bash_command="exec /opt/airflow/app-venv/bin/python -m src.ingestion.run_ingestion --entity all",
        cwd="/opt/airflow/app",
        skip_on_exit_code=None,
        do_xcom_push=False,
    )
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=(
            "exec /opt/airflow/app-venv/bin/dbt build"
            " --project-dir /opt/airflow/app/dbt --profiles-dir /opt/airflow/app/dbt"
        ),
        cwd="/opt/airflow/app",
        skip_on_exit_code=None,
        do_xcom_push=False,
    )

    ingest_all >> dbt_build
