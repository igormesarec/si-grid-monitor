"""Import-only sustained-load forecasting over fixed billing quarters."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from .engine import EPSILON, QUARTER_HOURS, PowerSegment, quarter_bounds

SEARCH_TOLERANCE_KW = 1e-6
MAX_SEARCH_KW = 1_000_000.0


class ForecastQuality(StrEnum):
    """Availability/confidence states exposed by the integration."""

    AVAILABLE = "available"
    INSUFFICIENT_COVERAGE = "insufficient_coverage"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class SustainedForecast:
    """Conservative result across recent-pattern and instantaneous scenarios."""

    can_add_kw: float | None
    must_reduce_kw: float | None
    quality: ForecastQuality
    horizon_minutes: int
    smoothing_seconds: int
    measurement_age_seconds: float | None
    coverage_seconds: float
    limiting_quarter_start_utc: datetime | None
    limiting_quarter_end_utc: datetime | None
    limiting_target_kw: float | None
    current_quarter_unrecoverable: bool
    assumption: str
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class _ScenarioResult:
    can_add_kw: float
    must_reduce_kw: float | None
    limiting_start: datetime
    limiting_end: datetime
    limiting_target_kw: float


TargetProvider = Callable[[datetime, datetime], float]


def calculate_sustained_forecast(
    *,
    now: datetime,
    current_import_kwh: float,
    current_unrecoverable: bool,
    recent_segments: Sequence[PowerSegment],
    latest_signed_kw: float | None,
    measurement_age_seconds: float | None,
    smoothing_seconds: int,
    horizon_minutes: int,
    target_for_quarter: TargetProvider,
    stale_after_seconds: float,
) -> SustainedForecast:
    """Forecast a constant load/reduction against every intersecting quarter.

    The recent signed path repeats cyclically. A second scenario holds the latest
    signed measurement constant. Proposed load is applied to signed power before
    import is clamped, so export at one time can never net import at another.
    """

    now_utc = now.astimezone(UTC)
    coverage = sum(segment.duration_seconds for segment in recent_segments)
    common = {
        "horizon_minutes": horizon_minutes,
        "smoothing_seconds": smoothing_seconds,
        "measurement_age_seconds": measurement_age_seconds,
        "coverage_seconds": coverage,
        "current_quarter_unrecoverable": current_unrecoverable,
        "assumption": "recent signed path repeats; latest signed power persists",
    }
    if latest_signed_kw is None or measurement_age_seconds is None:
        return _unavailable(ForecastQuality.UNAVAILABLE, "no_valid_measurement", common)
    if measurement_age_seconds > stale_after_seconds:
        return _unavailable(ForecastQuality.STALE, "source_measurement_stale", common)
    if coverage + EPSILON < smoothing_seconds or not recent_segments:
        return _unavailable(
            ForecastQuality.INSUFFICIENT_COVERAGE,
            "smoothing_window_incomplete",
            common,
        )
    if horizon_minutes not in {15, 30, 60, 120}:
        raise ValueError("horizon_minutes must be 15, 30, 60, or 120")
    if current_import_kwh < 0 or not math.isfinite(current_import_kwh):
        raise ValueError("current_import_kwh must be finite and nonnegative")

    history = _evaluate_scenario(
        now_utc,
        current_import_kwh,
        current_unrecoverable,
        recent_segments,
        horizon_minutes,
        target_for_quarter,
    )
    instant = _evaluate_scenario(
        now_utc,
        current_import_kwh,
        current_unrecoverable,
        (PowerSegment(float(smoothing_seconds), latest_signed_kw),),
        horizon_minutes,
        target_for_quarter,
    )
    if history.must_reduce_kw is None or instant.must_reduce_kw is None:
        return _unavailable(
            ForecastQuality.UNAVAILABLE,
            "scheduled_reduction_cannot_recover_limiting_quarter",
            common,
        )
    add_result = min((history, instant), key=lambda result: result.can_add_kw)
    reduce_result = max((history, instant), key=lambda result: result.must_reduce_kw)
    limiting = add_result if add_result.can_add_kw > 0 else reduce_result
    return SustainedForecast(
        can_add_kw=min(history.can_add_kw, instant.can_add_kw),
        must_reduce_kw=max(history.must_reduce_kw, instant.must_reduce_kw),
        quality=ForecastQuality.AVAILABLE,
        limiting_quarter_start_utc=limiting.limiting_start,
        limiting_quarter_end_utc=limiting.limiting_end,
        limiting_target_kw=limiting.limiting_target_kw,
        reason=("current_quarter_already_unrecoverable" if current_unrecoverable else None),
        **common,
    )


def _unavailable(
    quality: ForecastQuality, reason: str, common: dict[str, object]
) -> SustainedForecast:
    return SustainedForecast(
        can_add_kw=None,
        must_reduce_kw=None,
        quality=quality,
        limiting_quarter_start_utc=None,
        limiting_quarter_end_utc=None,
        limiting_target_kw=None,
        reason=reason,
        **common,  # type: ignore[arg-type]
    )


def _evaluate_scenario(
    now: datetime,
    current_import_kwh: float,
    current_unrecoverable: bool,
    pattern: Sequence[PowerSegment],
    horizon_minutes: int,
    target_for_quarter: TargetProvider,
) -> _ScenarioResult:
    load_end = now + timedelta(minutes=horizon_minutes)
    quarters: list[tuple[datetime, datetime, float, bool]] = []
    bounds = quarter_bounds(now)
    start = bounds.start_utc
    while start < load_end:
        end = start + timedelta(minutes=15)
        target = target_for_quarter(start, end)
        if not math.isfinite(target) or target < 0:
            raise ValueError("quarter target must be finite and nonnegative")
        quarters.append((start, end, target, start == bounds.start_utc))
        start = end

    def energy(quarter: tuple[datetime, datetime, float, bool], adjustment: float) -> float:
        start, end, _target, current = quarter
        forecast_start = now if current else start
        base = current_import_kwh if current else 0.0
        return base + _integrate_pattern(
            pattern,
            seconds=(end - forecast_start).total_seconds(),
            adjustment=adjustment,
            adjusted_until_seconds=max(
                0.0,
                min(
                    (load_end - forecast_start).total_seconds(),
                    (end - forecast_start).total_seconds(),
                ),
            ),
        )

    def add_fits(value: float) -> bool:
        return all(
            energy(quarter, value) <= quarter[2] * QUARTER_HOURS + EPSILON for quarter in quarters
        )

    can_add = 0.0 if current_unrecoverable else _max_true(add_fits)

    def reduction_fits(value: float) -> bool:
        for quarter in quarters:
            total = energy(quarter, -value)
            if quarter[3] and current_unrecoverable:
                if total > current_import_kwh + EPSILON:
                    return False
            elif total > quarter[2] * QUARTER_HOURS + EPSILON:
                return False
        return True

    must_reduce = _min_true(reduction_fits)
    # Report the tightest quarter at the final addition recommendation.
    limiting = min(
        quarters,
        key=lambda quarter: quarter[2] * QUARTER_HOURS - energy(quarter, can_add),
    )
    return _ScenarioResult(can_add, must_reduce, limiting[0], limiting[1], limiting[2])


def _integrate_pattern(
    pattern: Sequence[PowerSegment],
    *,
    seconds: float,
    adjustment: float,
    adjusted_until_seconds: float,
) -> float:
    cycle = sum(segment.duration_seconds for segment in pattern)
    if cycle <= 0:
        raise ValueError("forecast pattern must have positive duration")
    elapsed = 0.0
    energy_kwh = 0.0
    index = 0
    offset = 0.0
    while elapsed < seconds - EPSILON:
        segment = pattern[index]
        duration = min(segment.duration_seconds - offset, seconds - elapsed)
        if elapsed < adjusted_until_seconds:
            adjusted_duration = min(duration, adjusted_until_seconds - elapsed)
            energy_kwh += max(0.0, segment.signed_kw + adjustment) * adjusted_duration / 3600
            remaining = duration - adjusted_duration
            energy_kwh += max(0.0, segment.signed_kw) * remaining / 3600
        else:
            energy_kwh += max(0.0, segment.signed_kw) * duration / 3600
        elapsed += duration
        offset += duration
        if offset >= segment.duration_seconds - EPSILON:
            index = (index + 1) % len(pattern)
            offset = 0.0
    return energy_kwh


def _max_true(predicate: Callable[[float], bool]) -> float:
    low, high = 0.0, 1.0
    while high < MAX_SEARCH_KW and predicate(high):
        low, high = high, high * 2
    if predicate(high):
        return high
    while high - low > SEARCH_TOLERANCE_KW:
        middle = (low + high) / 2
        if predicate(middle):
            low = middle
        else:
            high = middle
    return low


def _min_true(predicate: Callable[[float], bool]) -> float | None:
    if predicate(0.0):
        return 0.0
    low, high = 0.0, 1.0
    while high < MAX_SEARCH_KW and not predicate(high):
        low, high = high, high * 2
    if not predicate(high):
        return None
    while high - low > SEARCH_TOLERANCE_KW:
        middle = (low + high) / 2
        if predicate(middle):
            high = middle
        else:
            low = middle
    return high
