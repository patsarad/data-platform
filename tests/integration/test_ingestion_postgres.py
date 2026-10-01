"""Real raw/metadata transactions with deterministic source pages, never live IGDB."""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from functools import partial
from types import SimpleNamespace

import psycopg
import pytest

from src.entities import COMPANIES, GAMES, INVOLVED_COMPANIES
from src.ingestion import pipeline
from src.ingestion.fetch_companies import fetch_companies_batches, save_companies_to_jsonl
from src.ingestion.fetch_games import fetch_games_batches, save_games_to_jsonl
from src.ingestion.fetch_involved_companies import (
    fetch_involved_companies_batches, save_involved_companies_to_jsonl,
)
from src.ingestion.windows import SourceWindow
from src.storage.ingestion_runs import get_source_watermark
from src.storage.raw_companies import ensure_raw_companies_table, upsert_raw_companies
from src.storage.raw_games import create_connection, ensure_raw_games_table, upsert_raw_games
from src.storage.raw_involved_companies import (
    ensure_raw_involved_companies_table, upsert_raw_involved_companies,
)


COMPONENTS = (
    (GAMES, fetch_games_batches, save_games_to_jsonl, ensure_raw_games_table, upsert_raw_games),
    (COMPANIES, fetch_companies_batches, save_companies_to_jsonl,
     ensure_raw_companies_table, upsert_raw_companies),
    (INVOLVED_COMPANIES, fetch_involved_companies_batches, save_involved_companies_to_jsonl,
     ensure_raw_involved_companies_table, upsert_raw_involved_companies),
)
START = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)


class Source:
    """Interpret generated time predicates and offsets over a fixed five-row source."""

    def __init__(self):
        self.rows = [
            {"id": key, "updated_at": int(START.timestamp()) - 100, "name": f"Row {key}"}
            for key in range(1, 6)
        ]

    def query(self, endpoint, statement):
        rows = self.rows
        bounds = re.search(r"where updated_at >= (\d+) & updated_at < (\d+)", statement)
        if bounds:
            lower, upper = map(int, bounds.groups())
            rows = [row for row in rows if lower <= row["updated_at"] < upper]
        limit = int(re.search(r"limit (\d+)", statement)[1])
        offset = int(re.search(r"offset (\d+)", statement)[1])
        return rows[offset:offset + limit]


@pytest.fixture(params=COMPONENTS, ids=lambda component: component[0].endpoint)
def scenario(request, monkeypatch, postgres_schemas, tmp_path):
    """Use production fetch/archive/load helpers with actual PostgreSQL connections."""

    entity, fetch, archive, ensure, upsert = request.param
    schema, _ = postgres_schemas
    source = Source()

    class Clock(datetime):
        at = START

        @classmethod
        def now(cls, tz=None):
            return cls.at

    monkeypatch.setattr(pipeline, "datetime", Clock)
    monkeypatch.setattr(pipeline, "create_igdb_client", lambda: source)
    sequence = 0

    def query(statement, parameters=None):
        with create_connection() as connection:
            return connection.execute(statement, parameters).fetchall()

    def rows():
        return query(f"SELECT igdb_id, payload, fetched_at FROM {schema}.{entity.raw_table} ORDER BY igdb_id")

    def last_run():
        # Metadata completion uses the real clock, including backfill starts.
        return query(f"""SELECT status, records_fetched, records_loaded,
            source_watermark_start, source_watermark_end FROM {schema}.ingestion_runs
            ORDER BY completed_at DESC NULLS LAST LIMIT 1""")[0]

    def watermark():
        with create_connection() as connection:
            return get_source_watermark(connection, schema, entity.endpoint)

    def run(mode="normal", cap=None, backfill=None):
        nonlocal sequence
        sequence += 1
        path = tmp_path / f"{sequence}.jsonl"
        result = pipeline.ingest_entity(
            entity=entity, schema_name=schema, output_path=path,
            fetch_records=partial(fetch, batch_size=2, max_batches=cap),
            archive_records=archive, ensure_table=ensure, upsert_records=upsert,
            logger=logging.getLogger(__name__),
            selection=pipeline.RunSelection(2, cap, True, mode, backfill),
        )
        payloads = {key: payload for key, payload, _ in rows()}
        archived = [json.loads(line) for line in path.read_text().splitlines()]
        assert all(payloads[row["id"]] == row for row in archived)
        return result

    return SimpleNamespace(
        source=source, clock=Clock, schema=schema, query=query, rows=rows,
        last_run=last_run, watermark=watermark, run=run,
    )


