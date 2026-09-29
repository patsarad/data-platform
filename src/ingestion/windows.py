"""Explicit source-window calculations, independent of payloads and persistence."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


OVERLAP_SECONDS = 86_400
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class SourceWindow:
    """Frozen Unix-second bounds; a None lower bound means unfiltered bootstrap.

    The upper bound is retained during bootstrap as a planned cutoff, not a
    query predicate or permission to publish a checkpoint.
    """

    lower_bound: int | None
    upper_bound: int

    def __post_init__(self) -> None:
        for name, value in (("lower_bound", self.lower_bound), ("upper_bound", self.upper_bound)):
            if name == "lower_bound" and value is None:
                continue
            if type(value) is not int:
                raise TypeError(f"{name} must be integer Unix seconds.")
            if value < 0:
                raise ValueError(f"{name} must be nonnegative.")
        if self.lower_bound is not None and self.upper_bound <= self.lower_bound:
            raise ValueError("upper_bound must be greater than lower_bound.")


def calculate_source_window(
    watermark: datetime | None, *, run_started_at: datetime
) -> SourceWindow:
    """Freeze a cutoff and apply a 24-hour overlap to an existing watermark.

    Call once before source work with an aware run-start instant. UTC conversion
    floors only that instant to whole seconds. A watermark must already be an
    aware, whole-second instant. Reject non-progressing cutoffs instead of
    manufacturing progress. None history produces a full, unfiltered bootstrap.
    This helper reads no clock, metadata, or payload and writes no watermark.
    """

    start = _as_utc(run_started_at, "run_started_at")
    # Integer timedelta division avoids float rounding at second boundaries.
    upper_bound = (start - _EPOCH) // timedelta(seconds=1)
    if watermark is None:
        return SourceWindow(lower_bound=None, upper_bound=upper_bound)

    previous = _as_utc(watermark, "watermark")
    if previous.microsecond:
        raise ValueError("watermark must have whole-second precision.")
    previous_seconds = (previous - _EPOCH) // timedelta(seconds=1)
    if upper_bound <= previous_seconds:
        raise ValueError("Run-start cutoff must be greater than watermark.")
    return SourceWindow(
        lower_bound=max(0, previous_seconds - OVERLAP_SECONDS),
        upper_bound=upper_bound,
    )


def _as_utc(value: datetime, name: str) -> datetime:
    """Reject implicit local times and pre-epoch inputs without coercion."""

    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a timezone-aware datetime.")
    if value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware.")
    value = value.astimezone(timezone.utc)
    if value < _EPOCH:
        raise ValueError(f"{name} must be at or after the Unix epoch.")
    return value
