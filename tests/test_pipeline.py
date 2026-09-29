"""Tests for calling reusable ingestion independently of CLI parsing."""

import json
from copy import deepcopy
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import psycopg
import pytest

from src.entities import COMPANIES, GAMES, GENRES, INVOLVED_COMPANIES, PLATFORMS
from src.ingestion import pipeline
from src.ingestion.client import IGDBClientError
from src.ingestion.fetch_games import build_games_query, fetch_games_batches, save_games_to_jsonl
from src.ingestion.fetch_genres import build_genres_query, fetch_genres_batches, save_genres_to_jsonl
from src.ingestion.fetch_platforms import (
    build_platforms_query, fetch_platforms_batches, save_platforms_to_jsonl,
)
from src.ingestion.fetch_companies import (
    build_companies_query, fetch_companies_batches, save_companies_to_jsonl,
)
from src.ingestion.fetch_involved_companies import (
    build_involved_companies_query, fetch_involved_companies_batches, save_involved_companies_to_jsonl,
)
from src.storage.raw_involved_companies import (
    ensure_raw_involved_companies_table, upsert_raw_involved_companies,
)
from src.storage.raw_companies import ensure_raw_companies_table, upsert_raw_companies
from src.storage.raw_games import ensure_raw_games_table, upsert_raw_games
from src.storage.raw_genres import ensure_raw_genres_table, upsert_raw_genres
from src.storage.raw_platforms import ensure_raw_platforms_table, upsert_raw_platforms


def test_ingest_entity_uses_supplied_operations(monkeypatch) -> None:
    """Run without CLI/settings access and preserve records and acknowledged counts."""

    monkeypatch.setattr("sys.argv", ["unrelated-command", "--not-an-ingestion-option"])
    connections = [MagicMock() for _ in range(3)]
    for connection in connections:
        connection.__enter__.return_value = connection
    monkeypatch.setattr(pipeline, "create_connection", MagicMock(side_effect=connections))
    client_factory = MagicMock()
    monkeypatch.setattr(pipeline, "create_igdb_client", client_factory)
    metadata = {}
    for name in ("ensure_ingestion_runs_table", "start_ingestion_run", "succeed_ingestion_run"):
        metadata[name] = MagicMock()
        monkeypatch.setattr(pipeline, name, metadata[name])
    records = [{"id": 1}, {"id": 2}]
    fetch = MagicMock(return_value=records)
    archive = MagicMock(return_value=2)
    ensure = MagicMock()
    upsert = MagicMock(return_value=1)
    output_path = Path("custom/games.jsonl")

    before = datetime.now(timezone.utc)
    counts = pipeline.ingest_entity(
        entity=GAMES,
        schema_name="custom_raw",
        output_path=output_path,
        fetch_records=fetch,
        archive_records=archive,
        ensure_table=ensure,
        upsert_records=upsert,
        logger=MagicMock(),
    )
    after = datetime.now(timezone.utc)

    assert counts == (2, 1)
    fetch.assert_called_once_with(client_factory.return_value)
    archive.assert_called_once_with(records, output_path)
    ensure.assert_called_once_with(connections[1], "custom_raw")
    upsert.assert_called_once()
    raw_connection, loaded_records, schema, fetched_at = upsert.call_args.args
    assert raw_connection is connections[1]
    assert loaded_records is records
    assert schema == "custom_raw"
    assert before <= fetched_at <= after
    assert fetched_at.tzinfo == timezone.utc
    metadata["start_ingestion_run"].assert_called_once_with(connections[0], "custom_raw", "games")
    metadata["succeed_ingestion_run"].assert_called_once_with(
        connections[2], "custom_raw", metadata["start_ingestion_run"].return_value, 2, 1
    )
    for connection in connections:
        connection.__exit__.assert_called_once_with(None, None, None)


