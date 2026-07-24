"""Helpers for fetching IGDB games data in batches."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from src.ingestion.client import IGDBClient
from src.utils.logger import get_logger


DEFAULT_GAME_FIELDS = (
    "id",
    "name",
    "slug",
    "first_release_date",
    "rating",
    "rating_count",
    "total_rating",
    "total_rating_count",
    "updated_at",
)


def build_games_query(
    *,
    limit: int,
    offset: int,
    fields: Iterable[str] = DEFAULT_GAME_FIELDS,
) -> str:
    """Build an IGDB APIcalypse query for the games endpoint."""

    field_list = ", ".join(fields)
    return f"fields {field_list}; sort id asc; limit {limit}; offset {offset};"


def fetch_games_batches(
    client: IGDBClient,
    *,
    batch_size: int = 500,
    max_batches: int | None = None,
    fields: Iterable[str] = DEFAULT_GAME_FIELDS,
) -> list[dict]:
    """Fetch IGDB games in batches until no more rows are returned."""

    logger = get_logger(__name__)
    all_games: list[dict] = []
    offset = 0
    batch_number = 0

    while max_batches is None or batch_number < max_batches:
        query = build_games_query(limit=batch_size, offset=offset, fields=fields)
        batch = client.query("games", query)
        batch_number += 1
        all_games.extend(batch)

        logger.info(
            "Fetched games batch %s with %s records at offset %s.",
            batch_number,
            len(batch),
            offset,
        )

        if not batch or len(batch) < batch_size:
            break

        offset += batch_size

    logger.info("Finished fetching %s total game records.", len(all_games))
    return all_games


def save_games_to_jsonl(games: Iterable[dict], output_path: Path) -> int:
    """Save raw game payloads to a newline-delimited JSON file."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0

    with output_path.open("w", encoding="utf-8") as file_handle:
        for game in games:
            file_handle.write(json.dumps(game, sort_keys=True))
            file_handle.write("\n")
            count += 1

    get_logger(__name__).info("Saved %s raw games to %s.", count, output_path)
    return count
