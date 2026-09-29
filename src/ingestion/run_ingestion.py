"""Command-line entrypoint for ingesting one or all configured IGDB entities."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

from src.entities import COMPANIES, GAMES, GENRES, INVOLVED_COMPANIES, PLATFORMS
from src.ingestion.fetch_companies import fetch_companies_batches, save_companies_to_jsonl
from src.ingestion.fetch_games import fetch_games_batches, save_games_to_jsonl
from src.ingestion.fetch_genres import fetch_genres_batches, save_genres_to_jsonl
from src.ingestion.fetch_involved_companies import (
    fetch_involved_companies_batches, save_involved_companies_to_jsonl,
)
from src.ingestion.fetch_platforms import fetch_platforms_batches, save_platforms_to_jsonl
from src.ingestion.pipeline import RunSelection, ingest_entity
from src.ingestion.windows import SourceWindow
from src.storage.raw_companies import ensure_raw_companies_table, upsert_raw_companies
from src.storage.raw_games import ensure_raw_games_table, upsert_raw_games
from src.storage.raw_genres import ensure_raw_genres_table, upsert_raw_genres
from src.storage.raw_involved_companies import (
    ensure_raw_involved_companies_table, upsert_raw_involved_companies,
)
from src.storage.raw_platforms import ensure_raw_platforms_table, upsert_raw_platforms
from src.utils.config import get_settings
from src.utils.logger import get_logger


DEFAULT_OUTPUT_DIR = Path("data/raw")
DEFAULT_OUTPUT_FILENAME_TEMPLATE = "raw_{entity}_{timestamp}.jsonl"


def _utc_second(value: str) -> int:
    """Parse an explicit whole-second UTC instant for a historical interval."""

    try:
        instant = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise argparse.ArgumentTypeError("use YYYY-MM-DDTHH:MM:SSZ (whole-second UTC)") from error
    if instant.strftime("%Y-%m-%dT%H:%M:%SZ") != value or instant.timestamp() < 0:
        raise argparse.ArgumentTypeError("use a whole-second UTC instant at or after the Unix epoch")
    return int(instant.timestamp())


def build_output_path(output_dir: Path = DEFAULT_OUTPUT_DIR, *, entity: str = "games") -> Path:
    """Build an entity archive path, retaining the default games directory/format."""

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return output_dir / DEFAULT_OUTPUT_FILENAME_TEMPLATE.format(entity=entity, timestamp=timestamp)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the ingestion command."""

    parser = argparse.ArgumentParser(description="Ingest IGDB entities into raw storage.")
    parser.add_argument(
        "--entity",
        choices=("games", "genres", "platforms", "companies", "involved_companies", "all"),
        default="games",
        help="Entity to ingest (default: games). All runs sequentially in the listed order.",
    )
    parser.add_argument("--batch-size", type=int, default=500, help="Records fetched per API call for each entity.")
    parser.add_argument(
        "--max-batches",
        type=int,
        default=None,
        help="Maximum batches per entity. Defaults to all available batches.",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help="Single-entity JSONL path. Defaults to data/raw/raw_<entity>_<timestamp>.jsonl.",
    )
    parser.add_argument("--full-refresh", action="store_true", help="Read selected endpoints unfiltered and upsert all returned rows.")
    parser.add_argument("--backfill-start", type=_utc_second, metavar="UTC", help="Inclusive historical updated_at bound (YYYY-MM-DDTHH:MM:SSZ).")
    parser.add_argument("--backfill-end", type=_utc_second, metavar="UTC", help="Exclusive historical updated_at bound (YYYY-MM-DDTHH:MM:SSZ).")
    args = parser.parse_args()
    if args.entity == "all" and args.output_path is not None:
        parser.error("--output-path is ambiguous with --entity all; each entity needs a separate archive. Select a single entity to override its path.")
    if (args.backfill_start is None) != (args.backfill_end is None):
        parser.error("--backfill-start and --backfill-end must be supplied together.")
    if args.full_refresh and args.backfill_start is not None:
        parser.error("--full-refresh cannot be combined with a backfill interval.")
    if args.backfill_start is not None and args.backfill_end <= args.backfill_start:
        parser.error("--backfill-end must be later than --backfill-start.")
    return args


def main() -> None:
    """Ingest selected entities sequentially; stop on failure, retaining prior commits."""

    args = parse_args()
    logger = get_logger(__name__)
    settings = get_settings()
    # Insertion order is the documented all-mode order, not a reference dependency.
    components = {
        "games": (GAMES, fetch_games_batches, save_games_to_jsonl,
                  ensure_raw_games_table, upsert_raw_games),
        "genres": (GENRES, fetch_genres_batches, save_genres_to_jsonl,
                   ensure_raw_genres_table, upsert_raw_genres),
        "platforms": (PLATFORMS, fetch_platforms_batches, save_platforms_to_jsonl,
                      ensure_raw_platforms_table, upsert_raw_platforms),
        "companies": (COMPANIES, fetch_companies_batches, save_companies_to_jsonl,
                      ensure_raw_companies_table, upsert_raw_companies),
        "involved_companies": (
            INVOLVED_COMPANIES, fetch_involved_companies_batches, save_involved_companies_to_jsonl,
            ensure_raw_involved_companies_table, upsert_raw_involved_companies,
        ),
    }
    selected = components.values() if args.entity == "all" else (components[args.entity],)
    mode = "backfill" if args.backfill_start is not None else ("full_refresh" if args.full_refresh else "normal")
    backfill_window = (
        SourceWindow(args.backfill_start, args.backfill_end)
        if mode == "backfill" else None
    )
    for entity, fetch, archive, ensure, upsert in selected:
        output_path = args.output_path or build_output_path(entity=entity.endpoint)
        logger.info(
            f"Starting IGDB {entity.endpoint} ingestion with batch_size=%s, max_batches=%s.",
            args.batch_size,
            args.max_batches,
        )
        records_fetched, records_loaded = ingest_entity(
            entity=entity,
            schema_name=settings.postgres_schema,
            output_path=output_path,
            fetch_records=partial(fetch, batch_size=args.batch_size, max_batches=args.max_batches),
            archive_records=archive,
            ensure_table=ensure,
            upsert_records=upsert,
            logger=logger,
            selection=RunSelection(
                batch_size=args.batch_size, max_batches=args.max_batches, default_fields=True,
                mode=mode, backfill_window=backfill_window,
            ),
        )
        logger.info(
            f"Finished ingestion. Saved %s {entity.endpoint} locally and loaded %s rows into %s.{entity.raw_table}.",
            records_fetched,
            records_loaded,
            settings.postgres_schema,
        )


if __name__ == "__main__":
    main()
