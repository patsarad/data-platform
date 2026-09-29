"""Reusable fetch/archive/load orchestration with durable run metadata."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from logging import Logger
from pathlib import Path

from psycopg import Connection

from src.entities import EntityConfig
from src.ingestion.client import IGDBClient, create_igdb_client
from src.ingestion.fetch_companies import fetch_companies_batches
from src.ingestion.fetch_games import fetch_games_batches
from src.ingestion.fetch_involved_companies import fetch_involved_companies_batches
from src.ingestion.windows import SourceWindow, calculate_source_window
from src.storage.ingestion_runs import (
    ensure_ingestion_runs_table,
    fail_ingestion_run,
    get_source_watermark,
    start_ingestion_run,
    succeed_ingestion_run,
)
from src.storage.raw_games import create_connection


_WINDOW_FETCHERS = {
    "games": fetch_games_batches,
    "companies": fetch_companies_batches,
    "involved_companies": fetch_involved_companies_batches,
}


@dataclass(frozen=True)
class RunSelection:
    """Explicit CLI extraction mode, backfill bounds, and checkpoint gates.

    Direct callers without this declaration retain their existing fetch/load
    behavior but cannot publish progress. Explicit custom fields are ineligible
    even when they happen to equal the default projection. A backfill never
    publishes progress, regardless of its other options.
    """

    batch_size: int
    max_batches: int | None
    default_fields: bool
    mode: str = "normal"
    backfill_window: SourceWindow | None = None


def _checkpoint_warning(
    entity: EntityConfig, selection: RunSelection | None,
    fetch_records: Callable, records: list[dict], archived: int,
    loaded: int, window: SourceWindow | None, completed_at: datetime,
) -> str | None:
    """Return a fixed safe reason to withhold an incremental checkpoint."""

    if selection is None and entity.endpoint in _WINDOW_FETCHERS:
        return "Checkpoint withheld: no declared normal selection."
    if window is None or selection is None:
        return None
    if (
        not isinstance(fetch_records, partial)
        or fetch_records.func is not _WINDOW_FETCHERS[entity.endpoint]
        or fetch_records.args
        or fetch_records.keywords != {
            "batch_size": selection.batch_size,
            "max_batches": selection.max_batches,
        }
        or not selection.default_fields
    ):
        return "Checkpoint withheld: extraction did not use the default field contract."
    if selection.max_batches is not None:
        return "Checkpoint withheld: extraction had a batch cap."
    if not 1 <= selection.batch_size <= 500:
        return "Checkpoint withheld: page size is outside 1–500."
    if archived != len(records) or loaded != len(records):
        return "Checkpoint withheld: archive or load count did not match fetched records."
    for record in records:
        value = record.get(entity.update_field)
        if type(value) is not int or value < 0:
            return "Checkpoint withheld: returned update timestamps are unusable."
        try:
            timestamp = datetime.fromtimestamp(value, timezone.utc)
        except (OverflowError, OSError, ValueError):
            return "Checkpoint withheld: returned update timestamps are unusable."
        if timestamp > completed_at:
            return "Checkpoint withheld: returned update timestamps are unusable."
        if window.lower_bound is not None and not (
            window.lower_bound <= value < window.upper_bound
        ):
            return "Checkpoint withheld: returned update timestamps are outside the window."
    return None


def ingest_entity(
    *,
    entity: EntityConfig,
    schema_name: str,
    output_path: Path,
    fetch_records: Callable[[IGDBClient], list[dict]],
    archive_records: Callable[[list[dict], Path], int],
    ensure_table: Callable[[Connection, str], None],
    upsert_records: Callable[[Connection, list[dict], str, datetime], int],
    logger: Logger,
    selection: RunSelection | None = None,
) -> tuple[int, int]:
    """Run supplied entity operations and return acknowledged fetch/load counts.

    Bind fetch options before calling. Storage callbacks own their existing
    commits; this runner owns connection contexts and separate metadata writes.
    Client creation follows the durable start. Success follows raw context exit.
    Failure reporting is best-effort and preserves the original exception.
    """

    window = None
    run_started_at = None
    mode = selection.mode if selection is not None else "normal"
    if mode not in {"normal", "full_refresh", "backfill"}:
        raise ValueError("Unknown ingestion selection mode.")
    if (mode == "backfill") != (selection is not None and selection.backfill_window is not None):
        raise ValueError("Backfill selection requires exactly one explicit window.")
    if mode == "backfill" and selection.backfill_window.lower_bound is None:
        raise ValueError("Backfill selection requires an inclusive lower bound.")
    # DDL is committed before lookup. The same short-lived metadata connection
    # then records the lower bound; no connection remains open during fetching.
    with create_connection() as connection:
        ensure_ingestion_runs_table(connection, schema_name)
        if mode == "backfill":
            window = selection.backfill_window
        elif selection is not None and entity.endpoint in _WINDOW_FETCHERS:
            watermark = get_source_watermark(connection, schema_name, entity.endpoint)
            run_started_at = datetime.now(timezone.utc)
            calculated = calculate_source_window(watermark, run_started_at=run_started_at)
            window = (
                SourceWindow(None, calculated.upper_bound)
                if mode == "full_refresh" else calculated
            )
        if window is not None and window.lower_bound is not None:
            lower = datetime.fromtimestamp(window.lower_bound, timezone.utc)
            run_id = start_ingestion_run(
                connection, schema_name, entity.endpoint,
                started_at=run_started_at, source_watermark_start=lower,
            )
        elif run_started_at is not None:
            run_id = start_ingestion_run(
                connection, schema_name, entity.endpoint, started_at=run_started_at,
            )
        else:
            run_id = start_ingestion_run(connection, schema_name, entity.endpoint)
        if window is not None:
            logger.info(
                "Run %s selected %s mode=%s with lower=%s, cutoff=%s, cap=%s.",
                run_id, entity.endpoint, mode, window.lower_bound, window.upper_bound,
                selection.max_batches,
            )

    records_fetched = 0
    records_loaded = 0
    stage = "source fetch"
    try:
        client = create_igdb_client()
        records = (
            fetch_records(client, window=window)
            if window is not None and window.lower_bound is not None
            else fetch_records(client)
        )
        records_fetched = len(records)
        fetch_completed_at = datetime.now(timezone.utc)

        stage = "JSONL archive"
        archived = archive_records(records, output_path)

        stage = "raw load"
        fetched_at = datetime.now(timezone.utc)
        with create_connection() as connection:
            ensure_table(connection, schema_name)
            records_loaded = upsert_records(connection, records, schema_name, fetched_at)

        warning = None
        if mode != "backfill":
            warning = _checkpoint_warning(
                entity, selection, fetch_records, records, archived, records_loaded,
                window, fetch_completed_at,
            )
        if warning:
            logger.warning("Ingestion run %s: %s", run_id, warning)
        checkpoint = (
            datetime.fromtimestamp(window.upper_bound, timezone.utc)
            if window is not None and warning is None and selection is not None
            and mode != "backfill" and entity.endpoint in _WINDOW_FETCHERS
            else None
        )
        stage = "run completion"
        with create_connection() as connection:
            if checkpoint is None:
                succeed_ingestion_run(
                    connection, schema_name, run_id, records_fetched, records_loaded
                )
            else:
                succeed_ingestion_run(
                    connection, schema_name, run_id, records_fetched, records_loaded,
                    source_watermark_end=checkpoint,
                )
    except Exception:
        # The raw/success context has already rolled back and closed if it failed.
        # Fixed stage summaries avoid copying credentials or payloads from exceptions.
        logger.error("Ingestion run %s failed during %s.", run_id, stage)
        try:
            with create_connection() as connection:
                fail_ingestion_run(
                    connection, schema_name, run_id,
                    records_fetched, records_loaded, f"{stage} failed.",
                )
        except Exception:
            logger.error("Could not record failure for ingestion run %s.", run_id)
        raise

    return records_fetched, records_loaded
