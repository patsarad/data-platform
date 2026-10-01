"""Tests for games CLI wiring to extraction, archival, and raw storage."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import psycopg
import pytest

from src.ingestion import pipeline, run_ingestion
from src.utils.config import Settings


@pytest.mark.parametrize(
    ("options", "batch_size", "max_batches", "output_path"),
    [
        ([], 500, None, None),
        (["--batch-size", "25", "--max-batches", "2", "--output-path", "custom/games.jsonl"],
         25, 2, Path("custom/games.jsonl")),
        (["--max-batches", "0"], 500, 0, None),
    ],
)
def test_cli_composes_games_components(monkeypatch, options, batch_size, max_batches, output_path):
    """Keep CLI defaults/options and games wiring at the composition boundary."""

    monkeypatch.setattr("sys.argv", ["run_ingestion", *options])
    monkeypatch.setattr(run_ingestion, "get_settings", lambda: Settings(postgres_schema="custom_raw"))
    default_path = Path("data/raw/raw_games_20260925T000000Z.jsonl")
    build_path = MagicMock(return_value=default_path)
    monkeypatch.setattr(run_ingestion, "build_output_path", build_path)
    runner = MagicMock(return_value=(3, 2))
    monkeypatch.setattr(run_ingestion, "ingest_entity", runner)
    fetch = MagicMock()
    monkeypatch.setattr(run_ingestion, "fetch_games_batches", fetch)
    logger = MagicMock()
    monkeypatch.setattr(run_ingestion, "get_logger", lambda _: logger)

    run_ingestion.main()

    runner.assert_called_once()
    components = runner.call_args.kwargs
    assert components["entity"] is run_ingestion.GAMES
    assert components["schema_name"] == "custom_raw"
    assert components["output_path"] == (output_path or default_path)
    assert build_path.call_count == (0 if output_path else 1)
    assert components["archive_records"] is run_ingestion.save_games_to_jsonl
    assert components["ensure_table"] is run_ingestion.ensure_raw_games_table
    assert components["upsert_records"] is run_ingestion.upsert_raw_games
    assert components["logger"] is logger
    client = object()
    components["fetch_records"](client)
    fetch.assert_called_once_with(client, batch_size=batch_size, max_batches=max_batches)
    assert logger.info.call_args.args[1:] == (3, 2, "custom_raw")


@pytest.mark.parametrize(
    ("games", "output_path", "write_fails"),
    [
        ([{"id": 1, "name": "Halo"}], None, False),
        ([{"id": 1}], "custom/games.jsonl", False),
        ([], None, False),
        ([{"id": 1}], None, "execute"),
        ([{"id": 1}], None, "commit"),
    ],
    ids=["default-output", "custom-output", "empty-games", "failed-upsert", "failed-load-commit"],
)
def test_main_preserves_games_flow(monkeypatch, games, output_path, write_fails) -> None:
    """Exercise real storage helpers with a fake connection, including failure exit."""

    argv = ["run_ingestion", "--batch-size", "25", "--max-batches", "2"]
    if output_path:
        argv.extend(["--output-path", output_path])
    monkeypatch.setattr("sys.argv", argv)
    monkeypatch.setattr(run_ingestion, "get_settings", lambda: Settings(postgres_schema="custom_raw"))
    monkeypatch.setattr(pipeline, "get_source_watermark", lambda *_: None)
    logger = MagicMock()
    monkeypatch.setattr(run_ingestion, "get_logger", lambda _: logger)
    client = object()
    monkeypatch.setattr(pipeline, "create_igdb_client", lambda: client)
    fetch = MagicMock(return_value=games)
    archive = MagicMock()
    connection = MagicMock()
    connection.__enter__.return_value = connection
    start_connection = MagicMock()
    start_connection.__enter__.return_value = start_connection
    finish_connection = MagicMock()
    finish_connection.__enter__.return_value = finish_connection
    finish_cursor = finish_connection.cursor.return_value.__enter__.return_value
    finish_cursor.rowcount = 1
    connect = MagicMock(side_effect=[start_connection, connection, finish_connection])
    monkeypatch.setattr(run_ingestion, "fetch_games_batches", fetch)
    monkeypatch.setattr(run_ingestion, "save_games_to_jsonl", archive)
    monkeypatch.setattr(pipeline, "create_connection", connect)
    cursor = connection.cursor.return_value.__enter__.return_value
    events = MagicMock()
    events.attach_mock(fetch, "fetch")
    events.attach_mock(archive, "archive")
    events.attach_mock(connect, "connect")
    events.attach_mock(cursor.execute, "ddl")
    events.attach_mock(cursor.executemany, "upsert")
    events.attach_mock(connection.commit, "commit")
    events.attach_mock(start_connection.commit, "start_commit")
    events.attach_mock(start_connection.__exit__, "start_exit")
    events.attach_mock(connection.__exit__, "raw_exit")
    events.attach_mock(finish_cursor.execute, "finish")
    events.attach_mock(finish_connection.commit, "finish_commit")
    events.attach_mock(finish_connection.__exit__, "finish_exit")
    error = psycopg.DatabaseError("Upsert failed")
    if write_fails == "execute":
        cursor.executemany.side_effect = error
    elif write_fails == "commit":
        connection.commit.side_effect = [None, error]

    before = datetime.now(timezone.utc)
    if write_fails:
        with pytest.raises(psycopg.DatabaseError) as raised:
            run_ingestion.main()
        assert raised.value is error
        assert connection.__exit__.call_args.args[1] is error
        assert logger.info.call_count == 2
    else:
        run_ingestion.main()
        connection.__exit__.assert_called_once_with(None, None, None)
        assert logger.info.call_args.args[1:] == (len(games), len(games), "custom_raw")
    after = datetime.now(timezone.utc)

    fetch.assert_called_once_with(client, batch_size=25, max_batches=2)
    archive.assert_called_once()
    archived_games, archived_path = archive.call_args.args
    assert archived_games is games
    if output_path:
        assert archived_path == Path(output_path)
    else:
        assert archived_path.parent == Path("data/raw")
        datetime.strptime(archived_path.name, "raw_games_%Y%m%dT%H%M%SZ.jsonl")
    assert connect.call_count == 3
    assert all(call.args == () and call.kwargs == {} for call in connect.call_args_list)
    assert cursor.execute.call_args_list[0].args == ("CREATE SCHEMA IF NOT EXISTS custom_raw;",)
    assert "CREATE TABLE IF NOT EXISTS custom_raw.raw_games" in cursor.execute.call_args_list[1].args[0]
    expected_events = [
        "connect", "start_commit", "start_commit", "start_exit",
        "fetch", "archive", "connect", "ddl", "ddl", "commit",
    ]
    if games:
        expected_events.append("upsert")
        sql, rows = cursor.executemany.call_args.args
        assert "INSERT INTO custom_raw.raw_games" in sql
        assert [row[3].obj for row in rows] == games
        assert before <= rows[0][4] <= after
        assert rows[0][4].tzinfo == timezone.utc
        if not write_fails or write_fails == "commit":
            expected_events.append("commit")
    else:
        cursor.executemany.assert_not_called()
    expected_events.extend(["raw_exit", "connect", "finish", "finish_commit", "finish_exit"])
    assert [call[0] for call in events.mock_calls] == expected_events

    start_cursor = start_connection.cursor.return_value.__enter__.return_value
    run_id, entity, started_at = start_cursor.execute.call_args.args[1]
    assert entity == "games"
    assert before <= started_at <= after
    completed_at, status, fetched, loaded, message, finished_id = finish_cursor.execute.call_args.args[1]
    assert finished_id == run_id
    assert started_at <= completed_at <= after
    assert completed_at.tzinfo == timezone.utc
    assert (status, fetched, loaded, message) == (
        "failed" if write_fails else "succeeded", len(games),
        0 if write_fails else len(games), "raw load failed." if write_fails else None,
    )
    start_connection.__exit__.assert_called_once_with(None, None, None)
    finish_connection.__exit__.assert_called_once_with(None, None, None)


@pytest.fixture
def cli_lifecycle(monkeypatch):
    """Use separate fake connections and mock boundaries to inject stage failures."""

    monkeypatch.setattr("sys.argv", ["run_ingestion"])
    monkeypatch.setattr(run_ingestion, "get_settings", lambda: Settings(postgres_schema="analytics"))
    mocks = {}
    for name in (
        "create_igdb_client", "fetch_games_batches", "save_games_to_jsonl",
        "ensure_raw_games_table", "upsert_raw_games", "ensure_ingestion_runs_table",
        "start_ingestion_run", "succeed_ingestion_run", "fail_ingestion_run",
        "get_source_watermark",
    ):
        mocks[name] = MagicMock()
        owner = run_ingestion if name in {
            "fetch_games_batches", "save_games_to_jsonl", "ensure_raw_games_table", "upsert_raw_games"
        } else pipeline
        monkeypatch.setattr(owner, name, mocks[name])
    mocks["fetch_games_batches"].return_value = [{"id": 1}]
    mocks["upsert_raw_games"].return_value = 1
    mocks["get_source_watermark"].return_value = None
    mocks["start_ingestion_run"].return_value = "test-run-id"
    connections = [MagicMock() for _ in range(4)]
    for connection in connections:
        connection.__enter__.return_value = connection
    mocks["create_connection"] = MagicMock(side_effect=connections)
    monkeypatch.setattr(pipeline, "create_connection", mocks["create_connection"])
    mocks["logger"] = MagicMock()
    monkeypatch.setattr(run_ingestion, "get_logger", lambda _: mocks["logger"])
    return mocks, connections


@pytest.mark.parametrize(
    ("operation", "stage", "fetched", "loaded", "connection_count"),
    [
        ("create_igdb_client", "source fetch", 0, 0, 2),
        ("fetch_games_batches", "source fetch", 0, 0, 2),
        ("save_games_to_jsonl", "JSONL archive", 1, 0, 2),
        ("ensure_raw_games_table", "raw load", 1, 0, 3),
        ("upsert_raw_games", "raw load", 1, 0, 3),
        ("succeed_ingestion_run", "run completion", 1, 1, 4),
    ],
)
def test_main_records_stage_failures(
    cli_lifecycle, operation, stage, fetched, loaded, connection_count
) -> None:
    """Failures retain known counts, safe summaries, and the original exception."""

    mocks, connections = cli_lifecycle
    error = RuntimeError("sensitive-token-must-not-be-persisted")
    mocks[operation].side_effect = error

    with pytest.raises(RuntimeError) as raised:
        run_ingestion.main()

    assert raised.value is error
    assert mocks["create_connection"].call_count == connection_count
    mocks["fail_ingestion_run"].assert_called_once_with(
        connections[connection_count - 1], "analytics", "test-run-id",
        fetched, loaded, f"{stage} failed.",
    )
    assert str(error) not in str(mocks["logger"].mock_calls)
    assert mocks["logger"].info.call_count == 2
    if stage in {"raw load", "run completion"}:
        assert connections[connection_count - 2].__exit__.call_args.args[1] is error
    if stage != "run completion":
        mocks["succeed_ingestion_run"].assert_not_called()
    if stage == "source fetch":
        mocks["save_games_to_jsonl"].assert_not_called()
    if connection_count == 2:
        mocks["ensure_raw_games_table"].assert_not_called()


@pytest.mark.parametrize("operation", ["create_connection", "ensure_ingestion_runs_table", "start_ingestion_run"])
def test_main_stops_before_fetch_when_start_cannot_be_recorded(cli_lifecycle, operation) -> None:
    """A durable start is required before ingestion; no failure row can be assumed."""

    mocks, _ = cli_lifecycle
    error = psycopg.OperationalError("Metadata unavailable")
    mocks[operation].side_effect = error

    with pytest.raises(psycopg.OperationalError) as raised:
        run_ingestion.main()

    assert raised.value is error
    mocks["fetch_games_batches"].assert_not_called()
    mocks["fail_ingestion_run"].assert_not_called()


@pytest.mark.parametrize("failure_target", ["connect", "write"])
def test_failure_reporting_error_never_masks_original_error(cli_lifecycle, failure_target) -> None:
    """A database outage during failure reporting leaves the source error visible."""

    mocks, connections = cli_lifecycle
    original = RuntimeError("Original fetch failure")
    secondary = psycopg.OperationalError("sensitive-connection-details")
    mocks["fetch_games_batches"].side_effect = original
    if failure_target == "connect":
        mocks["create_connection"].side_effect = [connections[0], secondary]
    else:
        mocks["fail_ingestion_run"].side_effect = secondary

    with pytest.raises(RuntimeError) as raised:
        run_ingestion.main()

    assert raised.value is original
    assert mocks["logger"].error.call_count == 2
    assert str(secondary) not in str(mocks["logger"].mock_calls)
    mocks["succeed_ingestion_run"].assert_not_called()


@pytest.mark.parametrize("failed_connection", [1, 2])
def test_main_records_raw_or_completion_connection_failure(cli_lifecycle, failed_connection) -> None:
    """Opening a later connection can fail after the start or raw data was committed."""

    mocks, connections = cli_lifecycle
    error = psycopg.OperationalError("Connection failed")
    attempts = list(connections)
    attempts[failed_connection] = error
    mocks["create_connection"].side_effect = attempts

    with pytest.raises(psycopg.OperationalError) as raised:
        run_ingestion.main()

    assert raised.value is error
    mocks["fail_ingestion_run"].assert_called_once_with(
        connections[failed_connection + 1], "analytics", "test-run-id", 1,
        0 if failed_connection == 1 else 1,
        "raw load failed." if failed_connection == 1 else "run completion failed.",
    )


ENTITY_NAMES = ("games", "genres", "platforms", "companies", "involved_companies")


@pytest.mark.parametrize("name", ENTITY_NAMES)
@pytest.mark.parametrize("override", [False, True], ids=["default-archive", "output-override"])
def test_single_entity_selection(monkeypatch, name, override):
    """Each selection supplies its own established contract and all four callbacks."""

    options = ["--entity", name, "--batch-size", "7", "--max-batches", "3"]
    if override:
        options += ["--output-path", "custom/one.jsonl"]
    monkeypatch.setattr("sys.argv", ["run_ingestion", *options])
    monkeypatch.setattr(run_ingestion, "get_settings", lambda: Settings())
    runner = MagicMock(return_value=(7, 6))
    monkeypatch.setattr(run_ingestion, "ingest_entity", runner)
    monkeypatch.setattr(run_ingestion, "get_logger", lambda _: MagicMock())

    run_ingestion.main()

    runner.assert_called_once()
    supplied = runner.call_args.kwargs
    assert supplied["entity"] is getattr(run_ingestion, name.upper())
    assert supplied["schema_name"] == "raw"
    assert supplied["fetch_records"].func is getattr(run_ingestion, f"fetch_{name}_batches")
    assert supplied["fetch_records"].keywords == {"batch_size": 7, "max_batches": 3}
    assert supplied["archive_records"] is getattr(run_ingestion, f"save_{name}_to_jsonl")
    assert supplied["ensure_table"] is getattr(run_ingestion, f"ensure_raw_{name}_table")
    assert supplied["upsert_records"] is getattr(run_ingestion, f"upsert_raw_{name}")
    if override:
        assert supplied["output_path"] == Path("custom/one.jsonl")
    else:
        assert supplied["output_path"].parent == Path("data/raw")
        datetime.strptime(supplied["output_path"].name, f"raw_{name}_%Y%m%dT%H%M%SZ.jsonl")


def test_default_games_path_compatibility(monkeypatch):
    """No-argument and custom-directory callers retain the exact UTC games format."""

    clock = MagicMock()
    clock.now.return_value = datetime(2026, 9, 26, 1, 2, 3, tzinfo=timezone.utc)
    monkeypatch.setattr(run_ingestion, "datetime", clock)
    assert run_ingestion.build_output_path() == Path("data/raw/raw_games_20260926T010203Z.jsonl")
    assert run_ingestion.build_output_path(Path("custom")) == Path("custom/raw_games_20260926T010203Z.jsonl")
    clock.now.assert_called_with(timezone.utc)


@pytest.mark.parametrize(
    ("options", "message"),
    [
        (["--entity", "unknown"], "invalid choice"),
        (["--entity", "all", "--output-path", "ambiguous.jsonl"], "--output-path is ambiguous"),
        (["--full-refresh", "--backfill-start", "2026-09-01T00:00:00Z",
          "--backfill-end", "2026-09-02T00:00:00Z"], "cannot be combined"),
        (["--backfill-start", "2026-09-01T00:00:00Z"], "must be supplied together"),
        (["--backfill-end", "2026-09-02T00:00:00Z"], "must be supplied together"),
        (["--backfill-start", "2026-09-02T00:00:00Z",
          "--backfill-end", "2026-09-01T00:00:00Z"], "must be later"),
        (["--backfill-start", "2026-09-01T00:00:00Z",
          "--backfill-end", "2026-09-01T00:00:00Z"], "must be later"),
        (["--backfill-start", "2026-09-01T00:00:00+00:00",
          "--backfill-end", "2026-09-02T00:00:00Z"], "whole-second UTC"),
        (["--backfill-start", "2026-09-01T00:00:00.1Z",
          "--backfill-end", "2026-09-02T00:00:00Z"], "whole-second UTC"),
        (["--backfill-start", "1969-12-31T23:59:59Z",
          "--backfill-end", "1970-01-01T00:00:01Z"], "Unix epoch"),
    ],
)
def test_invalid_selection_rejected_before_side_effects(monkeypatch, tmp_path, capsys, options, message):
    """Parsing rejects invalid combinations before settings, files, API, or database work."""

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["run_ingestion", *options])
    boundaries = []
    for owner, name in (
        (run_ingestion, "get_settings"), (run_ingestion, "get_logger"),
        (run_ingestion, "build_output_path"), (run_ingestion, "ingest_entity"),
        (pipeline, "create_igdb_client"), (pipeline, "create_connection"),
    ):
        boundary = MagicMock(side_effect=AssertionError("Unexpected side effect"))
        monkeypatch.setattr(owner, name, boundary)
        boundaries.append(boundary)
    with pytest.raises(SystemExit) as raised:
        run_ingestion.main()
    assert raised.value.code == 2
    assert message in capsys.readouterr().err
    for boundary in boundaries:
        boundary.assert_not_called()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("failure_stage", [None, "fetch", "raw_exit", "completion"])
def test_all_composes_independent_lifecycles(monkeypatch, tmp_path, failure_stage):
    """Real helpers retain per-entity limits/counts/archives and earlier successes on failure.

    Fake only API and database boundaries. Commit assertions establish acknowledged
    operations, not live PostgreSQL durability or rollback.
    """

    import json

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["run_ingestion", "--entity", "all", "--batch-size", "2", "--max-batches", "2"])
    monkeypatch.setattr(run_ingestion, "get_settings", lambda: Settings(postgres_schema="custom_raw"))
    monkeypatch.setattr(pipeline, "get_source_watermark", lambda *_: None)
    logger = MagicMock()
    monkeypatch.setattr(run_ingestion, "get_logger", lambda _: logger)
    error = RuntimeError("sensitive-failure-detail")
    events = MagicMock()
    connections = {}
    for name in ENTITY_NAMES:
        connections[name] = [MagicMock() for _ in range(3)]
        for stage, connection in zip(("start", "raw", "finish"), connections[name]):
            connection.__enter__.return_value = connection
            connection.cursor.return_value.__enter__.return_value.rowcount = 1
            events.attach_mock(connection.commit, f"{name}_{stage}_commit")
            events.attach_mock(connection.__exit__, f"{name}_{stage}_exit")
    attempted = ENTITY_NAMES if failure_stage is None else ENTITY_NAMES[:3]
    sequence = [connection for name in attempted for connection in connections[name]]
    if failure_stage == "fetch":
        sequence.remove(connections["platforms"][1])
    if failure_stage == "raw_exit":
        connections["platforms"][1].__exit__.side_effect = error
    if failure_stage == "completion":
        connections["platforms"][2].commit.side_effect = error
        failed = MagicMock()
        failed.__enter__.return_value = failed
        failed.cursor.return_value.__enter__.return_value.rowcount = 1
        sequence.append(failed)
    connect = MagicMock(side_effect=sequence)
    monkeypatch.setattr(pipeline, "create_connection", connect)
    # More than the cap for two entities, partial/empty termination for others.
    records = {
        name: [{"id": i, "extra": {"values": [None, False, "é"]}} for i in range(count)]
        for name, count in zip(ENTITY_NAMES, (6, 3, 2, 1, 5))
    }
    client = MagicMock()

    def query(endpoint, body):
        if endpoint == "platforms" and failure_stage == "fetch":
            raise error
        offset = int(body.split("offset ")[1].split(";")[0])
        return records[endpoint][offset:offset + 2]

    client.query.side_effect = query
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(pipeline, "create_igdb_client", factory)
    events.attach_mock(client.query, "query")
    if failure_stage:
        with pytest.raises(RuntimeError) as raised:
            run_ingestion.main()
        assert raised.value is error
    else:
        run_ingestion.main()

    assert factory.call_count == len(attempted)
    assert connect.call_count == len(sequence)
    expected_queries = []
    for name in attempted:
        entity = getattr(run_ingestion, name.upper())
        offsets = (0,) if name == "companies" or (name == "platforms" and failure_stage == "fetch") else (0, 2)
        expected_queries.extend((name, f"fields {', '.join(entity.fields)}; sort id asc; limit 2; offset {offset};") for offset in offsets)
    assert [call.args for call in client.query.call_args_list] == expected_queries
    event_names = [call[0] for call in events.mock_calls]
    run_ids = []
    for index, name in enumerate(attempted):
        start, raw, finish = connections[name]
        run_id, endpoint, started_at = start.cursor.return_value.__enter__.return_value.execute.call_args.args[1]
        run_ids.append(run_id)
        assert endpoint == name and started_at.tzinfo == timezone.utc
        assert start.commit.call_count == 2
        start.__exit__.assert_called_once_with(None, None, None)
        query_index = next(i for i, call in enumerate(events.mock_calls) if call[0] == "query" and call.args[0] == name)
        assert event_names.index(f"{name}_start_exit") < query_index
        if index:
            assert event_names.index(f"{attempted[index - 1]}_finish_exit") < event_names.index(f"{name}_start_commit")
        is_failure = bool(failure_stage and name == "platforms")
        fetched = 0 if is_failure and failure_stage == "fetch" else min(len(records[name]), 4)
        loaded = fetched
        terminal_connection = failed if is_failure and failure_stage == "completion" else finish
        terminal = terminal_connection.cursor.return_value.__enter__.return_value.execute.call_args.args[1]
        assert terminal[1:] == (
            "failed" if is_failure else "succeeded", fetched, loaded,
            {"fetch": "source fetch failed.", "raw_exit": "raw load failed.", "completion": "run completion failed."}[failure_stage] if is_failure else None,
            run_id,
        )
        assert terminal[0] >= started_at
        if fetched:
            raw.commit.assert_called()  # DDL and acknowledged upsert remain committed.
            assert raw.commit.call_count == 2
            rows = raw.cursor.return_value.__enter__.return_value.executemany.call_args.args[1]
            assert [row[-2].obj for row in rows] == records[name][:4]
            if not is_failure:
                assert event_names.index(f"{name}_raw_exit") < event_names.index(f"{name}_finish_commit")
        else:
            raw.__enter__.assert_not_called()
        archives = list(Path("data/raw").glob(f"raw_{name}_*.jsonl"))
        assert len(archives) == (0 if is_failure and failure_stage == "fetch" else 1)
        if archives:
            assert [json.loads(line) for line in archives[0].read_text().splitlines()] == records[name][:4]
    assert len(set(run_ids)) == len(attempted)
    for name in ENTITY_NAMES[len(attempted):]:
        assert not list(Path("data/raw").glob(f"raw_{name}_*.jsonl"))
        for connection in connections[name]:
            connection.__enter__.assert_not_called()
    finished_logs = [call.args for call in logger.info.call_args_list if call.args[0].startswith("Finished")]
    succeeded = attempted[:-1] if failure_stage else attempted
    assert [args[1:] for args in finished_logs] == [(min(len(records[name]), 4), min(len(records[name]), 4), "custom_raw") for name in succeeded]
    assert str(error) not in str(logger.mock_calls)
