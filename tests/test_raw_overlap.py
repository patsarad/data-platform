"""Overlap SQL/row preparation only: mocks execute neither IGDB filters nor SQL."""

import json
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from psycopg.types.json import Jsonb

from src.entities import COMPANIES, GAMES, INVOLVED_COMPANIES
from src.ingestion.fetch_companies import fetch_companies_batches
from src.ingestion.fetch_games import fetch_games_batches
from src.ingestion.fetch_involved_companies import fetch_involved_companies_batches
from src.ingestion.windows import calculate_source_window
from src.storage.raw_companies import upsert_raw_companies
from src.storage.raw_games import upsert_raw_games
from src.storage.raw_involved_companies import upsert_raw_involved_companies


FIRST_FETCH = datetime(2026, 9, 26, 12, tzinfo=timezone.utc)
SECOND_FETCH = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
TIED_UPDATE = 1790380800  # Within both explicitly supplied windows.


@pytest.fixture(params=[
    (GAMES, fetch_games_batches, upsert_raw_games),
    (COMPANIES, fetch_companies_batches, upsert_raw_companies),
    (INVOLVED_COMPANIES, fetch_involved_companies_batches, upsert_raw_involved_companies),
], ids=["games", "companies", "involved_companies"])
def supported(request):
    return request.param


def payload(entity, record_id, **changes):
    """Include nested source data and entity-specific relationships without expansion."""

    record = {
        "id": record_id, "updated_at": TIED_UPDATE,
        "extra": {"values": [False, None, "é", {"ids": [3, 1, 3]}]},
    }
    if entity is INVOLVED_COMPANIES:
        # Different relationship IDs deliberately share the same reference pair.
        record.update(game=9001, company=8001, developer=False, publisher=False)
    else:
        record.update(name="Original é", slug="original")
        if entity is GAMES:
            record.update(genres=[31, 12, 31], platforms=[], involved_companies=[901, 900])
    record.update(changes)
    return record


def assert_prepared_call(entity, captured, expected, fetched_at):
    """Check the emitted unconditional ID upsert and every bound row, not stored state."""

    statement, rows = captured.args
    rendered = statement if isinstance(statement, str) else statement.as_string()
    # Retain the loaders' existing identifier styles and complete UPDATE clauses.
    if entity is GAMES:
        target, key, columns = "analytics.raw_games", "igdb_id", " igdb_id, name, slug, payload, fetched_at "
    elif entity is COMPANIES:
        target, key, columns = '"analytics"."raw_companies"', '"igdb_id"', '"igdb_id", name, slug, payload, fetched_at'
    else:
        target, key, columns = '"analytics"."raw_involved_companies"', '"igdb_id"', '"igdb_id", payload, fetched_at'
    named = entity is not INVOLVED_COMPANIES
    values = "%s, %s, %s, %s, %s" if named else "%s, %s, %s"
    updates = "name = EXCLUDED.name, slug = EXCLUDED.slug, " if named else ""
    assert " ".join(rendered.split()) == (
        f"INSERT INTO {target} ({columns}) VALUES ({values}) "
        f"ON CONFLICT ({key}) DO UPDATE SET {updates}"
        "payload = EXCLUDED.payload, fetched_at = EXCLUDED.fetched_at;"
    )
    assert entity.source_primary_key == "id"
    assert entity.raw_primary_key == "igdb_id"
    assert len(rows) == len(expected)
    assert [row[0] for row in rows] == [record["id"] for record in expected]
    assert all(len(row) == (5 if named else 3) for row in rows)
    assert all(isinstance(row[-2], Jsonb) for row in rows)
    assert [json.loads(json.dumps(row[-2].obj)) for row in rows] == expected
    assert [row[-1] for row in rows] == [fetched_at] * len(expected)
    if named:
        assert [row[1:3] for row in rows] == [
            (record.get("name"), record.get("slug")) for record in expected
        ]


