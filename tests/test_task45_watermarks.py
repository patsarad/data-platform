"""Offline task 4.5 checks at the real fetch/archive/load/metadata boundary."""

import json
from datetime import datetime, timedelta, timezone
from functools import partial
from unittest.mock import MagicMock

import pytest

from src.entities import COMPANIES, GAMES, GENRES, INVOLVED_COMPANIES, PLATFORMS
from src.ingestion import pipeline, run_ingestion
from src.ingestion.fetch_companies import fetch_companies_batches, save_companies_to_jsonl
from src.ingestion.fetch_games import fetch_games_batches, save_games_to_jsonl
from src.ingestion.fetch_genres import fetch_genres_batches, save_genres_to_jsonl
from src.ingestion.fetch_involved_companies import (
    fetch_involved_companies_batches, save_involved_companies_to_jsonl,
)
from src.ingestion.fetch_platforms import fetch_platforms_batches, save_platforms_to_jsonl
from src.ingestion.windows import SourceWindow
from src.storage.raw_companies import ensure_raw_companies_table, upsert_raw_companies
from src.storage.raw_games import ensure_raw_games_table, upsert_raw_games
from src.storage.raw_genres import ensure_raw_genres_table, upsert_raw_genres
from src.storage.raw_involved_companies import (
    ensure_raw_involved_companies_table, upsert_raw_involved_companies,
)
from src.storage.raw_platforms import ensure_raw_platforms_table, upsert_raw_platforms
from src.utils.config import Settings


NOW = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
U = int(NOW.timestamp())
W = NOW - timedelta(hours=2)
L = int(W.timestamp()) - 86_400
COMPONENTS = (
    (GAMES, fetch_games_batches, save_games_to_jsonl, ensure_raw_games_table, upsert_raw_games),
    (COMPANIES, fetch_companies_batches, save_companies_to_jsonl,
     ensure_raw_companies_table, upsert_raw_companies),
    (INVOLVED_COMPANIES, fetch_involved_companies_batches, save_involved_companies_to_jsonl,
     ensure_raw_involved_companies_table, upsert_raw_involved_companies),
)
REFERENCE_COMPONENTS = (
    (GENRES, fetch_genres_batches, save_genres_to_jsonl, ensure_raw_genres_table, upsert_raw_genres),
    (PLATFORMS, fetch_platforms_batches, save_platforms_to_jsonl,
     ensure_raw_platforms_table, upsert_raw_platforms),
)


class FixedDatetime(datetime):
    """Supply one deterministic run cutoff and fetch-completion instant."""

    @classmethod
    def now(cls, tz=None):
        return NOW


def connection(watermark=None):
    """Model only recorded SQL, parameters, commits, and context calls."""

    result = MagicMock()
    result.__enter__.return_value = result
    cursor = result.cursor.return_value.__enter__.return_value
    cursor.rowcount = 1
    cursor.fetchone.return_value = (watermark,)
    return result


def execute_args(db):
    return [call.args for call in db.cursor.return_value.__enter__.return_value.execute.call_args_list]


def flow(monkeypatch, tmp_path, component, *, watermark=None, pages=None, cap=None,
         batch_size=2, default_fields=True, fetch=None, archive=None, upsert=None,
         mode="normal", backfill_window=None):
    entity, canonical_fetch, canonical_archive, ensure, canonical_upsert = component
    start, raw, finish, failure = (connection(watermark) for _ in range(4))
    connect = MagicMock(side_effect=[start, raw, finish, failure])
    monkeypatch.setattr(pipeline, "create_connection", connect)
    client = MagicMock()
    client.query.side_effect = pages if pages is not None else [[{"id": 1, "updated_at": U - 1}]]
    monkeypatch.setattr(pipeline, "create_igdb_client", MagicMock(return_value=client))
    monkeypatch.setattr(pipeline, "datetime", FixedDatetime)
    path = tmp_path / f"{entity.endpoint}.jsonl"
    logger = MagicMock()
    run = partial(
        pipeline.ingest_entity, entity=entity, schema_name="custom_raw", output_path=path,
        fetch_records=fetch or partial(canonical_fetch, batch_size=batch_size, max_batches=cap),
        archive_records=archive or canonical_archive, ensure_table=ensure,
        upsert_records=upsert or canonical_upsert, logger=logger,
        selection=pipeline.RunSelection(batch_size, cap, default_fields, mode, backfill_window),
    )
    return run, (start, raw, finish, failure), client, path, logger, connect


