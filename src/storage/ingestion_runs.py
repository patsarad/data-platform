"""Ingestion lifecycle records and persisted progress, separate from raw loads."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import psycopg
from psycopg import sql


def ensure_ingestion_runs_table(connection: psycopg.Connection, schema_name: str) -> None:
    """Create and commit the run table."""

    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {};").format(sql.Identifier(schema_name))
        )
        cursor.execute(sql.SQL("""
            CREATE TABLE IF NOT EXISTS {}.ingestion_runs (
                run_id UUID PRIMARY KEY,
                entity TEXT NOT NULL,
                started_at TIMESTAMPTZ NOT NULL,
                completed_at TIMESTAMPTZ,
                status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
                records_fetched INTEGER NOT NULL DEFAULT 0 CHECK (records_fetched >= 0),
                records_loaded INTEGER NOT NULL DEFAULT 0 CHECK (records_loaded >= 0),
                source_watermark_start TIMESTAMPTZ,
                source_watermark_end TIMESTAMPTZ,
                error_message TEXT
            );
        """).format(sql.Identifier(schema_name)))
    connection.commit()


def start_ingestion_run(
    connection: psycopg.Connection, schema_name: str, entity: str,
    *, started_at: datetime | None = None, source_watermark_start: datetime | None = None,
) -> UUID:
    """Commit a running record with its actual inclusive selection bound."""

    run_id = uuid4()
    with connection.cursor() as cursor:
        if source_watermark_start is None:
            cursor.execute(
                sql.SQL("""
                    INSERT INTO {}.ingestion_runs (run_id, entity, started_at, status)
                    VALUES (%s, %s, %s, 'running');
                """).format(sql.Identifier(schema_name)),
                (run_id, entity, started_at or datetime.now(timezone.utc)),
            )
        else:
            cursor.execute(
                sql.SQL("""
                    INSERT INTO {}.ingestion_runs
                        (run_id, entity, started_at, status, source_watermark_start)
                    VALUES (%s, %s, %s, 'running', %s);
                """).format(sql.Identifier(schema_name)),
                (run_id, entity, started_at or datetime.now(timezone.utc), source_watermark_start),
            )
    connection.commit()
    return run_id


def get_source_watermark(
    connection: psycopg.Connection, schema_name: str, entity: str
) -> datetime | None:
    """Return the greatest successful non-NULL end for this schema/entity.

    The supplied connection selects the database and owns transaction visibility;
    callers should read durable history without pending metadata writes. Completion
    order and source_watermark_start never determine progress. No eligible end,
    including legacy NULL-only history, returns None. All lookup errors propagate.
    Only the cursor is managed here: no DDL, commit, rollback, or connection close.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("""
                SELECT MAX(source_watermark_end)
                FROM {}.ingestion_runs
                WHERE entity = %s AND status = 'succeeded'
                    AND source_watermark_end IS NOT NULL;
            """).format(sql.Identifier(schema_name)),
            (entity,),
        )
        # An aggregate without GROUP BY returns one row, even for empty history.
        (watermark,) = cursor.fetchone()
    return watermark


def succeed_ingestion_run(
    connection: psycopg.Connection,
    schema_name: str,
    run_id: UUID,
    records_fetched: int,
    records_loaded: int,
    *, source_watermark_end: datetime | None = None,
) -> None:
    """Commit success only after the caller has completed its raw-load context."""

    _finish_ingestion_run(
        connection, schema_name, run_id, "succeeded", records_fetched, records_loaded, None,
        source_watermark_end=source_watermark_end,
    )


def fail_ingestion_run(
    connection: psycopg.Connection,
    schema_name: str,
    run_id: UUID,
    records_fetched: int,
    records_loaded: int,
    error_message: str,
) -> None:
    """Commit failure with a caller-supplied safe summary, never raw exception text."""

    _finish_ingestion_run(
        connection, schema_name, run_id, "failed", records_fetched, records_loaded, error_message
    )


def _finish_ingestion_run(
    connection: psycopg.Connection,
    schema_name: str,
    run_id: UUID,
    status: str,
    records_fetched: int,
    records_loaded: int,
    error_message: str | None,
    *, source_watermark_end: datetime | None = None,
) -> None:
    """Finish a running record once; leave rollback on any error to the caller."""

    with connection.cursor() as cursor:
        if source_watermark_end is None:
            cursor.execute(
                sql.SQL("""
                    UPDATE {}.ingestion_runs
                    SET completed_at = %s, status = %s, records_fetched = %s,
                        records_loaded = %s, error_message = %s
                    WHERE run_id = %s AND status = 'running';
                """).format(sql.Identifier(schema_name)),
                (datetime.now(timezone.utc), status, records_fetched,
                 records_loaded, error_message, run_id),
            )
        else:
            cursor.execute(
                sql.SQL("""
                    UPDATE {}.ingestion_runs
                    SET completed_at = %s, status = %s, records_fetched = %s,
                        records_loaded = %s, error_message = %s, source_watermark_end = %s
                    WHERE run_id = %s AND status = 'running';
                """).format(sql.Identifier(schema_name)),
                (datetime.now(timezone.utc), status, records_fetched,
                 records_loaded, error_message, source_watermark_end, run_id),
            )
        if cursor.rowcount != 1:
            raise ValueError("Ingestion run is missing or already completed.")
    connection.commit()
