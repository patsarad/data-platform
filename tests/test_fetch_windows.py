"""Assert query construction and payload fidelity; fakes do not filter IGDB data."""

from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.ingestion.client import IGDBClientError
from src.ingestion.fetch_companies import build_companies_query, fetch_companies_batches
from src.ingestion.fetch_games import build_games_query, fetch_games_batches
from src.ingestion.fetch_genres import build_genres_query, fetch_genres_batches
from src.ingestion.fetch_involved_companies import (
    build_involved_companies_query, fetch_involved_companies_batches,
)
from src.ingestion.fetch_platforms import build_platforms_query, fetch_platforms_batches
from src.ingestion.windows import SourceWindow, calculate_source_window


WINDOW = calculate_source_window(
    datetime(2026, 9, 25, 12, tzinfo=timezone.utc),
    run_started_at=datetime(2026, 9, 26, 12, 0, 0, 999999, tzinfo=timezone.utc),
)
BOOTSTRAP = calculate_source_window(
    None, run_started_at=datetime(2026, 9, 26, 12, tzinfo=timezone.utc),
)
PREDICATE = "where updated_at >= 1790251200 & updated_at < 1790424000; "


@pytest.fixture(params=[
    ("games", build_games_query, fetch_games_batches,
     "id, name, slug, first_release_date, rating, rating_count, total_rating, "
     "total_rating_count, updated_at, genres, platforms, involved_companies"),
    ("companies", build_companies_query, fetch_companies_batches, "id, name, slug, updated_at"),
    ("involved_companies", build_involved_companies_query, fetch_involved_companies_batches,
     "id, game, company, developer, publisher, updated_at"),
], ids=["games", "companies", "involved_companies"])
def supported(request):
    return request.param


def test_exact_queries_without_window_and_unfiltered_bootstrap(supported) -> None:
    """No window or no history preserves the entire original query string."""

    endpoint, build, fetch, fields = supported
    expected = f"fields {fields}; sort id asc; limit 500; offset 0;"
    assert build(limit=500, offset=0) == expected
    for window in (None, BOOTSTRAP):
        assert build(limit=500, offset=0, window=window) == expected
        client = MagicMock()
        # Bootstrap must not discard old, absent, or post-cutoff update times.
        records = [{"id": 1, "updated_at": 0}, {"id": 2},
                   {"id": 3, "updated_at": None}, {"id": 4, "updated_at": 1790424001}]
        client.query.return_value = records
        assert fetch(client, window=window) == records
        client.query.assert_called_once_with(endpoint, expected)


def test_windowed_query_has_inclusive_lower_exclusive_upper(supported) -> None:
    _, build, _, fields = supported
    assert build(limit=250, offset=500, window=WINDOW) == (
        f"fields {fields}; {PREDICATE}sort id asc; limit 250; offset 500;"
    )
    assert build(limit=1, offset=0, fields=["name"], window=SourceWindow(0, 1)) == (
        "fields name; where updated_at >= 0 & updated_at < 1; sort id asc; limit 1; offset 0;"
    )


def test_frozen_bounds_and_complete_payloads_across_pages(supported) -> None:
    """Queued records are deliberately unfiltered; no local timestamp gate exists."""

    endpoint, _, fetch, fields = supported
    records = [
        {"id": 1, "updated_at": 1790251200, "extra": {"values": [False, None, "é"]}},
        {"id": 2, "updated_at": 1790251200},  # Tied lower-bound second across pages.
        {"id": 3},
        {"id": 4, "updated_at": None},
        {"id": 5, "updated_at": 1790424000},  # Would be excluded by a conforming API.
        {"id": 6, "updated_at": "unexpected"},
    ]
    original = deepcopy(records)
    client = MagicMock()
    client.query.side_effect = [[record] for record in records] + [[]]

    result = fetch(client, batch_size=1, window=WINDOW)

    assert result == original == records
    assert all(actual is source for actual, source in zip(result, records))
    assert [call.args for call in client.query.call_args_list] == [
        (endpoint, f"fields {fields}; {PREDICATE}sort id asc; limit 1; offset {offset};")
        for offset in range(7)
    ]


@pytest.mark.parametrize("window", [None, BOOTSTRAP, WINDOW], ids=["default", "bootstrap", "window"])
@pytest.mark.parametrize("field_type", [tuple, list, iter], ids=["tuple", "list", "iterator"])
def test_exact_custom_projection_across_pages(supported, window, field_type) -> None:
    endpoint, _, fetch, _ = supported
    client = MagicMock()
    client.query.side_effect = [[{"id": 1}], [{"id": 2}]]
    assert fetch(client, batch_size=1, max_batches=2, fields=field_type(["name", "id"]),
                 window=window) == [{"id": 1}, {"id": 2}]
    predicate = PREDICATE if window is WINDOW else ""
    assert [call.args for call in client.query.call_args_list] == [
        (endpoint, f"fields name, id; {predicate}sort id asc; limit 1; offset {offset};")
        for offset in (0, 1)
    ]


@pytest.mark.parametrize(
    ("pages", "cap"),
    [([[]], None), ([[{"id": 1}]], None),
     ([[{"id": 1}, {"id": 2}], []], None),
     ([[{"id": 1}, {"id": 2}], [{"id": 3}]], None),
     ([[{"id": 1}, {"id": 2}]], 1), ([], 0), ([], -1)],
    ids=["empty", "short", "full-empty", "full-short", "capped", "zero-cap", "negative-cap"],
)
def test_window_keeps_pagination_and_stopping_rules(supported, pages, cap) -> None:
    endpoint, _, fetch, fields = supported
    client = MagicMock()
    client.query.side_effect = pages
    assert fetch(client, batch_size=2, max_batches=cap, window=WINDOW) == [
        record for page in pages for record in page
    ]
    assert [call.args for call in client.query.call_args_list] == [
        (endpoint, f"fields {fields}; {PREDICATE}sort id asc; limit 2; offset {page * 2};")
        for page in range(len(pages))
    ]


def test_windowed_later_page_error_propagates(supported) -> None:
    _, _, fetch, _ = supported
    error = IGDBClientError("Later page failed")
    client = MagicMock()
    client.query.side_effect = [[{"id": 1}], error]
    with pytest.raises(IGDBClientError) as raised:
        fetch(client, batch_size=1, window=WINDOW)
    assert raised.value is error
    assert client.query.call_count == 2


@pytest.mark.parametrize(("endpoint", "build", "fetch"), [
    ("genres", build_genres_query, fetch_genres_batches),
    ("platforms", build_platforms_query, fetch_platforms_batches),
])
def test_reference_entities_default_unfiltered_and_explicit_window(endpoint, build, fetch) -> None:
    records = [{"id": 1, "updated_at": 0}, {"id": 2, "updated_at": None}, {"id": 3}]
    client = MagicMock()
    client.query.side_effect = [records[:2], records[2:]]
    assert fetch(client, batch_size=2) == records
    expected = "fields id, name, slug, updated_at; sort id asc; limit 2; offset {offset};"
    assert build(limit=2, offset=0) == expected.format(offset=0)
    assert [call.args for call in client.query.call_args_list] == [
        (endpoint, expected.format(offset=offset)) for offset in (0, 2)
    ]
    # Reference entities use windows only when a caller explicitly supplies one.
    assert build(limit=2, offset=0, window=WINDOW) == (
        f"fields id, name, slug, updated_at; where updated_at >= {WINDOW.lower_bound} "
        f"& updated_at < {WINDOW.upper_bound}; sort id asc; limit 2; offset 0;"
    )
