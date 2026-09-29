"""Genres SQL and transaction boundaries without a live PostgreSQL service."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import psycopg
import pytest
from psycopg.types.json import Jsonb

from src.storage.raw_genres import ensure_raw_genres_table, upsert_raw_genres


def test_ddl_preserves_raw_shape_and_quotes_schema() -> None:
    """Use the raw ID/payload contract in the configured schema."""

    connection = MagicMock()
    ensure_raw_genres_table(connection, 'custom"schema')
    calls = connection.cursor.return_value.__enter__.return_value.execute.call_args_list
    assert calls[0].args[0].as_string() == 'CREATE SCHEMA IF NOT EXISTS "custom""schema";'
    assert " ".join(calls[1].args[0].as_string().split()) == (
        'CREATE TABLE IF NOT EXISTS "custom""schema"."raw_genres" ( '
        '"igdb_id" BIGINT PRIMARY KEY, name TEXT, slug TEXT, '
        'payload JSONB NOT NULL, fetched_at TIMESTAMPTZ NOT NULL );'
    )
    connection.commit.assert_called_once_with()


def test_upsert_preserves_payloads_and_updates_all_nonkey_columns() -> None:
    """Prepare ordered iterable rows with optional attributes and complete JSONB."""

    connection = MagicMock()
    timestamp = datetime(2026, 9, 25, tzinfo=timezone.utc)
    records = [{"id": 5, "name": "Shooter", "slug": "shooter", "updated_at": 123}, {"id": 5}]
    assert upsert_raw_genres(connection, iter(records), 'custom"schema', timestamp) == 2
    statement, rows = connection.cursor.return_value.__enter__.return_value.executemany.call_args.args
    assert " ".join(statement.as_string().split()) == (
        'INSERT INTO "custom""schema"."raw_genres" ("igdb_id", name, slug, payload, fetched_at) '
        'VALUES (%s, %s, %s, %s, %s) ON CONFLICT ("igdb_id") DO UPDATE SET '
        'name = EXCLUDED.name, slug = EXCLUDED.slug, payload = EXCLUDED.payload, '
        'fetched_at = EXCLUDED.fetched_at;'
    )
    assert [row[:3] for row in rows] == [(5, "Shooter", "shooter"), (5, None, None)]
    assert all(isinstance(row[3], Jsonb) for row in rows)
    assert [row[3].obj for row in rows] == records
    assert all(row[4] == timestamp for row in rows)
    connection.commit.assert_called_once_with()


def test_empty_upsert_has_no_cursor_or_commit() -> None:
    """Empty input is a no-op at the storage helper boundary."""

    connection = MagicMock()
    assert upsert_raw_genres(connection, iter([]), "analytics", datetime.now(timezone.utc)) == 0
    connection.cursor.assert_not_called()
    connection.commit.assert_not_called()


def test_missing_id_prevents_all_writes() -> None:
    """Reject a missing key in a later row before executing any upsert."""

    connection = MagicMock()
    with pytest.raises(KeyError, match="id"):
        upsert_raw_genres(connection, [{"id": 1}, {}], "analytics", datetime.now(timezone.utc))
    connection.cursor.assert_not_called()
    connection.commit.assert_not_called()


@pytest.mark.parametrize("operation", ["schema", "table", "upsert", "ddl_commit", "load_commit"])
def test_database_failure_propagates_for_context_rollback(operation) -> None:
    """Failed writes do not commit; failed commits stay visible to the caller."""

    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    error = psycopg.DatabaseError("Write failed")
    if operation.endswith("commit"):
        connection.commit.side_effect = error
    elif operation == "upsert":
        cursor.executemany.side_effect = error
    else:
        cursor.execute.side_effect = [None, error] if operation == "table" else error
    with pytest.raises(psycopg.DatabaseError) as raised:
        if operation in {"upsert", "load_commit"}:
            upsert_raw_genres(connection, [{"id": 1}], "analytics", datetime.now(timezone.utc))
        else:
            ensure_raw_genres_table(connection, "analytics")
    assert raised.value is error
    if not operation.endswith("commit"):
        connection.commit.assert_not_called()
    connection.rollback.assert_not_called()