@pytest.mark.parametrize("component", COMPONENTS, ids=lambda c: c[0].endpoint)
@pytest.mark.parametrize("watermark", [None, W], ids=["bootstrap", "window"])
def test_normal_selection_commits_cutoff_after_raw_exit(monkeypatch, tmp_path, component, watermark):
    records = [{"id": 7, "updated_at": U - 1 if watermark is None else L},
               {"id": 7, "updated_at": U - 1}]
    run, (start, raw, finish, _), client, path, logger, _ = flow(
        monkeypatch, tmp_path, component, watermark=watermark, pages=[records, []],
    )
    events = MagicMock()
    events.attach_mock(raw.__exit__, "raw_exit")
    events.attach_mock(finish.commit, "terminal_commit")

    assert run() == (2, 2)
    assert [json.loads(line) for line in path.read_text().splitlines()] == records
    queries = [call.args[1] for call in client.query.call_args_list]
    assert [q.split("offset ")[1] for q in queries] == ["0;", "2;"]
    predicate = f"where updated_at >= {L} & updated_at < {U}; "
    assert all((predicate in q) == (watermark is not None) for q in queries)
    assert all("sort id asc;" in q for q in queries)
    lookup_sql, lookup_params = execute_args(start)[2]
    assert "SELECT MAX(source_watermark_end)" in lookup_sql.as_string()
    assert lookup_params == (component[0].endpoint,)
    start_sql, start_params = execute_args(start)[-1]
    assert start_params[2] == NOW
    if watermark is None:
        assert "source_watermark_start" not in start_sql.as_string()
    else:
        assert start_params[-1] == datetime.fromtimestamp(L, timezone.utc)
    terminal_sql, terminal_params = execute_args(finish)[0]
    assert "source_watermark_end = %s" in terminal_sql.as_string()
    assert terminal_params[1:4] == ("succeeded", 2, 2)
    assert terminal_params[-2] == NOW
    assert terminal_params[-1] == start_params[0]
    assert "AND status = 'running'" in terminal_sql.as_string()
    assert [call[0] for call in events.mock_calls] == ["raw_exit", "terminal_commit"]
    assert start.commit.call_count == 2
    assert raw.commit.call_count == 2
    finish.commit.assert_called_once_with()
    logger.warning.assert_not_called()


@pytest.mark.parametrize("watermark", [None, W])
def test_empty_uncapped_success_advances_without_upsert_commit(monkeypatch, tmp_path, watermark):
    run, (_, raw, finish, _), _, path, _, _ = flow(
        monkeypatch, tmp_path, COMPONENTS[0], watermark=watermark, pages=[[]],
    )
    assert run() == (0, 0)
    assert path.read_bytes() == b""
    raw.cursor.return_value.__enter__.return_value.executemany.assert_not_called()
    raw.commit.assert_called_once_with()  # DDL only.
    assert execute_args(finish)[0][1][1:4] == ("succeeded", 0, 0)
    assert execute_args(finish)[0][1][-2] == NOW


@pytest.mark.parametrize("cap", [0, -1, 1, 99])
def test_any_supplied_cap_withholds_checkpoint(monkeypatch, tmp_path, cap):
    pages = [] if cap <= 0 else [[{"id": 1, "updated_at": U - 1}]]
    run, (start, _, finish, _), client, _, logger, _ = flow(
        monkeypatch, tmp_path, COMPONENTS[1], watermark=W, pages=pages, cap=cap,
    )
    assert run()[0] == (0 if cap <= 0 else 1)
    assert ("source_watermark_start" in execute_args(start)[-1][0].as_string())
    assert "source_watermark_end" not in execute_args(finish)[0][0].as_string()
    assert logger.warning.call_args.args[2].endswith("batch cap.")
    assert client.query.call_count == (0 if cap <= 0 else 1)


@pytest.mark.parametrize("batch_size", [0, 501])
def test_out_of_range_page_size_withholds_checkpoint(monkeypatch, tmp_path, batch_size):
    run, (_, _, finish, _), _, _, logger, _ = flow(
        monkeypatch, tmp_path, COMPONENTS[0], pages=[[]], batch_size=batch_size,
    )
    assert run() == (0, 0)
    assert "source_watermark_end" not in execute_args(finish)[0][0].as_string()
    assert "page size" in logger.warning.call_args.args[2]


@pytest.mark.parametrize("value", [None, True, -1, 1.5, "1", 10**100, U + 1, L - 1, U])
def test_unusable_window_timestamp_preserves_payload_and_withholds_end(monkeypatch, tmp_path, value):
    records = [{"id": 3, "updated_at": value, "nested": [None, False]}]
    run, (_, raw, finish, _), _, path, logger, _ = flow(
        monkeypatch, tmp_path, COMPONENTS[0], watermark=W, pages=[records],
    )
    assert run() == (1, 1)
    assert json.loads(path.read_text()) == records[0]
    rows = raw.cursor.return_value.__enter__.return_value.executemany.call_args.args[1]
    assert rows[0][-2].obj == records[0]
    assert "source_watermark_end" not in execute_args(finish)[0][0].as_string()
    logger.warning.assert_called_once()


