FROM apache/airflow:3.3.2-python3.11

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Named volumes inherit non-root ownership without host mounts or a root init.
USER airflow
RUN mkdir -p /opt/airflow/config /opt/airflow/logs /opt/airflow/dags /opt/airflow/app/data/raw /opt/airflow/dbt-artifacts \
    && python -m venv /opt/airflow/app-venv
COPY --chown=airflow:root docker/airflow/requirements-ingestion.txt /opt/airflow/local/requirements-ingestion.txt
RUN PIP_USER=false /opt/airflow/app-venv/bin/python -m pip install --no-cache-dir \
        -r /opt/airflow/local/requirements-ingestion.txt \
    && /opt/airflow/app-venv/bin/python -m pip check
COPY --chown=airflow:root docker/airflow/bootstrap.py /opt/airflow/local/bootstrap.py
COPY --chown=airflow:root src/__init__.py src/entities.py /opt/airflow/app/src/
COPY --chown=airflow:root src/ingestion/ /opt/airflow/app/src/ingestion/
COPY --chown=airflow:root src/storage/ /opt/airflow/app/src/storage/
COPY --chown=airflow:root src/utils/ /opt/airflow/app/src/utils/
COPY --chown=airflow:root dbt/ /opt/airflow/app/dbt/
COPY --chown=airflow:root dags/ /opt/airflow/dags/