@pytest.fixture(params=["games", "genres", "platforms", "companies", "involved_companies"])
def entity_pipeline(request, monkeypatch, tmp_path):
    """Compose real entity/metadata helpers; fake only API and database boundaries."""

    if request.param == "games":
        entity, build_query, fetch, archive, ensure, upsert = (
            GAMES, build_games_query, fetch_games_batches, save_games_to_jsonl,
            ensure_raw_games_table, upsert_raw_games,
        )
    elif request.param == "genres":
        entity, build_query, fetch, archive, ensure, upsert = (
            GENRES, build_genres_query, fetch_genres_batches, save_genres_to_jsonl,
            ensure_raw_genres_table, upsert_raw_genres,
        )
    elif request.param == "platforms":
        entity, build_query, fetch, archive, ensure, upsert = (
            PLATFORMS, build_platforms_query, fetch_platforms_batches, save_platforms_to_jsonl,
            ensure_raw_platforms_table, upsert_raw_platforms,
        )
    elif request.param == "companies":
        entity, build_query, fetch, archive, ensure, upsert = (
            COMPANIES, build_companies_query, fetch_companies_batches, save_companies_to_jsonl,
            ensure_raw_companies_table, upsert_raw_companies,
        )

    else:
        entity, build_query, fetch, archive, ensure, upsert = (
            INVOLVED_COMPANIES, build_involved_companies_query,
            fetch_involved_companies_batches, save_involved_companies_to_jsonl,
            ensure_raw_involved_companies_table, upsert_raw_involved_companies,
        )

    start, raw, finish = [MagicMock() for _ in range(3)]
    for connection in (start, raw, finish):
        connection.__enter__.return_value = connection
        connection.cursor.return_value.__enter__.return_value.rowcount = 1
    connect = MagicMock(side_effect=[start, raw, finish])
    monkeypatch.setattr(pipeline, "create_connection", connect)
    client = MagicMock()
    client_factory = MagicMock(return_value=client)
    monkeypatch.setattr(pipeline, "create_igdb_client", client_factory)
    events = MagicMock()
    for name, operation in (
        ("start_commit", start.commit), ("start_exit", start.__exit__),
        ("client", client_factory), ("query", client.query),
        ("raw_commit", raw.commit), ("raw_exit", raw.__exit__),
        ("finish", finish.cursor.return_value.__enter__.return_value.execute),
        ("finish_commit", finish.commit),
    ):
        events.attach_mock(operation, name)
    output_path = tmp_path / "archive" / f"{entity.endpoint}.jsonl"
    logger = MagicMock()
    run = partial(
        pipeline.ingest_entity,
        entity=entity,
        schema_name="custom_raw",
        output_path=output_path,
        fetch_records=partial(fetch, batch_size=2),
        archive_records=archive,
        ensure_table=ensure,
        upsert_records=upsert,
        logger=logger,
    )
    return SimpleNamespace(
        entity=entity, build_query=build_query, run=run, client=client, connect=connect, start=start, raw=raw,
        finish=finish, output_path=output_path, events=events, logger=logger,
    )


def assert_run_completion(flow, status, fetched, loaded, message) -> None:
    """Check real metadata helpers pair start/finish for the same run without watermarks."""

    start_cursor = flow.start.cursor.return_value.__enter__.return_value
    start_sql, (run_id, entity, started_at) = start_cursor.execute.call_args.args
    assert "'running'" in start_sql.as_string()
    assert entity == flow.entity.endpoint
    finish_cursor = flow.finish.cursor.return_value.__enter__.return_value
    finish_cursor.execute.assert_called_once()
    finish_sql, (completed_at, *terminal) = finish_cursor.execute.call_args.args
    assert terminal == [status, fetched, loaded, message, run_id]
    assert completed_at >= started_at
    assert "AND status = 'running'" in finish_sql.as_string()
    assert "watermark" not in start_sql.as_string() + finish_sql.as_string()
    assert flow.start.commit.call_count == 2
    flow.finish.commit.assert_called_once_with()
    flow.start.__exit__.assert_called_once_with(None, None, None)
    flow.finish.__exit__.assert_called_once_with(None, None, None)