def test_missing_bootstrap_timestamp_withholds_end_without_dropping_record(monkeypatch, tmp_path):
    run, (_, raw, finish, _), _, path, logger, _ = flow(
        monkeypatch, tmp_path, COMPONENTS[2], pages=[[{"id": 3, "publisher": False}]],
    )
    assert run() == (1, 1)
    assert json.loads(path.read_text()) == {"id": 3, "publisher": False}
    assert raw.cursor.return_value.__enter__.return_value.executemany.call_args.args[1][0][-2].obj == {
        "id": 3, "publisher": False,
    }
    assert "source_watermark_end" not in execute_args(finish)[0][0].as_string()
    logger.warning.assert_called_once()


@pytest.mark.parametrize("operation", ["archive", "load"])
def test_mismatched_acknowledged_count_withholds_end(monkeypatch, tmp_path, operation):
    canonical = COMPONENTS[0]
    archive = (lambda records, path: 0) if operation == "archive" else canonical[2]
    upsert = (lambda db, rows, schema, at: 0) if operation == "load" else canonical[4]
    run, (_, _, finish, _), _, _, logger, _ = flow(
        monkeypatch, tmp_path, canonical, archive=archive, upsert=upsert,
    )
    assert run() == ((1, 1) if operation == "archive" else (1, 0))
    assert "source_watermark_end" not in execute_args(finish)[0][0].as_string()
    assert "count did not match" in logger.warning.call_args.args[2]


def test_bootstrap_accepts_timestamp_after_cutoff_before_fetch_completion(monkeypatch, tmp_path):
    class LaterDatetime(datetime):
        calls = 0

        @classmethod
        def now(cls, tz=None):
            cls.calls += 1
            return NOW if cls.calls == 1 else NOW + timedelta(seconds=3)

    run, (_, _, finish, _), _, _, _, _ = flow(
        monkeypatch, tmp_path, COMPONENTS[0], pages=[[{"id": 1, "updated_at": U + 2}]],
    )
    monkeypatch.setattr(pipeline, "datetime", LaterDatetime)
    assert run() == (1, 1)
    assert execute_args(finish)[0][1][-2] == NOW


def test_lookup_error_precedes_source_and_start(monkeypatch, tmp_path):
    run, (start, raw, finish, _), client, path, _, connect = flow(
        monkeypatch, tmp_path, COMPONENTS[0], watermark=None,
    )
    error = RuntimeError("lookup unavailable")
    monkeypatch.setattr(pipeline, "get_source_watermark", MagicMock(side_effect=error))
    with pytest.raises(RuntimeError) as raised:
        run()
    assert raised.value is error
    assert start.commit.call_count == 1  # Metadata DDL, then failed lookup.
    assert all("INSERT INTO" not in sql.as_string() for sql, *_ in execute_args(start))
    assert connect.call_count == 1
    client.query.assert_not_called()
    raw.__enter__.assert_not_called()
    finish.__enter__.assert_not_called()
    assert not path.exists()


@pytest.mark.parametrize("watermark", [NOW, NOW + timedelta(seconds=1)])
def test_nonprogressing_cutoff_aborts_before_source(monkeypatch, tmp_path, watermark):
    run, (start, raw, _, _), client, path, _, connect = flow(
        monkeypatch, tmp_path, COMPONENTS[0], watermark=watermark,
    )
    with pytest.raises(ValueError, match="greater than watermark"):
        run()
    assert start.commit.call_count == 1
    assert all("INSERT INTO" not in sql.as_string() for sql, *_ in execute_args(start))
    assert connect.call_count == 1
    client.query.assert_not_called()
    raw.__enter__.assert_not_called()
    assert not path.exists()


@pytest.mark.parametrize("failure", ["raw_exit", "terminal_commit", "guard"])
def test_post_load_failure_keeps_count_and_original_error(monkeypatch, tmp_path, failure):
    run, (_, raw, finish, failed), _, _, logger, _ = flow(
        monkeypatch, tmp_path, COMPONENTS[0], watermark=W,
    )
    error = RuntimeError("private failure detail")
    if failure == "raw_exit":
        raw.__exit__.side_effect = error
    elif failure == "terminal_commit":
        finish.commit.side_effect = error
    else:
        finish.cursor.return_value.__enter__.return_value.rowcount = 0
    with pytest.raises((RuntimeError, ValueError)) as raised:
        run()
    if failure != "guard":
        assert raised.value is error
    if failure == "raw_exit":
        assert execute_args(finish)[0][1][1:4] == ("failed", 1, 1)
        assert "source_watermark_end" not in execute_args(finish)[0][0].as_string()
        failed.cursor.return_value.__enter__.return_value.execute.assert_not_called()
    else:
        assert "source_watermark_end = %s" in execute_args(finish)[0][0].as_string()
        assert execute_args(failed)[0][1][1:4] == ("failed", 1, 1)
        assert "source_watermark_end" not in execute_args(failed)[0][0].as_string()
    assert str(error) not in str(logger.mock_calls)


