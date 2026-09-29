"""Fetch and archive IGDB company lookup records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from src.entities import COMPANIES
from src.ingestion.client import IGDBClient
from src.ingestion.pagination import fetch_paginated
from src.ingestion.windows import SourceWindow
from src.utils.logger import get_logger


DEFAULT_COMPANY_FIELDS = COMPANIES.fields


def build_companies_query(
    *,
    limit: int,
    offset: int,
    fields: Iterable[str] = DEFAULT_COMPANY_FIELDS,
    window: SourceWindow | None = None,
) -> str:
    """Build an ID-ordered companies query with an optional frozen window."""

    window_filter = (
        f"where updated_at >= {window.lower_bound} & updated_at < {window.upper_bound}; "
        if window is not None and window.lower_bound is not None else ""
    )
    return (
        f"fields {', '.join(fields)}; {window_filter}sort {COMPANIES.source_primary_key} asc; "
        f"limit {limit}; offset {offset};"
    )


def fetch_companies_batches(
    client: IGDBClient,
    *,
    batch_size: int = 500,
    max_batches: int | None = None,
    fields: Iterable[str] = DEFAULT_COMPANY_FIELDS,
    window: SourceWindow | None = None,
) -> list[dict]:
    """Fetch companies until an empty/partial page or the batch cap is reached."""

    # Materialize once so iterable field overrides survive subsequent pages.
    fields = tuple(fields)
    return fetch_paginated(
        client,
        endpoint=COMPANIES.endpoint,
        build_query=lambda limit, offset: build_companies_query(
            limit=limit, offset=offset, fields=fields, window=window
        ),
        batch_size=batch_size,
        max_batches=max_batches,
    )


def save_companies_to_jsonl(companies: Iterable[dict], output_path: Path) -> int:
    """Write complete fetched company payloads as UTF-8 newline-delimited JSON."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8") as file_handle:
        for company in companies:
            file_handle.write(json.dumps(company, sort_keys=True))
            file_handle.write("\n")
            count += 1

    get_logger(__name__).info("Saved %s raw companies to %s.", count, output_path)
    return count