@pytest.mark.parametrize("timestamp", [
    {"updated_at": TIED_UPDATE}, {"updated_at": TIED_UPDATE + 1},
    {"updated_at": TIED_UPDATE - 1}, {}, {"updated_at": None},
], ids=["same", "newer", "stale", "missing", "null"])
def test_overlapping_fetches_prepare_replays_by_id(supported, timestamp):
    """Replay changed records with the same key even for stale/absent source times.

    The queued missing/null responses test fidelity, not IGDB window selection.
    Supplying a hypothetical prior cutoff here does not persist a watermark.
    """

    entity, fetch, upsert = supported
    windows = [
        calculate_source_window(datetime(2026, 9, 25, 12, tzinfo=timezone.utc),
                                run_started_at=FIRST_FETCH),
        calculate_source_window(FIRST_FETCH, run_started_at=SECOND_FETCH),
    ]
    assert windows[0].lower_bound < windows[1].lower_bound < TIED_UPDATE < windows[0].upper_bound
    replay = payload(entity, 101, extra={"replacement": [None, False]})
    if entity is INVOLVED_COMPANIES:
        replay.update(company=8002, developer=True)
    else:
        replay.update(name=None, slug="changed")
        if entity is GAMES:
            replay.update(genres=None, platforms=[6], involved_companies=[])
    replay.pop("updated_at")
    replay.update(timestamp)
    extractions = [
        [payload(entity, 101), payload(entity, 102)],
        [replay, payload(entity, 102), payload(entity, 103)],
    ]
    original = deepcopy(extractions)
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    # Driver rowcount is deliberately unrelated to acknowledged input-row count.
    cursor.rowcount = -1
    events = MagicMock()
    events.attach_mock(cursor.executemany, "upsert")
    events.attach_mock(connection.commit, "commit")

    for index, (window, records, fetched_at) in enumerate(
        zip(windows, extractions, (FIRST_FETCH, SECOND_FETCH))
    ):
        client = MagicMock()
        client.query.side_effect = [[record] for record in records] + [[]]
        fetched = fetch(client, batch_size=1, window=window)
        assert fetched == original[index]
        assert upsert(connection, fetched, "analytics", fetched_at) == len(records)
        assert_prepared_call(entity, cursor.executemany.call_args, original[index], fetched_at)
        assert [call.args for call in client.query.call_args_list] == [
            (entity.endpoint, f"fields {', '.join(entity.fields)}; "
             f"where updated_at >= {window.lower_bound} & updated_at < {window.upper_bound}; "
             f"sort id asc; limit 1; offset {offset};")
            for offset in range(len(records) + 1)
        ]

    assert extractions == original
    assert [call[0] for call in events.mock_calls] == ["upsert", "commit", "upsert", "commit"]
    cursor.execute.assert_not_called()  # No identity/version SELECT or extra SQL.
    connection.rollback.assert_not_called()
    connection.__enter__.assert_not_called()  # Caller still owns the connection context.


def test_repeated_ids_keep_input_order_and_all_payload_versions(supported):
    """No sorting/deduplication or timestamp preference precedes executemany.

    Ordered parameters plus unconditional SQL request last-upsert behavior; this
    test does not simulate a PostgreSQL table or assert database final state.
    """

    entity, _, upsert = supported
    records = [
        payload(entity, 202), payload(entity, 101),
        payload(entity, 202, name="Same second, changed", company=8002),
        payload(entity, 202, updated_at=TIED_UPDATE - 1, name="Stale last", slug=None),
        {"id": 101, "updated_at": None, "developer": False, "publisher": False},
        {"id": 202},
    ]
    original = deepcopy(records)
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.rowcount = 2  # Two distinct IDs still acknowledge six input rows.

    assert upsert(connection, iter(records), "analytics", SECOND_FETCH) == 6

    cursor.executemany.assert_called_once()
    assert_prepared_call(entity, cursor.executemany.call_args, original, SECOND_FETCH)
    assert records == original
    connection.commit.assert_called_once_with()
    cursor.execute.assert_not_called()
