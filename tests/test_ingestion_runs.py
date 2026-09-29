"""Run metadata SQL, transitions, and transaction tests without PostgreSQL."""

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import UUID

import psycopg
import pytest

from src.storage import ingestion_runs


@pytest.fixture
def connection():
    """Return a connection whose cursor reports one affected row."""

    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value.rowcount = 1
    return connection


def test_ensure_ingestion_runs_table(connection) -> None:
    """Create the table with constrained states/counts and unused nullable watermarks."""

    ingestion_runs.ensure_ingestion_runs_table(connection, 'custom"schema')

    calls = connection.cursor.return_value.__enter__.return_value.execute.call_args_list
    assert calls[0].args[0].as_string() == 'CREATE SCHEMA IF NOT EXISTS "custom""schema";'
    ddl = " ".join(calls[1].args[0].as_string().split())
    assert ddl == (
        'CREATE TABLE IF NOT EXISTS "custom""schema".ingestion_runs ( '
        "run_id UUID PRIMARY KEY, entity TEXT NOT NULL, started_at TIMESTAMPTZ NOT NULL, "
        "completed_at TIMESTAMPTZ, status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')), "
        "records_fetched INTEGER NOT NULL DEFAULT 0 CHECK (records_fetched >= 0), "
        "records_loaded INTEGER NOT NULL DEFAULT 0 CHECK (records_loaded >= 0), "
        "source_watermark_start TIMESTAMPTZ, source_watermark_end TIMESTAMPTZ, error_message TEXT );"
    )
    connection.commit.assert_called_once_with()


def test_start_creates_unique_committed_runs(connection) -> None:
    """Each invocation persists a new running record; values are SQL parameters."""

    before = datetime.now(timezone.utc)
    first = ingestion_runs.start_ingestion_run(connection, "analytics", "games'quoted")
    second = ingestion_runs.start_ingestion_run(connection, "analytics", "games")
    after = datetime.now(timezone.utc)

    assert isinstance(first, UUID)
    assert first != second
    calls = connection.cursor.return_value.__enter__.return_value.execute.call_args_list
    for call, run_id, entity in zip(calls, [first, second], ["games'quoted", "games"]):
        statement, (stored_id, stored_entity, started_at) = call.args
        assert " ".join(statement.as_string().split()) == (
            'INSERT INTO "analytics".ingestion_runs (run_id, entity, started_at, status) '
            "VALUES (%s, %s, %s, 'running');"
        )
        assert (stored_id, stored_entity) == (run_id, entity)
        assert before <= started_at <= after
        assert started_at.tzinfo == timezone.utc
    assert connection.commit.call_count == 2


def test_start_persists_explicit_inclusive_lower_bound(connection) -> None:
    """The running row records the actual overlap bound, not the prior end."""

    start = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
    lower = datetime(2026, 9, 26, 10, tzinfo=timezone.utc)
    run_id = ingestion_runs.start_ingestion_run(
        connection, "analytics", "games", started_at=start, source_watermark_start=lower,
    )
    statement, params = connection.cursor.return_value.__enter__.return_value.execute.call_args.args
    assert "source_watermark_start" in statement.as_string()
    assert params == (run_id, "games", start, lower)
    assert "source_watermark_end" not in statement.as_string()
    connection.commit.assert_called_once_with()


def test_eligible_success_commits_end_with_guarded_status(connection) -> None:
    """End and terminal success share one SQL update and commit call."""

    cutoff = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
    run_id = UUID(int=45)
    ingestion_runs.succeed_ingestion_run(
        connection, "analytics", run_id, 3, 3, source_watermark_end=cutoff,
    )
    statement, params = connection.cursor.return_value.__enter__.return_value.execute.call_args.args
    assert "status = %s" in statement.as_string()
    assert "source_watermark_end = %s" in statement.as_string()
    assert "AND status = 'running'" in statement.as_string()
    assert params[1:] == ("succeeded", 3, 3, None, cutoff, run_id)
    connection.commit.assert_called_once_with()

    connection.reset_mock()
    connection.cursor.return_value.__enter__.return_value.rowcount = 0
    with pytest.raises(ValueError, match="already completed"):
        ingestion_runs.succeed_ingestion_run(
            connection, "analytics", run_id, 3, 3, source_watermark_end=cutoff,
        )
    connection.commit.assert_not_called()


