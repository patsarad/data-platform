"""PostgreSQL table creation and idempotent loading for raw IGDB companies."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from src.entities import COMPANIES


def ensure_raw_companies_table(connection: psycopg.Connection, schema_name: str) -> None:
    """Create the configured schema and raw_companies table, then commit DDL."""

    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {};").format(sql.Identifier(schema_name))
        )
        cursor.execute(sql.SQL("""
            CREATE TABLE IF NOT EXISTS {}.{} (
                {} BIGINT PRIMARY KEY,
                name TEXT,
                slug TEXT,
                payload JSONB NOT NULL,
                fetched_at TIMESTAMPTZ NOT NULL
            );
        """).format(
            sql.Identifier(schema_name), sql.Identifier(COMPANIES.raw_table),
            sql.Identifier(COMPANIES.raw_primary_key),
        ))
    connection.commit()


def upsert_raw_companies(
    connection: psycopg.Connection,
    companies: Iterable[dict],
    schema_name: str,
    fetched_at: datetime,
) -> int:
    """Commit company upserts by IGDB ID and return processed input-row count.

    Prepare all rows before writing. Empty input opens no cursor and commits
    nothing. Errors propagate to the caller's connection context for rollback.
    """

    rows = [
        (
            company[COMPANIES.source_primary_key], company.get("name"), company.get("slug"),
            Jsonb(company), fetched_at,
        )
        for company in companies
    ]
    if not rows:
        return 0

    statement = sql.SQL("""
        INSERT INTO {}.{} ({}, name, slug, payload, fetched_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT ({}) DO UPDATE SET
            name = EXCLUDED.name,
            slug = EXCLUDED.slug,
            payload = EXCLUDED.payload,
            fetched_at = EXCLUDED.fetched_at;
    """).format(
        sql.Identifier(schema_name), sql.Identifier(COMPANIES.raw_table),
        sql.Identifier(COMPANIES.raw_primary_key), sql.Identifier(COMPANIES.raw_primary_key),
    )
    with connection.cursor() as cursor:
        cursor.executemany(statement, rows)
    connection.commit()
    return len(rows)
