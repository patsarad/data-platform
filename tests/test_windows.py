"""Pure window calculations: explicit time inputs, no API or database calls."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from src.ingestion.windows import SourceWindow, calculate_source_window


EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
WATERMARK = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
START = datetime(2026, 9, 26, 12, tzinfo=timezone.utc)


def test_overlap_is_relative_to_watermark_even_after_long_outage() -> None:
    """Replay 24 hours before W, including the elapsed gap until run start."""

    assert calculate_source_window(WATERMARK, run_started_at=START) == SourceWindow(
        lower_bound=1790251200, upper_bound=1790424000,
    )
    assert calculate_source_window(
        WATERMARK, run_started_at=START + timedelta(days=30)
    ).lower_bound == 1790251200


@pytest.mark.parametrize(("seconds", "lower"), [(0, 0), (1, 0), (86399, 0), (86400, 0), (86401, 1)])
def test_overlap_clamps_at_epoch(seconds, lower) -> None:
    window = calculate_source_window(EPOCH + timedelta(seconds=seconds), run_started_at=START)
    assert window == SourceWindow(lower_bound=lower, upper_bound=1790424000)


@pytest.mark.parametrize("offset_hours", [-5, 0, 5.5])
def test_utc_conversion_floors_only_run_start(offset_hours) -> None:
    zone = timezone(timedelta(hours=offset_hours))
    window = calculate_source_window(
        WATERMARK.astimezone(zone),
        run_started_at=START.replace(microsecond=999999).astimezone(zone),
    )
    assert window == SourceWindow(lower_bound=1790251200, upper_bound=1790424000)


def test_bootstrap_retains_cutoff_without_historical_lower_bound() -> None:
    assert calculate_source_window(None, run_started_at=START) == SourceWindow(None, 1790424000)
    assert calculate_source_window(None, run_started_at=EPOCH) == SourceWindow(None, 0)


@pytest.mark.parametrize("delta", [timedelta(days=-1), timedelta(0), timedelta(microseconds=999999)])
def test_reject_nonprogressing_cutoff_after_flooring(delta) -> None:
    with pytest.raises(ValueError, match="greater than watermark"):
        calculate_source_window(WATERMARK, run_started_at=WATERMARK + delta)


@pytest.mark.parametrize("name", ["watermark", "run_started_at"])
@pytest.mark.parametrize(
    ("value", "error", "message"),
    [("2026-09-25", TypeError, "datetime"),
     (1790337600, TypeError, "datetime"),
     (datetime(2026, 9, 25), ValueError, "timezone-aware"),
     (EPOCH - timedelta(microseconds=1), ValueError, "Unix epoch")],
)
def test_invalid_time_inputs(name, value, error, message) -> None:
    arguments = {"watermark": WATERMARK, "run_started_at": START, name: value}
    with pytest.raises(error, match=message):
        calculate_source_window(**arguments)


def test_reject_fractional_watermark_without_rounding() -> None:
    with pytest.raises(ValueError, match="whole-second"):
        calculate_source_window(WATERMARK.replace(microsecond=1), run_started_at=START)


def test_explicit_run_start_is_required_even_for_bootstrap() -> None:
    with pytest.raises(TypeError):
        calculate_source_window(None)
    with pytest.raises(TypeError, match="datetime"):
        calculate_source_window(None, run_started_at=None)
    with pytest.raises(ValueError, match="timezone-aware"):
        calculate_source_window(None, run_started_at=START.replace(tzinfo=None))


@pytest.mark.parametrize(
    ("lower", "upper", "error"),
    [(None, None, TypeError), (0, None, TypeError), (False, 2, TypeError),
     (0, True, TypeError), (1.0, 2, TypeError), (0, 2.5, TypeError),
     ("0", 2, TypeError), (0, "2", TypeError), (-1, 2, ValueError),
     (None, -1, ValueError), (2, 2, ValueError), (3, 2, ValueError)],
)
def test_invalid_window_bounds(lower, upper, error) -> None:
    with pytest.raises(error):
        SourceWindow(lower_bound=lower, upper_bound=upper)


def test_window_requires_both_arguments_and_is_immutable() -> None:
    with pytest.raises(TypeError):
        SourceWindow(lower_bound=0)
    with pytest.raises(TypeError):
        SourceWindow(upper_bound=2)
    window = SourceWindow(0, 2)
    with pytest.raises(FrozenInstanceError):
        window.upper_bound = 3
    with pytest.raises(FrozenInstanceError):
        window.lower_bound = 1