@pytest.mark.parametrize("status", ["succeeded", "failed"])
@pytest.mark.parametrize(("fetched", "loaded"), [(0, 0), (3, 3), (3, 0)])
def test_finish_records_counts_and_time(connection, status, fetched, loaded) -> None:
    """Completion targets only the running UUID and never sets watermarks."""

    run_id = UUID(int=1)
    message = "raw load failed." if status == "failed" else None
    before = datetime.now(timezone.utc)
    if status == "failed":
        ingestion_runs.fail_ingestion_run(connection, "analytics", run_id, fetched, loaded, message)
    else:
        ingestion_runs.succeed_ingestion_run(connection, "analytics", run_id, fetched, loaded)
    after = datetime.now(timezone.utc)

    statement, params = connection.cursor.return_value.__enter__.return_value.execute.call_args.args
    assert " ".join(statement.as_string().split()) == (
        'UPDATE "analytics".ingestion_runs SET completed_at = %s, status = %s, records_fetched = %s, '
        "records_loaded = %s, error_message = %s WHERE run_id = %s AND status = 'running';"
    )
    assert params[1:] == (status, fetched, loaded, message, run_id)
    assert before <= params[0] <= after
    assert params[0].tzinfo == timezone.utc
    connection.commit.assert_called_once_with()


@pytest.mark.parametrize("status", ["succeeded", "failed"])
def test_finish_rejects_missing_or_completed_run(connection, status) -> None:
    """Never silently report success when the requested transition did not occur."""

    connection.cursor.return_value.__enter__.return_value.rowcount = 0
    with pytest.raises(ValueError, match="missing or already completed"):
        if status == "failed":
            ingestion_runs.fail_ingestion_run(connection, "analytics", UUID(int=1), 0, 0, "fetch failed.")
        else:
            ingestion_runs.succeed_ingestion_run(connection, "analytics", UUID(int=1), 0, 0)

    connection.commit.assert_not_called()


@pytest.mark.parametrize("operation", ["schema", "table", "start", "success", "failure"])
@pytest.mark.parametrize("failure_point", ["execute", "commit"])
def test_database_errors_propagate_for_caller_rollback(connection, operation, failure_point) -> None:
    """Helpers neither swallow database errors nor reuse a failed transaction."""

    error = psycopg.DatabaseError("Database failed")
    cursor = connection.cursor.return_value.__enter__.return_value
    if failure_point == "commit":
        connection.commit.side_effect = error
    else:
        cursor.execute.side_effect = [None, error] if operation == "table" else error

    with pytest.raises(psycopg.DatabaseError) as raised:
        if operation in {"schema", "table"}:
            ingestion_runs.ensure_ingestion_runs_table(connection, "analytics")
        elif operation == "start":
            ingestion_runs.start_ingestion_run(connection, "analytics", "games")
        elif operation == "success":
            ingestion_runs.succeed_ingestion_run(connection, "analytics", UUID(int=1), 1, 1)
        else:
            ingestion_runs.fail_ingestion_run(connection, "analytics", UUID(int=1), 1, 0, "load failed.")

    assert raised.value is error
    if failure_point == "execute":
        connection.commit.assert_not_called()
    connection.rollback.assert_not_called()


def assert_lookup_leaves_connection_owned_by_caller(connection) -> None:
    """A SELECT must not manage transactions or the supplied connection lifecycle."""

    connection.commit.assert_not_called()
    connection.rollback.assert_not_called()
    connection.close.assert_not_called()
    connection.__enter__.assert_not_called()
    connection.__exit__.assert_not_called()
    connection.transaction.assert_not_called()