def test_terminal_acknowledgment_error_cannot_replace_guarded_success(monkeypatch, tmp_path):
    """Model an uncertain commit: the failed transition sees no running row."""

    run, (_, raw, finish, failed), _, _, logger, _ = flow(
        monkeypatch, tmp_path, COMPONENTS[0], watermark=W,
    )
    error = RuntimeError("completion acknowledgment lost")
    finish.commit.side_effect = error
    failed.cursor.return_value.__enter__.return_value.rowcount = 0
    with pytest.raises(RuntimeError) as raised:
        run()
    assert raised.value is error
    assert raw.__exit__.called
    assert execute_args(finish)[0][1][-2] == NOW
    assert execute_args(failed)[0][1][1:4] == ("failed", 1, 1)
    failed.commit.assert_not_called()
    assert logger.error.call_count == 2


@pytest.mark.parametrize("component", COMPONENTS, ids=lambda c: c[0].endpoint)
def test_full_refresh_ignores_history_and_commits_new_cutoff(monkeypatch, tmp_path, component):
    rows = [{"id": 1, "updated_at": U - 100000, "nested": [None, False]},
            {"id": 2, "updated_at": U - 1}]
    run, (start, raw, finish, _), client, path, _, _ = flow(
        monkeypatch, tmp_path, component, watermark=W, pages=[rows, []],
        mode="full_refresh",
    )
    order = MagicMock()
    order.attach_mock(raw.__exit__, "raw_exit")
    order.attach_mock(finish.commit, "terminal_commit")
    assert run() == (2, 2)
    assert [json.loads(line) for line in path.read_text().splitlines()] == rows
    assert [q.split("offset ")[1] for _, q in (call.args for call in client.query.call_args_list)] == ["0;", "2;"]
    assert all("where updated_at" not in call.args[1] for call in client.query.call_args_list)
    assert "source_watermark_start" not in execute_args(start)[-1][0].as_string()
    assert execute_args(finish)[0][1][-2] == NOW
    assert raw.cursor.return_value.__enter__.return_value.executemany.call_args.args[1][0][-2].obj == rows[0]
    assert [call[0] for call in order.mock_calls] == ["raw_exit", "terminal_commit"]


@pytest.mark.parametrize("reason", ["cap", "timestamp", "raw_exit", "terminal_commit"])
def test_full_refresh_withholds_end_on_ineligible_or_failed_run(monkeypatch, tmp_path, reason):
    pages = [[{"id": 1, "updated_at": None if reason == "timestamp" else U - 1}]]
    run, (_, raw, terminal, failed), _, _, logger, _ = flow(
        monkeypatch, tmp_path, COMPONENTS[0], watermark=W, pages=pages,
        cap=1 if reason == "cap" else None, mode="full_refresh",
    )
    if reason == "raw_exit":
        raw.__exit__.side_effect = RuntimeError("private raw error")
    if reason == "terminal_commit":
        terminal.commit.side_effect = RuntimeError("private metadata error")
    if reason in {"raw_exit", "terminal_commit"}:
        with pytest.raises(RuntimeError):
            run()
        failure_db = terminal if reason == "raw_exit" else failed
        assert "source_watermark_end" not in execute_args(failure_db)[0][0].as_string()
        assert "private" not in str(logger.mock_calls)
    else:
        assert run() == (1, 1)
        assert "source_watermark_end" not in execute_args(terminal)[0][0].as_string()


def test_full_refresh_rejects_nonprogressing_cutoff_before_source(monkeypatch, tmp_path):
    run, (start, _, _, _), client, path, _, connect = flow(
        monkeypatch, tmp_path, COMPONENTS[0], watermark=NOW, mode="full_refresh",
    )
    with pytest.raises(ValueError, match="greater than watermark"):
        run()
    assert start.commit.call_count == 1
    assert connect.call_count == 1
    client.query.assert_not_called()
    assert not path.exists()


@pytest.mark.parametrize("component", COMPONENTS + REFERENCE_COMPONENTS, ids=lambda c: c[0].endpoint)
def test_backfill_filters_every_page_and_never_publishes_progress(monkeypatch, tmp_path, component):
    a, b = U - 200000, U - 100000
    rows = [{"id": 1, "updated_at": a}, {"id": 2, "updated_at": b - 1}]
    run, (start, raw, finish, _), client, path, logger, _ = flow(
        monkeypatch, tmp_path, component, watermark=W, pages=[rows, []],
        mode="backfill", backfill_window=SourceWindow(a, b),
    )
    assert run() == (2, 2)
    assert [json.loads(line) for line in path.read_text().splitlines()] == rows
    assert [call.args[1].split("offset ")[1] for call in client.query.call_args_list] == ["0;", "2;"]
    assert all(f"where updated_at >= {a} & updated_at < {b};" in call.args[1]
               for call in client.query.call_args_list)
    assert all("SELECT MAX" not in sql.as_string() for sql, *_ in execute_args(start))
    assert execute_args(start)[-1][1][-1] == datetime.fromtimestamp(a, timezone.utc)
    assert "source_watermark_end" not in execute_args(finish)[0][0].as_string()
    assert execute_args(finish)[0][1][1:4] == ("succeeded", 2, 2)
    assert raw.commit.call_count == 2
    logger.warning.assert_not_called()


