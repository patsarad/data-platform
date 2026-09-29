"""PostgreSQL connections, table creation, and loading for raw IGDB games."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

import psycopg

from src.entities import GAMES
from src.utils.config import get_settings


def create_connection() -> psycopg.Connection:
    """Create a PostgreSQL connection using environment-backed settings."""

    settings = get_settings()
    return psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
    )


def ensure_raw_games_table(connection: psycopg.Connection, schema_name: str) -> None:
    """Create the raw schema and raw_games table if they do not exist."""

    create_schema_sql = f"CREATE SCHEMA IF NOT EXISTS {schema_name};"
    create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {schema_name}.{GAMES.raw_table} (
            {GAMES.raw_primary_key} BIGINT PRIMARY KEY,
            name TEXT,
            slug TEXT,
            payload JSONB NOT NULL,
            fetched_at TIMESTAMPTZ NOT NULL
        );
    """

    with connection.cursor() as cursor:
        cursor.execute(create_schema_sql)
        cursor.execute(create_table_sql)

    connection.commit()


def upsert_raw_games(
    connection: psycopg.Connection,
    games: Iterable[dict],
    schema_name: str,
    fetched_at: datetime,
) -> int:
    """Upsert raw games into PostgreSQL."""

    rows = [
        (
            game[GAMES.source_primary_key],
            game.get("name"),
            game.get("slug"),
            psycopg.types.json.Jsonb(game),
            fetched_at,
        )
        for game in games
    ]

    if not rows:
        return 0

    insert_sql = f"""
        INSERT INTO {schema_name}.{GAMES.raw_table} (
            {GAMES.raw_primary_key},
            name,
            slug,
            payload,
            fetched_at
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT ({GAMES.raw_primary_key}) DO UPDATE SET
            name = EXCLUDED.name,
            slug = EXCLUDED.slug,
            payload = EXCLUDED.payload,
            fetched_at = EXCLUDED.fetched_at;
    """

    with connection.cursor() as cursor:
        cursor.executemany(insert_sql, rows)

    connection.commit()
    return len(rows)
