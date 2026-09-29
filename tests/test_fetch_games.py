"""Tests for batched IGDB game fetching and local raw persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.ingestion.fetch_games import (
    DEFAULT_GAME_FIELDS,
    build_games_query,
    fetch_games_batches,
    save_games_to_jsonl,
)


class FakeClient:
    """Minimal fake IGDB client for batch testing."""

    def __init__(self, responses: list[list[dict]]) -> None:
        self.responses = responses
        self.queries: list[tuple[str, str]] = []

    def query(self, endpoint: str, query: str) -> list[dict]:
        """Record the request and return the next queued response."""

        self.queries.append((endpoint, query))
        return self.responses.pop(0)


def test_build_games_query_uses_limit_offset_and_fields() -> None:
    """Games query should use APIcalypse limit and offset clauses."""

    query = build_games_query(limit=250, offset=500, fields=("id", "name"))

    assert query == "fields id, name; sort id asc; limit 250; offset 500;"


def test_build_games_query_preserves_defaults_after_custom_fields() -> None:
    """A per-call field override must not change the shared default contract."""

    original_fields = DEFAULT_GAME_FIELDS
    build_games_query(limit=1, offset=0, fields=["name"])

    assert DEFAULT_GAME_FIELDS is original_fields
    assert build_games_query(limit=500, offset=0) == (
        "fields id, name, slug, first_release_date, rating, rating_count, "
        "total_rating, total_rating_count, updated_at, genres, platforms, involved_companies; "
        "sort id asc; limit 500; offset 0;"
    )


def test_fetch_games_batches_stops_after_partial_batch() -> None:
    """Fetching should stop when IGDB returns a partial batch."""

    client = FakeClient(
        [
            [{"id": 1}, {"id": 2}],
            [{"id": 3}],
        ]
    )

    games = fetch_games_batches(client, batch_size=2)

    assert games == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert len(client.queries) == 2
    assert client.queries[0][0] == "games"
    assert "offset 0;" in client.queries[0][1]
    assert "offset 2;" in client.queries[1][1]


def test_fetch_games_batches_preserves_default_query() -> None:
    """Request relationship IDs alongside original fields with unchanged paging."""

    client = FakeClient([[]])

    assert fetch_games_batches(client) == []
    assert client.queries == [
        (
            "games",
            "fields id, name, slug, first_release_date, rating, rating_count, "
            "total_rating, total_rating_count, updated_at, genres, platforms, involved_companies; "
            "sort id asc; limit 500; offset 0;",
        )
    ]


@pytest.mark.parametrize("fields", [("id", "slug"), ["id", "slug"]])
def test_fetch_games_batches_preserves_custom_fields_and_batch_cap(fields) -> None:
    """Custom fields apply to every page and the cap prevents extra requests."""

    client = FakeClient([[{"id": 1}], [{"id": 2}]])

    games = fetch_games_batches(
        client, batch_size=1, max_batches=2, fields=fields
    )

    assert games == [{"id": 1}, {"id": 2}]
    assert client.queries == [
        ("games", "fields id, slug; sort id asc; limit 1; offset 0;"),
        ("games", "fields id, slug; sort id asc; limit 1; offset 1;"),
    ]


@pytest.mark.parametrize("max_batches", [0, -1])
def test_fetch_games_batches_with_non_positive_cap_makes_no_requests(max_batches: int) -> None:
    """Preserve the existing no-op behavior for non-positive batch caps."""

    client = FakeClient([])

    assert fetch_games_batches(client, max_batches=max_batches) == []
    assert client.queries == []


def test_save_games_to_jsonl_writes_newline_delimited_json(tmp_path: Path) -> None:
    """Saving raw games should create a JSONL file."""

    games = [{"id": 1, "name": "Halo"}, {"id": 2, "name": "Portal"}]
    output_path = tmp_path / "games.jsonl"

    count = save_games_to_jsonl(games, output_path)

    assert count == 2
    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == games