def test_capped_backfill_and_failed_backfill_keep_prior_progress(monkeypatch, tmp_path):
    interval = SourceWindow(U - 200000, U - 100000)
    run, (start, _, finish, _), client, path, _, _ = flow(
        monkeypatch, tmp_path, COMPONENTS[1], watermark=W,
        pages=[[{"id": 1, "updated_at": interval.lower_bound}]],
        cap=1, mode="backfill", backfill_window=interval,
    )
    assert run() == (1, 1)
    assert client.query.call_count == 1
    assert "SELECT MAX" not in str(execute_args(start))
    assert "source_watermark_end" not in execute_args(finish)[0][0].as_string()
    first_archive = path.read_text()

    run, (start, failed, _, _), client, path, logger, _ = flow(
        monkeypatch, tmp_path, COMPONENTS[1], watermark=W,
        pages=[RuntimeError("private source detail")],
        mode="backfill", backfill_window=interval,
    )
    with pytest.raises(RuntimeError, match="private source detail"):
        run()
    assert execute_args(start)[-1][1][-1] == datetime.fromtimestamp(interval.lower_bound, timezone.utc)
    assert execute_args(failed)[0][1][1:4] == ("failed", 0, 0)
    assert "source_watermark_end" not in execute_args(failed)[0][0].as_string()
    assert path.read_text() == first_archive
    assert "private source detail" not in str(logger.mock_calls)


@pytest.mark.parametrize("component", REFERENCE_COMPONENTS, ids=lambda c: c[0].endpoint)
def test_reference_full_refresh_is_usual_unfiltered_run(monkeypatch, tmp_path, component):
    run, (start, _, finish, _), client, _, _, _ = flow(
        monkeypatch, tmp_path, component, mode="full_refresh",
    )
    assert run() == (1, 1)
    assert "where updated_at" not in client.query.call_args.args[1]
    assert "SELECT MAX" not in str(execute_args(start))
    assert "source_watermark_start" not in execute_args(start)[-1][0].as_string()
    assert "source_watermark_end" not in execute_args(finish)[0][0].as_string()


@pytest.mark.parametrize("mode", ["full_refresh", "backfill"])
@pytest.mark.parametrize("prior", [None, W], ids=["no_history", "existing_history"])
def test_normal_rerun_uses_only_eligible_prior_end(monkeypatch, tmp_path, mode, prior):
    backfill = SourceWindow(U - 200000, U - 100000) if mode == "backfill" else None
    first, (_, _, first_finish, _), first_client, _, _, _ = flow(
        monkeypatch, tmp_path, COMPONENTS[0], watermark=prior,
        pages=[[{"id": 1, "updated_at": U - 1}]],
        mode=mode, backfill_window=backfill,
    )
    assert first() == (1, 1)
    published = mode == "full_refresh"
    assert ("source_watermark_end" in execute_args(first_finish)[0][0].as_string()) == published
    if mode == "backfill":
        assert "where updated_at" in first_client.query.call_args.args[1]
    next_history = NOW if published else prior
    class NextDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW + timedelta(days=1)
    second, (second_start, _, second_finish, _), second_client, _, _, _ = flow(
        monkeypatch, tmp_path, COMPONENTS[0], watermark=next_history,
        pages=[[{"id": 2, "updated_at": U - 1}]],
    )
    monkeypatch.setattr(pipeline, "datetime", NextDatetime)
    assert second() == (1, 1)
    query = second_client.query.call_args.args[1]
    if next_history is None:
        assert "where updated_at" not in query
    else:
        lower = max(0, int(next_history.timestamp()) - 86400)
        assert f"where updated_at >= {lower} & updated_at < {U + 86400};" in query
        assert execute_args(second_start)[-1][1][-1] == datetime.fromtimestamp(lower, timezone.utc)
    assert execute_args(second_finish)[0][1][-2] == NOW + timedelta(days=1)


