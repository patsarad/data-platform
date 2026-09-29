"""Reusable offset-based fetching for IGDB endpoints."""

from __future__ import annotations

from collections.abc import Callable

from src.ingestion.client import IGDBClient
from src.utils.logger import get_logger


def fetch_paginated(
    client: IGDBClient,
    *,
    endpoint: str,
    build_query: Callable[[int, int], str],
    batch_size: int = 500,
    max_batches: int | None = None,
) -> list[dict]:
    """Collect records until an empty/partial page or the batch cap is reached.

    ``build_query`` receives limit and offset as positional arguments and must
    use them with a deterministic sort. Offsets start at zero. A non-positive
    ``max_batches`` makes no requests; ``None`` leaves the fetch uncapped.
    Client errors propagate, with retries remaining the client's responsibility.
    """

    logger = get_logger(__name__)
    records: list[dict] = []
    offset = 0
    batch_number = 0

    while max_batches is None or batch_number < max_batches:
        query = build_query(batch_size, offset)
        batch = client.query(endpoint, query)
        batch_number += 1
        records.extend(batch)

        logger.info(
            "Fetched %s batch %s with %s records at offset %s.",
            endpoint,
            batch_number,
            len(batch),
            offset,
        )

        if not batch or len(batch) < batch_size:
            break

        offset += batch_size

    logger.info("Finished fetching %s total records from %s.", len(records), endpoint)
    return records
