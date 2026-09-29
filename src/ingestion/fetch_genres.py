"""Fetch and archive IGDB genre lookup records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from src.entities import GENRES
from src.ingestion.client import IGDBClient
from src.ingestion.pagination import fetch_paginated
from src.ingestion.windows import SourceWindow
from src.utils.logger import get_logger


DEFAULT_GENRE_FIELDS = GENRES.fields


def build_genres_query(
    *,
    limit: int,
    offset: int,
    fields: Iterable[str] = DEFAULT_GENRE_FIELDS,
    window: SourceWindow | None = None,
) -> str:
    """Build an ID-ordered genres query, optionally filtered for backfill."""

    window_filter = (
        f"where updated_at >= {window.lower_bound} & updated_at < {window.upper_bound}; "
        if window is not None and window.lower_bound is not None else ""
    )
    return (
        f"fields {', '.join(fields)}; {window_filter}sort {GENRES.source_primary_key} asc; "
        f"limit {limit}; offset {offset};"
    )


def fetch_genres_batches(
    client: IGDBClient,
    *,
    batch_size: int = 500,
    max_batches: int | None = None,
    fields: Iterable[str] = DEFAULT_GENRE_FIELDS,
    window: SourceWindow | None = None,
) -> list[dict]:
    """Fetch genres until an empty/partial page or the batch cap is reached."""

    # Materialize once so iterable field overrides survive subsequent pages.
    fields = tuple(fields)
    return fetch_paginated(
        client,
        endpoint=GENRES.endpoint,
        build_query=lambda limit, offset: build_genres_query(
            limit=limit, offset=offset, fields=fields, window=window
        ),
        batch_size=batch_size,
        max_batches=max_batches,
    )


def save_genres_to_jsonl(genres: Iterable[dict], output_path: Path) -> int:
    """Write complete fetched genre payloads as UTF-8 newline-delimited JSON."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8") as file_handle:
        for genre in genres:
            file_handle.write(json.dumps(genre, sort_keys=True))
            file_handle.write("\n")
            count += 1

    get_logger(__name__).info("Saved %s raw genres to %s.", count, output_path)
    return count