@pytest.mark.parametrize("mode", ["full_refresh", "backfill"])
def test_all_mode_applies_explicit_selection_independently(monkeypatch, tmp_path, mode):
    monkeypatch.chdir(tmp_path)
    options = ["--entity", "all", "--batch-size", "2"]
    if mode == "full_refresh":
        options.append("--full-refresh")
    else:
        options.extend(["--backfill-start", "2026-09-01T00:00:00Z",
                        "--backfill-end", "2026-09-02T00:00:00Z"])
    monkeypatch.setattr("sys.argv", ["run_ingestion", *options])
    monkeypatch.setattr(run_ingestion, "get_settings", lambda: Settings(postgres_schema="custom_raw"))
    monkeypatch.setattr(run_ingestion, "get_logger", lambda _: MagicMock())
    monkeypatch.setattr(pipeline, "datetime", FixedDatetime)
    connections = [connection(W) for _ in range(15)]
    monkeypatch.setattr(pipeline, "create_connection", MagicMock(side_effect=connections))
    client = MagicMock()
    client.query.side_effect = [[{"id": i, "updated_at": U - 1}] for i in range(5)]
    monkeypatch.setattr(pipeline, "create_igdb_client", MagicMock(return_value=client))
    run_ingestion.main()
    assert [call.args[0] for call in client.query.call_args_list] == [
        "games", "genres", "platforms", "companies", "involved_companies",
    ]
    for index, entity in enumerate(("games", "genres", "platforms", "companies", "involved_companies")):
        start, raw, finish = connections[index * 3:index * 3 + 3]
        query = client.query.call_args_list[index].args[1]
        if mode == "full_refresh":
            assert "where updated_at" not in query
            assert "source_watermark_start" not in execute_args(start)[-1][0].as_string()
        else:
            assert "where updated_at >= 1788220800 & updated_at < 1788307200;" in query
            assert execute_args(start)[-1][1][-1] == datetime.fromtimestamp(1788220800, timezone.utc)
        assert ("SELECT MAX" in str(execute_args(start))) == (
            mode == "full_refresh" and entity in {"games", "companies", "involved_companies"}
        )
        assert ("source_watermark_end" in execute_args(finish)[0][0].as_string()) == (
            mode == "full_refresh" and entity in {"games", "companies", "involved_companies"}
        )
        assert raw.commit.call_count == 2
    assert len(list((tmp_path / "data/raw").glob("*.jsonl"))) == 5


def test_direct_and_custom_callback_cannot_checkpoint(monkeypatch, tmp_path):
    canonical = COMPONENTS[0]
    run, (_, _, finish, _), _, _, _, _ = flow(
        monkeypatch, tmp_path, canonical, pages=[[{"id": 1, "updated_at": U - 1}]],
        fetch=partial(canonical[1], batch_size=2, max_batches=None, fields=("id", "updated_at")),
    )
    assert run() == (1, 1)
    assert "source_watermark_end" not in execute_args(finish)[0][0].as_string()

    run, (_, _, finish, _), _, _, _, _ = flow(
        monkeypatch, tmp_path, canonical, pages=[[{"id": 1, "updated_at": U - 1}]],
        default_fields=False,
    )
    assert run() == (1, 1)
    assert "source_watermark_end" not in execute_args(finish)[0][0].as_string()

    def arbitrary_with_window(client, *, window):
        return [{"id": 2, "updated_at": U - 1}]

    run, (_, _, finish, _), _, _, _, _ = flow(
        monkeypatch, tmp_path, canonical, watermark=W, fetch=arbitrary_with_window,
    )
    assert run() == (1, 1)
    assert "source_watermark_end" not in execute_args(finish)[0][0].as_string()

    arbitrary = lambda client: [{"id": 2, "updated_at": U - 1}]
    start, raw, terminal = (connection() for _ in range(3))
    monkeypatch.setattr(pipeline, "create_connection", MagicMock(side_effect=[start, raw, terminal]))
    monkeypatch.setattr(pipeline, "get_source_watermark", MagicMock(side_effect=AssertionError))
    direct_logger = MagicMock()
    assert pipeline.ingest_entity(
        entity=GAMES, schema_name="custom_raw", output_path=tmp_path / "direct.jsonl",
        fetch_records=arbitrary, archive_records=canonical[2], ensure_table=canonical[3],
        upsert_records=canonical[4], logger=direct_logger,
    ) == (1, 1)
    assert "source_watermark_end" not in execute_args(terminal)[0][0].as_string()
    assert direct_logger.warning.call_args.args[2].endswith("no declared normal selection.")


