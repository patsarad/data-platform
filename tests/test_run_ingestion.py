"""Tests for Postgres ingestion helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.ingestion.run_ingestion import ensure_raw_games_table, upsert_raw_games


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


def test_upsert_raw_games_executes_expected_insert() -> None:
    """Upsert helper should prepare rows for raw_games storage."""

    connection = FakeConnection()
    fetched_at = datetime(2026, 4, 18, tzinfo=timezone.utc)
    games = [{"id": 1, "name": "Halo", "slug": "halo"}]

    inserted_count = upsert_raw_games(connection, games, "analytics", fetched_at)

    assert inserted_count == 1
    assert connection.commit_calls == 1
    sql, rows = connection.cursor_instance.executemany_calls[0]
    assert "INSERT INTO analytics.raw_games" in sql
    assert rows[0][0] == 1
    assert rows[0][1] == "Halo"
    assert rows[0][2] == "halo"
    assert rows[0][4] == fetched_at