def test_bootstrap_overlap_and_empty_run(scenario):
    """Observe committed progress and duplicate-safe changes from fresh connections."""

    s = scenario
    assert s.run() == (5, 5)
    assert s.watermark() == START
    first_rows = s.rows()
    s.clock.at += timedelta(seconds=2)
    s.source.rows[0]["name"] = "Changed"
    s.source.rows.append({"id": 6, "updated_at": int(s.clock.at.timestamp()) - 1})
    assert s.run() == (6, 6)
    assert len(s.rows()) == 6
    assert s.rows()[0][1]["name"] == "Changed"
    assert all(new[2] > old[2] for old, new in zip(first_rows, s.rows()))
    assert s.last_run()[3:] == (START - timedelta(days=1), s.clock.at)
    s.clock.at += timedelta(days=2)
    assert s.run() == (6, 6)  # Last overlap still includes these records.
    s.clock.at += timedelta(days=2)
    assert s.run() == (0, 0)
    assert s.watermark() == s.clock.at
    assert s.last_run()[:3] == ("succeeded", 0, 0)


def test_cap_backfill_and_full_refresh(scenario):
    """Modes preserve or advance persisted progress without deleting old raw rows."""

    s = scenario
    s.run()
    s.clock.at += timedelta(seconds=2)
    assert s.run(cap=1) == (2, 2)
    assert s.watermark() == START
    assert s.last_run()[4] is None
    s.clock.at += timedelta(seconds=2)
    lower = int(START.timestamp()) - 1000
    upper = int(s.clock.at.timestamp())
    assert s.run("backfill", backfill=SourceWindow(lower, upper)) == (5, 5)
    assert s.last_run()[3:] == (datetime.fromtimestamp(lower, timezone.utc), None)
    assert s.watermark() == START
    s.clock.at += timedelta(seconds=2)
    s.source.rows[0]["updated_at"] = 1
    assert s.run("full_refresh") == (5, 5)
    assert len(s.rows()) == 5
    assert s.watermark() == s.clock.at
    assert s.last_run()[3] is None


def test_raw_sql_failure_rolls_back_and_retains_checkpoint(scenario):
    """A real bigint conversion error rolls back the preceding write in that batch."""

    s = scenario
    s.run()
    before = s.rows()
    s.clock.at += timedelta(seconds=2)
    s.source.rows = [
        {"id": 1, "updated_at": int(START.timestamp()), "name": "Must roll back"},
        {"id": "invalid-bigint", "updated_at": int(START.timestamp())},
    ]
    with pytest.raises(psycopg.errors.InvalidTextRepresentation):
        s.run()
    assert s.rows() == before
    assert s.watermark() == START
    assert s.last_run()[:3] == ("failed", 2, 0)
    assert s.last_run()[4] is None


def test_terminal_sql_failure_retains_raw_commit_and_retry_replays(scenario):
    """Reject success in PostgreSQL, then verify safe recovery from the prior end."""

    s = scenario
    s.run()
    s.clock.at += timedelta(seconds=2)
    s.source.rows.append({"id": 6, "updated_at": int(s.clock.at.timestamp()) - 1})
    with create_connection() as connection:
        connection.execute(f"""CREATE FUNCTION {s.schema}.reject_success() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
            IF NEW.status = 'succeeded' THEN RAISE EXCEPTION 'test terminal failure'; END IF;
            RETURN NEW; END $$""")
        connection.execute(f"""CREATE TRIGGER reject_success BEFORE UPDATE ON
            {s.schema}.ingestion_runs FOR EACH ROW EXECUTE FUNCTION {s.schema}.reject_success()""")
    with pytest.raises(psycopg.errors.RaiseException):
        s.run()
    assert len(s.rows()) == 6
    assert s.watermark() == START
    assert s.last_run()[:3] == ("failed", 6, 6)
    assert s.last_run()[4] is None
    with create_connection() as connection:
        connection.execute(f"DROP TRIGGER reject_success ON {s.schema}.ingestion_runs")
    s.clock.at += timedelta(seconds=2)
    assert s.run() == (6, 6)
    assert len(s.rows()) == 6
    assert s.watermark() == s.clock.at


def test_error_after_terminal_commit_cannot_replace_success(scenario, monkeypatch):
    """Simulate lost acknowledgment after an actual commit, not a network outage."""

    s = scenario
    succeed = pipeline.succeed_ingestion_run

    def lose_acknowledgment(*args, **kwargs):
        succeed(*args, **kwargs)
        raise RuntimeError("Simulated acknowledgment failure")

    monkeypatch.setattr(pipeline, "succeed_ingestion_run", lose_acknowledgment)
    with pytest.raises(RuntimeError, match="Simulated acknowledgment failure"):
        s.run()
    assert len(s.rows()) == 5
    assert s.watermark() == START
    assert s.last_run()[:3] == ("succeeded", 5, 5)