@pytest.mark.parametrize("entity_pipeline", ["games"], indirect=True)
@pytest.mark.parametrize(
    "relationships",
    [
        {"genres": [31, 12, 31], "platforms": [167, 6], "involved_companies": [90002, 90001]},
        {},
        {"genres": [], "platforms": [], "involved_companies": []},
        {"genres": None, "platforms": [], "involved_companies": [90002]},
    ],
    ids=["ids-in-source-order", "missing", "empty-arrays", "mixed-null-empty-ids"],
)
def test_games_relationship_payload_survives_pipeline(entity_pipeline, relationships) -> None:
    """Preserve source states and extra data without resolving or normalizing IDs."""

    flow = entity_pipeline
    records = [
        {"id": 101, "name": "Jeu é", "slug": "jeu", "rating": 0,
         "updated_at": 1776470400, "extra": {"values": [False, None, "é"]},
         **relationships},
        {"id": 102},
        {"id": 103, "genres": [], "involved_companies": [90003]},
    ]
    expected = deepcopy(records)
    flow.client.query.side_effect = [records[:2], records[2:]]

    assert flow.run() == (3, 3)

    fields = (
        "fields id, name, slug, first_release_date, rating, rating_count, "
        "total_rating, total_rating_count, updated_at, genres, platforms, involved_companies; "
    )
    assert [call.args for call in flow.client.query.call_args_list] == [
        ("games", fields + f"sort id asc; limit 2; offset {offset};")
        for offset in (0, 2)
    ]
    assert [json.loads(line) for line in flow.output_path.read_text().splitlines()] == expected
    cursor = flow.raw.cursor.return_value.__enter__.return_value
    cursor.executemany.assert_called_once()
    statement, rows = cursor.executemany.call_args.args
    assert [row[:3] for row in rows] == [(101, "Jeu é", "jeu"), (102, None, None), (103, None, None)]
    assert all(len(row) == 5 for row in rows)
    assert [json.loads(json.dumps(row[3].obj)) for row in rows] == expected
    assert records == expected  # No source mutations, defaults, sorting, or deduplication.
    assert "payload = EXCLUDED.payload" in statement
    assert "ON CONFLICT (igdb_id)" in statement
    assert_run_completion(flow, "succeeded", 3, 3, None)
    assert flow.raw.commit.call_count == 2
    events = [call[0] for call in flow.events.mock_calls]
    assert events.index("start_exit") < events.index("client")
    assert events.index("raw_exit") < events.index("finish")


