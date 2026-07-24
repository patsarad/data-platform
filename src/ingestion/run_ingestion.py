"""Command-line entrypoint for ingesting raw IGDB games data."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import psycopg

from src.ingestion.client import create_igdb_client
from src.ingestion.fetch_games import fetch_games_batches, save_games_to_jsonl
from src.utils.config import get_settings
from src.utils.logger import get_logger


DEFAULT_OUTPUT_DIR = Path("data/raw")
DEFAULT_OUTPUT_FILENAME_TEMPLATE = "raw_games_{timestamp}.jsonl"


def build_output_path(output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    """Build a timestamped output path for raw game payloads."""

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return output_dir / DEFAULT_OUTPUT_FILENAME_TEMPLATE.format(timestamp=timestamp)


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
        CREATE TABLE IF NOT EXISTS {schema_name}.raw_games (
            igdb_id BIGINT PRIMARY KEY,
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
            game["id"],
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
        INSERT INTO {schema_name}.raw_games (
            igdb_id,
            name,
            slug,
            payload,
            fetched_at
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (igdb_id) DO UPDATE SET
            name = EXCLUDED.name,
            slug = EXCLUDED.slug,
            payload = EXCLUDED.payload,
            fetched_at = EXCLUDED.fetched_at;
    """

    with connection.cursor() as cursor:
        cursor.executemany(insert_sql, rows)

    connection.commit()
    return len(rows)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the ingestion command."""

    parser = argparse.ArgumentParser(description="Ingest IGDB games into raw storage.")
    parser.add_argument("--batch-size", type=int, default=500, help="Games fetched per API call.")
    parser.add_argument(
        "--max-batches",
        type=int,
        default=None,
        help="Maximum number of batches to fetch. Defaults to all available batches.",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help="Optional path for the raw JSONL export. Defaults to data/raw/raw_games_<timestamp>.jsonl.",
    )
    return parser.parse_args()


def main() -> None:
    """Fetch raw IGDB games, save them locally, and load them into Postgres."""

    args = parse_args()
    logger = get_logger(__name__)
    settings = get_settings()
    output_path = args.output_path or build_output_path()

    logger.info(
        "Starting IGDB games ingestion with batch_size=%s, max_batches=%s.",
        args.batch_size,
        args.max_batches,
    )

    client = create_igdb_client()
    games = fetch_games_batches(
        client,
        batch_size=args.batch_size,
        max_batches=args.max_batches,
    )

    save_games_to_jsonl(games, output_path)

    fetched_at = datetime.now(timezone.utc)
    with create_connection() as connection:
        ensure_raw_games_table(connection, settings.postgres_schema)
        inserted_count = upsert_raw_games(
            connection,
            games,
            settings.postgres_schema,
            fetched_at,
        )

    logger.info(
        "Finished ingestion. Saved %s games locally and loaded %s rows into %s.raw_games.",
        len(games),
        inserted_count,
        settings.postgres_schema,
    )


if __name__ == "__main__":
    main()
