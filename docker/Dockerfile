FROM python:3.11.16-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false \
    DBT_PROFILES_DIR=/app/dbt \
    DBT_PROJECT_DIR=/app/dbt \
    DBT_TARGET_PATH=/tmp/dbt/target \
    DBT_LOG_PATH=/tmp/dbt/logs

WORKDIR /app

# Cache dependency installation independently of source changes. No build secrets.
COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip check

RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/data/raw /tmp/dbt \
    && chown app:app /app/data/raw /tmp/dbt

COPY src/ ./src/
COPY dbt/ ./dbt/
COPY tests/ ./tests/

USER app

# A plain command override supports Python, dbt and pytest without a wrapper.
CMD ["python", "-m", "src.ingestion.run_ingestion", "--help"]
