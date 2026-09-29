"""PostgreSQL table creation and idempotent loading for raw IGDB involved_companies."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from src.entities import INVOLVED_COMPANIES


def ensure_raw_involved_companies_table(connection: psycopg.Connection, schema_name: str) -> None:
    """Create the configured schema and raw_involved_companies table, then commit DDL."""

    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {};").format(sql.Identifier(schema_name))
        )
        cursor.execute(sql.SQL("""
            CREATE TABLE IF NOT EXISTS {}.{} (
                {} BIGINT PRIMARY KEY,
                payload JSONB NOT NULL,
                fetched_at TIMESTAMPTZ NOT NULL
            );
        """).format(
            sql.Identifier(schema_name), sql.Identifier(INVOLVED_COMPANIES.raw_table),
            sql.Identifier(INVOLVED_COMPANIES.raw_primary_key),
        ))
    connection.commit()


def upsert_raw_involved_companies(
    connection: psycopg.Connection,
    involved_companies: Iterable[dict],
    schema_name: str,
    fetched_at: datetime,
) -> int:
    """Commit involved-company upserts by IGDB ID and return processed input-row count.

    Retain references and roles unchanged in JSONB; the relationship ID is the key.
    Prepare all rows before writing. Empty input opens no cursor and commits
    nothing. Errors propagate to the caller's connection context for rollback.
    """

    rows = [
        (
            involved_company[INVOLVED_COMPANIES.source_primary_key],
            Jsonb(involved_company), fetched_at,
        )
        for involved_company in involved_companies
    ]
    if not rows:
        return 0

    statement = sql.SQL("""
        INSERT INTO {}.{} ({}, payload, fetched_at)
        VALUES (%s, %s, %s)
        ON CONFLICT ({}) DO UPDATE SET
            payload = EXCLUDED.payload,
            fetched_at = EXCLUDED.fetched_at;
    """).format(
        sql.Identifier(schema_name), sql.Identifier(INVOLVED_COMPANIES.raw_table),
        sql.Identifier(INVOLVED_COMPANIES.raw_primary_key), sql.Identifier(INVOLVED_COMPANIES.raw_primary_key),
    )
    with connection.cursor() as cursor:
        cursor.executemany(statement, rows)
    connection.commit()
    return len(rows)