OLDER_END = datetime(2026, 9, 24, tzinfo=timezone.utc)
GREATEST_END = datetime(2026, 9, 25, tzinfo=timezone.utc)
LATER_TIME = datetime(2026, 9, 26, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("history", "expected"),
    [
        ([("succeeded", GREATEST_END, GREATEST_END)], GREATEST_END),
        ([], None),
        ([("succeeded", None, OLDER_END), ("succeeded", None, LATER_TIME)], None),
        ([("failed", LATER_TIME, LATER_TIME), ("running", LATER_TIME, None)], None),
        ([("succeeded", GREATEST_END, GREATEST_END),
          ("failed", LATER_TIME, LATER_TIME), ("running", LATER_TIME, None),
          ("succeeded", None, LATER_TIME)], GREATEST_END),
        ([("succeeded", GREATEST_END, GREATEST_END),
          ("succeeded", OLDER_END, LATER_TIME)], GREATEST_END),
        ([("succeeded", None, LATER_TIME),
          ("succeeded", OLDER_END, LATER_TIME),
          ("succeeded", GREATEST_END, GREATEST_END)], GREATEST_END),
    ],
    ids=["eligible", "empty", "legacy-null-only", "failed-running-only",
         "exclude-failed-running-null", "later-success-has-older-end", "reordered-history"],
)
def test_get_source_watermark_history(connection, history, expected) -> None:
    """Assert the aggregate SQL contract; model its result without executing SQL."""

    cursor = connection.cursor.return_value.__enter__.return_value

    def execute(statement, params):
        # Exact SQL guards the predicates/MAX independently of the result fake.
        assert " ".join(statement.as_string().split()) == (
            'SELECT MAX(source_watermark_end) FROM "analytics".ingestion_runs '
            "WHERE entity = %s AND status = 'succeeded' "
            "AND source_watermark_end IS NOT NULL;"
        )
        assert params == ("games",)
        ends = [end for status, end, completed_at in history
                if status == "succeeded" and end is not None]
        cursor.fetchone.return_value = (max(ends, default=None),)

    cursor.execute.side_effect = execute

    assert ingestion_runs.get_source_watermark(connection, "analytics", "games") == expected

    connection.cursor.assert_called_once_with()
    cursor.execute.assert_called_once()
    cursor.fetchone.assert_called_once_with()
    cursor.executemany.assert_not_called()
    connection.cursor.return_value.__exit__.assert_called_once_with(None, None, None)
    assert_lookup_leaves_connection_owned_by_caller(connection)


@pytest.mark.parametrize("schema", ["analytics", 'custom"schema; --'])
@pytest.mark.parametrize("entity", ["games", "companies", "involved_companies", "games' OR true --"])
def test_get_source_watermark_scoping_and_safe_sql(connection, schema, entity) -> None:
    """Scope exactly to the supplied schema/entity, including hostile-looking names."""

    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (GREATEST_END,)

    assert ingestion_runs.get_source_watermark(connection, schema, entity) is GREATEST_END

    cursor.execute.assert_called_once()
    statement, params = cursor.execute.call_args.args
    quoted_schema = '"' + schema.replace('"', '""') + '"'
    assert " ".join(statement.as_string().split()) == (
        f'SELECT MAX(source_watermark_end) FROM {quoted_schema}.ingestion_runs '
        "WHERE entity = %s AND status = 'succeeded' "
        "AND source_watermark_end IS NOT NULL;"
    )
    assert params == (entity,)
    assert_lookup_leaves_connection_owned_by_caller(connection)


@pytest.mark.parametrize(
    ("failure_point", "error_type"),
    [("cursor", psycopg.OperationalError), ("execute", psycopg.DatabaseError),
     ("execute", psycopg.errors.UndefinedTable), ("fetchone", psycopg.DatabaseError),
     ("fetchone", RuntimeError), ("cursor_exit", psycopg.OperationalError)],
)
def test_get_source_watermark_propagates_lookup_errors(connection, failure_point, error_type) -> None:
    """Connection, missing-table, fetch, and cleanup failures never become no history."""

    cursor_context = connection.cursor.return_value
    cursor = cursor_context.__enter__.return_value
    cursor.fetchone.return_value = (GREATEST_END,)
    operation = {
        "cursor": connection.cursor,
        "execute": cursor.execute,
        "fetchone": cursor.fetchone,
        "cursor_exit": cursor_context.__exit__,
    }[failure_point]
    error = error_type("Lookup failed")
    operation.side_effect = error

    with pytest.raises(error_type) as raised:
        ingestion_runs.get_source_watermark(connection, "analytics", "games")

    assert raised.value is error
    assert_lookup_leaves_connection_owned_by_caller(connection)
