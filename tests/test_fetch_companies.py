"""Companies query and archive contracts, using an offline API boundary."""

import json
from unittest.mock import MagicMock

import pytest

from src.ingestion.fetch_companies import (
    build_companies_query,
    fetch_companies_batches,
    save_companies_to_jsonl,
)


def test_default_query_after_custom_fields() -> None:
    """Custom fields do not mutate the minimal default query or stable ordering."""

    assert build_companies_query(limit=10, offset=20, fields=("id", "slug")) == (
        "fields id, slug; sort id asc; limit 10; offset 20;"
    )
    client = MagicMock()
    client.query.return_value = []
    assert fetch_companies_batches(client) == []
    client.query.assert_called_once_with(
        "companies", "fields id, name, slug, updated_at; sort id asc; limit 500; offset 0;"
    )


def test_custom_iterable_fields_survive_pages_and_batch_cap() -> None:
    """Forward options to shared pagination and keep fields on every request."""

    client = MagicMock()
    client.query.side_effect = [[{"id": 1}], [{"id": 2}]]
    assert fetch_companies_batches(
        client, batch_size=1, max_batches=2, fields=iter(["id", "name"])
    ) == [{"id": 1}, {"id": 2}]
    assert [call.args for call in client.query.call_args_list] == [
        ("companies", "fields id, name; sort id asc; limit 1; offset 0;"),
        ("companies", "fields id, name; sort id asc; limit 1; offset 1;"),
    ]


@pytest.mark.parametrize("max_batches", [0, -1])
def test_nonpositive_cap_skips_source(max_batches) -> None:
    """Retain the shared helper's no-op cap semantics."""

    client = MagicMock()
    assert fetch_companies_batches(client, max_batches=max_batches) == []
    client.query.assert_not_called()


@pytest.mark.parametrize("records", [[], [{"id": 5, "name": "Rôle", "nested": [1, None]}]])
def test_archive_preserves_payloads_and_creates_parent(tmp_path, records) -> None:
    """Archive iterable input faithfully, including an empty result."""

    output = tmp_path / "nested" / "companies.jsonl"
    assert save_companies_to_jsonl(iter(records), output) == len(records)
    content = output.read_text(encoding="utf-8")
    assert [json.loads(line) for line in content.splitlines()] == records
    assert content.endswith("\n") if records else content == ""


def test_archive_io_error_propagates(tmp_path) -> None:
    """A failed archive must prevent the runner from proceeding to raw loading."""

    with pytest.raises(IsADirectoryError):
        save_companies_to_jsonl([{"id": 1}], tmp_path)