def test_all_mode_has_independent_lookups_and_progress(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["run_ingestion", "--entity", "all", "--batch-size", "2"])
    monkeypatch.setattr(run_ingestion, "get_settings", lambda: Settings(postgres_schema="custom_raw"))
    monkeypatch.setattr(run_ingestion, "get_logger", lambda _: MagicMock())
    monkeypatch.setattr(pipeline, "datetime", FixedDatetime)
    histories = [None, None, None, W, W]
    connections = [connection(histories[i // 3]) for i in range(15)]
    monkeypatch.setattr(pipeline, "create_connection", MagicMock(side_effect=connections))
    client = MagicMock()
    client.query.side_effect = [[{"id": i, "updated_at": U - 1}] for i in range(5)]
    monkeypatch.setattr(pipeline, "create_igdb_client", MagicMock(return_value=client))

    run_ingestion.main()

    assert [call.args[0] for call in client.query.call_args_list] == [
        "games", "genres", "platforms", "companies", "involved_companies",
    ]
    assert ["where updated_at" in call.args[1] for call in client.query.call_args_list] == [
        False, False, False, True, True,
    ]
    for index, entity in enumerate(("games", "genres", "platforms", "companies", "involved_companies")):
        start, raw, finish = connections[index * 3:index * 3 + 3]
        assert start.commit.call_count == 2
        assert raw.commit.call_count == 2
        sql, params = execute_args(finish)[0]
        assert params[1:4] == ("succeeded", 1, 1)
        assert ("source_watermark_end" in sql.as_string()) == (entity in {
            "games", "companies", "involved_companies",
        })
        if entity in {"companies", "involved_companies"}:
            assert execute_args(start)[-1][1][-1] == datetime.fromtimestamp(L, timezone.utc)
        if index < 4:
            assert start.__exit__.called and finish.__exit__.called
    assert len(list((tmp_path / "data/raw").glob("*.jsonl"))) == 5


def test_bootstrap_overlap_and_no_change_keep_separate_cutoffs(monkeypatch, tmp_path):
    """Compose three invocations; supplied history models each prior committed end."""

    first = datetime(2026, 9, 26, 12, 0, 0, 900000, tzinfo=timezone.utc)
    second = first + timedelta(days=1)
    third = second + timedelta(days=1)
    history = None
    for index, (instant, pages) in enumerate((
        (first, [[{"id": 1, "updated_at": int(first.timestamp()) - 1}]]),
        (second, [[
            {"id": 1, "updated_at": int(first.timestamp()) - 86_400},
            {"id": 2, "updated_at": int(first.timestamp()) - 86_400},
        ], [{"id": 3, "updated_at": int(second.timestamp()) - 1}]]),
        (third, [[]]),
    )):
        class RunClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return instant

        run, (start, raw, finish, _), client, path, _, _ = flow(
            monkeypatch, tmp_path, COMPONENTS[0], watermark=history,
            pages=pages, batch_size=2,
        )
        monkeypatch.setattr(pipeline, "datetime", RunClock)
        assert run() == ((1, 1), (3, 3), (0, 0))[index]
        queries = [call.args[1] for call in client.query.call_args_list]
        assert [int(q.split("offset ")[1].split(";")[0]) for q in queries] == (
            [0], [0, 2], [0]
        )[index]
        if history is None:
            assert all("where updated_at" not in q for q in queries)
            assert "source_watermark_start" not in execute_args(start)[-1][0].as_string()
        else:
            lower = max(0, int(history.timestamp()) - 86_400)
            assert all(
                f"where updated_at >= {lower} & updated_at < {int(instant.timestamp())}; " in q
                for q in queries
            )
            assert execute_args(start)[-1][1][-1] == datetime.fromtimestamp(lower, timezone.utc)
        end = execute_args(finish)[0][1][-2]
        assert end == instant.replace(microsecond=0)
        history = end
        assert raw.__exit__.called and finish.commit.call_count == 1
        if index == 1:
            assert [json.loads(line)["id"] for line in path.read_text().splitlines()] == [1, 2, 3]
            assert [row[0] for row in raw.cursor.return_value.__enter__.return_value.executemany.call_args.args[1]] == [1, 2, 3]
        if index == 2:
            assert path.read_bytes() == b""
            assert raw.commit.call_count == 1


@pytest.mark.parametrize("watermark,instant,expected_lower", [
    (datetime(1970, 1, 1, 1, tzinfo=timezone.utc),
     datetime(1970, 1, 1, 1, 0, 1, 999999, tzinfo=timezone.utc), 0),
    (datetime(2026, 9, 28, 7, tzinfo=timezone(timedelta(hours=-5))),
     datetime(2026, 9, 28, 7, 0, 2, 999999, tzinfo=timezone(timedelta(hours=-5))),
     int(datetime(2026, 9, 28, 12, tzinfo=timezone.utc).timestamp()) - 86_400),
])
def test_runtime_converts_utc_and_clamps_epoch(monkeypatch, tmp_path, watermark, instant, expected_lower):
    class RunClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant

    cutoff = int(instant.timestamp())
    run, (start, _, finish, _), client, _, _, _ = flow(
        monkeypatch, tmp_path, COMPONENTS[1], watermark=watermark,
        pages=[[{"id": 1, "updated_at": expected_lower}]],
    )
    monkeypatch.setattr(pipeline, "datetime", RunClock)
    assert run() == (1, 1)
    assert f"updated_at >= {expected_lower} & updated_at < {cutoff}" in client.query.call_args.args[1]
    assert execute_args(start)[-1][1][-1] == datetime.fromtimestamp(expected_lower, timezone.utc)
    assert execute_args(finish)[0][1][-2] == datetime.fromtimestamp(cutoff, timezone.utc)


@pytest.mark.parametrize("stage,expected_counts", [
    ("source", (0, 0)), ("archive", (1, 0)),
    ("raw_ddl", (1, 0)), ("raw_upsert", (1, 0)),
])
def test_windowed_failure_keeps_acknowledged_counts_and_safe_summary(
    monkeypatch, tmp_path, stage, expected_counts
):
    error = RuntimeError("private payload and token")
    component = COMPONENTS[0]
    archive = MagicMock(side_effect=error) if stage == "archive" else None
    upsert = MagicMock(side_effect=error) if stage == "raw_upsert" else None
    if stage == "raw_ddl":
        component = (*component[:3], MagicMock(side_effect=error), component[4])
    run, (_, raw, finish, _), client, _, logger, _ = flow(
        monkeypatch, tmp_path, component, watermark=W, archive=archive, upsert=upsert,
    )
    if stage == "source":
        client.query.side_effect = error
    with pytest.raises(RuntimeError) as raised:
        run()
    assert raised.value is error
    report = raw if stage in {"source", "archive"} else finish
    assert execute_args(report)[0][1][1:4] == ("failed", *expected_counts)
    assert execute_args(report)[0][1][4] == (
        "JSONL archive failed." if stage == "archive" else
        "source fetch failed." if stage == "source" else "raw load failed."
    )
    assert "source_watermark_end" not in execute_args(report)[0][0].as_string()
    if stage in {"source", "archive"}:
        finish.__enter__.assert_not_called()
    else:
        assert raw.__exit__.called
    assert str(error) not in str(logger.mock_calls)


def test_all_mode_later_source_failure_retains_earlier_eligible_successes(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["run_ingestion", "--entity", "all", "--batch-size", "2"])
    monkeypatch.setattr(run_ingestion, "get_settings", lambda: Settings(postgres_schema="custom_raw"))
    monkeypatch.setattr(run_ingestion, "get_logger", lambda _: MagicMock())
    monkeypatch.setattr(pipeline, "datetime", FixedDatetime)
    connections = [connection(W) for _ in range(14)]
    connect = MagicMock(side_effect=connections)
    monkeypatch.setattr(pipeline, "create_connection", connect)
    client = MagicMock()
    error = RuntimeError("private source details")
    client.query.side_effect = [
        [{"id": 1, "updated_at": U - 1}], [{"id": 2}], [{"id": 3}],
        [{"id": 4, "updated_at": L}], error,
    ]
    monkeypatch.setattr(pipeline, "create_igdb_client", MagicMock(return_value=client))

    with pytest.raises(RuntimeError) as raised:
        run_ingestion.main()
    assert raised.value is error
    assert [call.args[0] for call in client.query.call_args_list] == [
        "games", "genres", "platforms", "companies", "involved_companies",
    ]
    for index in range(4):
        start, raw, finish = connections[index * 3:index * 3 + 3]
        assert start.commit.call_count == 2
        assert raw.commit.call_count == 2
        assert finish.commit.call_count == 1
        sql, params = execute_args(finish)[0]
        assert ("source_watermark_end" in sql.as_string()) == (index in {0, 3})
        if index in {0, 3}:
            assert params[-2] == NOW
    failed_start, failed_report = connections[12:]
    assert execute_args(failed_start)[-1][1][-1] == datetime.fromtimestamp(L, timezone.utc)
    assert execute_args(failed_report)[0][1][1:4] == ("failed", 0, 0)
    assert "source_watermark_end" not in execute_args(failed_report)[0][0].as_string()
    assert connect.call_count == 14
    assert len(list((tmp_path / "data/raw").glob("*.jsonl"))) == 4


def test_failed_window_retries_from_prior_progress_and_offset_zero(monkeypatch, tmp_path):
    record = {"id": 8, "updated_at": L, "detail": {"replayed": True}}
    failed_run, (_, raw, terminal, _), first_client, _, _, _ = flow(
        monkeypatch, tmp_path, COMPONENTS[2], watermark=W, pages=[[record]],
    )
    error = RuntimeError("raw context failed")
    raw.__exit__.side_effect = error
    with pytest.raises(RuntimeError) as raised:
        failed_run()
    assert raised.value is error
    assert execute_args(terminal)[0][1][1:4] == ("failed", 1, 1)
    assert "source_watermark_end" not in execute_args(terminal)[0][0].as_string()

    retry, (start, _, finish, _), second_client, path, _, _ = flow(
        monkeypatch, tmp_path, COMPONENTS[2], watermark=W, pages=[[record]],
    )
    assert retry() == (1, 1)
    assert first_client.query.call_args.args[1] == second_client.query.call_args.args[1]
    assert "offset 0;" in second_client.query.call_args.args[1]
    assert execute_args(start)[-1][1][-1] == datetime.fromtimestamp(L, timezone.utc)
    assert execute_args(finish)[0][1][-2] == NOW
    assert json.loads(path.read_text()) == record
