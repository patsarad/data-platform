"""Tests for Postgres ingestion helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from unittest.mock import MagicMock

import psycopg
import pytest

from src.storage import raw_games
from src.storage.raw_games import ensure_raw_games_table, upsert_raw_games
from src.utils.config import Settings


class FakeCursor:
    """Minimal cursor stub for capturing SQL statements."""

    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, Any]] = []
        self.executemany_calls: list[tuple[str, list[tuple[Any, ...]]]] = []

    def execute(self, sql: str, params: Any = None) -> None:
        """Record a single execute call."""

        self.execute_calls.append((sql, params))

    def executemany(self, sql: str, params: list[tuple[Any, ...]]) -> None:
        """Record an executemany call."""

        self.executemany_calls.append((sql, params))

    def __enter__(self) -> "FakeCursor":
        """Support context manager usage."""

        return self

    def __exit__(self, exc_type: Any, exc: Any, exc_tb: Any) -> None:
        """Support context manager usage."""

        return None


class FakeConnection:
    """Minimal connection stub for capturing transaction behavior."""

    def __init__(self) -> None:
        self.cursor_instance = FakeCursor()
        self.commit_calls = 0

    def cursor(self) -> FakeCursor:
        """Return a fake cursor instance."""

        return self.cursor_instance

    def commit(self) -> None:
        """Record commits."""

        self.commit_calls += 1


def test_ensure_raw_games_table_creates_schema_and_table() -> None:
    """Schema helper should create both schema and raw_games table."""

    connection = FakeConnection()

    ensure_raw_games_table(connection, "analytics")

    assert connection.commit_calls == 1
    executed_sql = "\n".join(call[0] for call in connection.cursor_instance.execute_calls)
    assert "CREATE SCHEMA IF NOT EXISTS analytics;" in executed_sql
    assert "CREATE TABLE IF NOT EXISTS analytics.raw_games" in executed_sql
    assert " ".join(executed_sql.split()) == (
        "CREATE SCHEMA IF NOT EXISTS analytics; "
        "CREATE TABLE IF NOT EXISTS analytics.raw_games ( "
        "igdb_id BIGINT PRIMARY KEY, name TEXT, slug TEXT, "
        "payload JSONB NOT NULL, fetched_at TIMESTAMPTZ NOT NULL );"
    )


def test_upsert_raw_games_executes_expected_insert() -> None:
    """Upsert helper should prepare rows for raw_games storage."""

    connection = FakeConnection()
    fetched_at = datetime(2026, 4, 18, tzinfo=timezone.utc)
    games = [{"id": 1, "name": "Halo", "slug": "halo", "updated_at": 1776470400}]

    inserted_count = upsert_raw_games(connection, games, "analytics", fetched_at)

    assert inserted_count == 1
    assert connection.commit_calls == 1
    sql, rows = connection.cursor_instance.executemany_calls[0]
    assert "INSERT INTO analytics.raw_games" in sql
    assert rows[0][0] == 1
    assert rows[0][1] == "Halo"
    assert rows[0][2] == "halo"
    assert isinstance(rows[0][3], psycopg.types.json.Jsonb)
    assert rows[0][3].obj == games[0]
    assert rows[0][4] == fetched_at
    assert " ".join(sql.split()) == (
        "INSERT INTO analytics.raw_games ( igdb_id, name, slug, payload, fetched_at ) "
        "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (igdb_id) DO UPDATE SET "
        "name = EXCLUDED.name, slug = EXCLUDED.slug, payload = EXCLUDED.payload, "
        "fetched_at = EXCLUDED.fetched_at;"
    )


def test_create_connection_passes_database_settings(monkeypatch) -> None:
    """Connect with configured credentials and retain driver transaction defaults."""

    settings = Settings(
        postgres_host="db.test", postgres_port=6543, postgres_db="test_db",
        postgres_user="test_user", postgres_password="test_password",
    )
    connect = MagicMock()
    monkeypatch.setattr(raw_games, "get_settings", lambda: settings)
    monkeypatch.setattr(raw_games.psycopg, "connect", connect)

    assert raw_games.create_connection() is connect.return_value
    connect.assert_called_once_with(
        host="db.test", port=6543, dbname="test_db",
        user="test_user", password="test_password",
    )


def test_create_connection_propagates_database_failure(monkeypatch) -> None:
    """Connection failures remain visible to callers."""

    error = psycopg.OperationalError("Connection failed")
    monkeypatch.setattr(raw_games, "get_settings", Settings)
    monkeypatch.setattr(raw_games.psycopg, "connect", MagicMock(side_effect=error))

    with pytest.raises(psycopg.OperationalError) as raised:
        raw_games.create_connection()

    assert raised.value is error


def test_upsert_raw_games_preserves_iterables_and_optional_fields() -> None:
    """Keep full payloads, row order, and one timestamp for iterable input."""

    connection = FakeConnection()
    fetched_at = datetime(2026, 9, 25, tzinfo=timezone.utc)
    games = [{"id": 2, "rating": 95, "nested": {"values": [1, 2]}}, {"id": 1}]

    assert upsert_raw_games(connection, iter(games), "custom_raw", fetched_at) == 2

    sql, rows = connection.cursor_instance.executemany_calls[0]
    assert "INSERT INTO custom_raw.raw_games" in sql
    assert [(row[0], row[1], row[2], row[4]) for row in rows] == [
        (2, None, None, fetched_at), (1, None, None, fetched_at),
    ]
    assert [row[3].obj for row in rows] == games
    assert connection.commit_calls == 1


def test_upsert_raw_games_empty_input_does_not_open_cursor_or_commit() -> None:
    """An empty iterable remains a no-op."""

    connection = MagicMock()

    assert upsert_raw_games(connection, iter([]), "analytics", datetime.now(timezone.utc)) == 0
    connection.cursor.assert_not_called()
    connection.commit.assert_not_called()


def test_upsert_raw_games_missing_id_fails_before_writing() -> None:
    """Prepare all rows before writing and continue to require the source ID."""

    connection = MagicMock()

    with pytest.raises(KeyError, match="id"):
        upsert_raw_games(connection, [{"id": 1}, {}], "analytics", datetime.now(timezone.utc))

    connection.cursor.assert_not_called()
    connection.commit.assert_not_called()


@pytest.mark.parametrize("operation", ["schema", "table", "upsert"])
def test_database_write_failure_propagates_without_commit(operation: str) -> None:
    """Leave rollback to the caller's connection context after failed writes."""

    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    error = psycopg.DatabaseError("Write failed")
    if operation == "upsert":
        cursor.executemany.side_effect = error
    else:
        cursor.execute.side_effect = [error] if operation == "schema" else [None, error]

    with pytest.raises(psycopg.DatabaseError) as raised:
        if operation == "upsert":
            upsert_raw_games(connection, [{"id": 1}], "analytics", datetime.now(timezone.utc))
        else:
            ensure_raw_games_table(connection, "custom_raw")

    assert raised.value is error
    connection.commit.assert_not_called()
    connection.rollback.assert_not_called()
    assert connection.cursor.return_value.__exit__.call_args.args[1] is error