@pytest.mark.parametrize(
    "records",
    [
        [],
        [
            {"id": 7, "name": "Original", "slug": "original", "nested": {"values": [1, None]}},
            {"id": 7, "name": "Updated", "updated_at": 1776470400},
        ],
    ],
    ids=["empty-first-page", "full-page-then-empty-with-repeated-id"],
)
def test_entity_pipeline_archives_and_loads_completed_pagination(entity_pipeline, records) -> None:
    """Carry real pagination results through JSONL, row preparation, and success counts."""

    flow = entity_pipeline
    if records and flow.entity is INVOLVED_COMPANIES:
        records = [
            {"id": 7, "game": 101, "company": 202, "developer": True, "publisher": False},
            {"id": 7, "game": 101, "company": 203, "developer": False, "publisher": True,
             "updated_at": 1776470400, "extra": {"values": [None, "Rôle"]}},
        ]
    pages = [records, []] if records else [[]]
    flow.client.query.side_effect = pages

    assert flow.run() == (len(records), len(records))

    assert [call.args for call in flow.client.query.call_args_list] == [
        (flow.entity.endpoint, flow.build_query(limit=2, offset=2 * page)) for page in range(len(pages))
    ]
    assert [json.loads(line) for line in flow.output_path.read_text().splitlines()] == records
    cursor = flow.raw.cursor.return_value.__enter__.return_value
    assert cursor.execute.call_count == 2  # Ensure the raw table even for an empty fetch.
    if records:
        cursor.executemany.assert_called_once()
        _, rows = cursor.executemany.call_args.args
        if flow.entity is INVOLVED_COMPANIES:
            assert [row[0] for row in rows] == [7, 7]
            assert all(len(row) == 3 for row in rows)
        else:
            assert [row[:3] for row in rows] == [(7, "Original", "original"), (7, "Updated", None)]
        assert all(isinstance(row[-2], psycopg.types.json.Jsonb) for row in rows)
        assert [row[-2].obj for row in rows] == records
        assert rows[0][-1] == rows[1][-1]
        assert rows[0][-1].tzinfo == timezone.utc
    else:
        assert flow.output_path.read_bytes() == b""
        cursor.executemany.assert_not_called()
    assert_run_completion(flow, "succeeded", len(records), len(records), None)
    assert [call[0] for call in flow.events.mock_calls] == [
        "start_commit", "start_commit", "start_exit", "client",
        *(["query"] * len(pages)), "raw_commit",
        *(["raw_commit"] if records else []), "raw_exit", "finish", "finish_commit",
    ]
    assert flow.connect.call_count == 3


def test_entity_pipeline_later_page_failure_keeps_zero_counts(entity_pipeline) -> None:
    """A partial fetch is neither archived nor loaded nor acknowledged in metadata."""

    flow = entity_pipeline
    error = IGDBClientError("Later page failed")
    flow.client.query.side_effect = [[{"id": 1}, {"id": 2}], error]
    flow.connect.side_effect = [flow.start, flow.finish]

    with pytest.raises(IGDBClientError) as raised:
        flow.run()

    assert raised.value is error
    assert flow.client.query.call_count == 2
    assert not flow.output_path.exists()
    flow.raw.__enter__.assert_not_called()
    assert flow.connect.call_count == 2
    assert_run_completion(flow, "failed", 0, 0, "source fetch failed.")


def test_entity_pipeline_invalid_row_preserves_archive_but_skips_upsert(entity_pipeline) -> None:
    """A missing ID after a valid row fails preparation before any payload is written."""

    flow = entity_pipeline
    records = [{"id": 1}, {"name": "Missing ID"}]
    flow.client.query.side_effect = [records, []]

    with pytest.raises(KeyError, match="id") as raised:
        flow.run()

    assert [json.loads(line) for line in flow.output_path.read_text().splitlines()] == records
    cursor = flow.raw.cursor.return_value.__enter__.return_value
    cursor.executemany.assert_not_called()
    flow.raw.commit.assert_called_once_with()  # Only the DDL was committed.
    assert flow.raw.__exit__.call_args.args[1] is raised.value
    assert_run_completion(flow, "failed", 2, 0, "raw load failed.")


def test_entity_pipeline_raw_exit_failure_retains_acknowledged_load_count(entity_pipeline) -> None:
    """A context-exit failure cannot report success or discard the loader's returned count."""

    flow = entity_pipeline
    flow.client.query.side_effect = [[{"id": 1}]]
    error = psycopg.OperationalError("sensitive-connection-details")
    flow.raw.__exit__.side_effect = error

    with pytest.raises(psycopg.OperationalError) as raised:
        flow.run()

    assert raised.value is error
    assert flow.raw.commit.call_count == 2
    flow.raw.__exit__.assert_called_once_with(None, None, None)
    assert_run_completion(flow, "failed", 1, 1, "raw load failed.")
    assert [call[0] for call in flow.events.mock_calls][-3:] == ["raw_exit", "finish", "finish_commit"]
    assert str(error) not in str(flow.logger.mock_calls)
