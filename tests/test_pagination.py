"""Tests for reusable pagination without live IGDB access."""

from __future__ import annotations

import pytest

from src.ingestion.client import IGDBClientError
from src.ingestion.pagination import fetch_paginated


class FakeClient:
    """Record requests and return queued pages or raise queued failures."""

    def __init__(self, responses: list[list[dict] | Exception]) -> None:
        self.responses = responses
        self.queries: list[tuple[str, str]] = []

    def query(self, endpoint: str, query: str) -> list[dict]:
        """Return the next result, failing if an extra request is made."""

        self.queries.append((endpoint, query))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def build_test_query(limit: int, offset: int) -> str:
    """Keep test-specific fields and filtering outside the pagination helper."""

    return f"fields id; where id > 0; sort id asc; limit {limit}; offset {offset};"


@pytest.mark.parametrize(
    ("pages", "expected"),
    [
        ([[]], []),
        ([[{"id": 1}]], [{"id": 1}]),
        ([[{"id": 1}, {"id": 2}], []], [{"id": 1}, {"id": 2}]),
        (
            [[{"id": 1}, {"id": 2}], [{"id": 3}, {"id": 4}], [{"id": 5}]],
            [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}, {"id": 5}],
        ),
    ],
    ids=["empty-first-page", "partial-first-page", "full-then-empty", "multiple-pages"],
)
def test_fetch_paginated_stops_at_empty_or_partial_page(pages, expected) -> None:
    """Retain page order and use the supplied endpoint/query at each offset."""

    page_count = len(pages)
    client = FakeClient(list(pages))

    records = fetch_paginated(
        client, endpoint="test_records", build_query=build_test_query, batch_size=2
    )

    assert records == expected
    assert client.queries == [
        ("test_records", build_test_query(2, page * 2))
        for page in range(page_count)
    ]


@pytest.mark.parametrize("max_batches", [0, -1, 1, 2])
def test_fetch_paginated_respects_batch_cap(max_batches: int) -> None:
    """A cap limits requests, including making none for non-positive caps."""

    client = FakeClient([[{"id": 1}], [{"id": 2}], [{"id": 3}]])

    records = fetch_paginated(
        client,
        endpoint="test_records",
        build_query=build_test_query,
        batch_size=1,
        max_batches=max_batches,
    )

    count = max(0, max_batches)
    assert records == [{"id": i + 1} for i in range(count)]
    assert client.queries == [
        ("test_records", build_test_query(1, offset)) for offset in range(count)
    ]


def test_fetch_paginated_propagates_client_error_after_successful_page() -> None:
    """A later failure must propagate instead of returning incomplete data."""

    error = IGDBClientError("Request failed")
    client = FakeClient([[{"id": 1}], error])

    with pytest.raises(IGDBClientError) as raised:
        fetch_paginated(
            client, endpoint="test_records", build_query=build_test_query, batch_size=1
        )

    assert raised.value is error
    assert len(client.queries) == 2
