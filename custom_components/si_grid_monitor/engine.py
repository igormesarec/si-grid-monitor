"""Pure-Python SI Grid Monitor calculation engine.

The engine keeps rolling signed averages separate from fixed-quarter,
import-only billing-style demand. Live samples are modeled as piecewise
constant until the next sample or the configured stale limit, whichever comes
first. Time without a supported signal is a gap, never an assumed zero.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

LJUBLJANA = ZoneInfo("Europe/Ljubljana")
QUARTER_SECONDS = 15 * 60
QUARTER_HOURS = 0.25
EPSILON = 1e-9


class CalculationError(ValueError):
    """Raised for invalid calculation input or time ordering."""


class DataQuality(StrEnum):
    """Required quarter/archive quality vocabulary."""

    MEASURED_ALIGNED = "measured_aligned"
    COUNTER_DERIVED = "counter_derived"
    RECONSTRUCTED = "reconstructed"
    INCOMPLETE = "incomplete"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class QuarterBounds:
    start_utc: datetime
    end_utc: datetime
    start_local: datetime
    end_local: datetime


@dataclass(frozen=True, slots=True)
class PowerSample:
    timestamp: datetime
    signed_kw: float

    def __post_init__(self) -> None:
        _require_aware(self.timestamp, "timestamp")
        if not math.isfinite(self.signed_kw):
            raise CalculationError("signed_kw must be finite")

    @property
    def timestamp_utc(self) -> datetime:
        return self.timestamp.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class WindowAverage:
    value_kw: float | None
    coverage_seconds: float
    gap_seconds: float
    complete: bool


@dataclass(frozen=True, slots=True)
class PowerSegment:
    """One covered piece of a time-weighted signed-power path."""

    duration_seconds: float
    signed_kw: float


@dataclass(frozen=True, slots=True)
class CompletedQuarter:
    start_utc: datetime
    end_utc: datetime
    import_kwh: float
    export_kwh: float
    signed_net_kwh: float
    import_demand_kw: float
    signed_average_kw: float
    coverage_seconds: float
    gap_seconds: float
    quality: DataQuality
    source_id: str


@dataclass(frozen=True, slots=True)
class Projection:
    operational_target_kw: float
    budget_kwh: float
    budget_remaining_kwh: float
    allowed_remaining_import_kw: float | None
    forecast_instant_kw: float | None
    forecast_smoothed_kw: float | None
    forecast_instant_utilization_pct: float | None
    forecast_smoothed_utilization_pct: float | None
    current_utilization_pct: float | None
    can_add_kw: float | None
    must_reduce_kw: float | None
    unrecoverable: bool
    projected_exceedance: bool | None

    @property
    def forecast_utilization_pct(self) -> float | None:
        """Backward-compatible primary forecast utilization (smoothed)."""

        return self.forecast_smoothed_utilization_pct


@dataclass(frozen=True, slots=True)
class EngineSnapshot:
    bounds: QuarterBounds
    now_utc: datetime
    current_signed_power_kw: float | None
    input_stale: bool
    quarter_import_kwh: float
    quarter_export_kwh: float
    quarter_signed_net_kwh: float
    elapsed_seconds: float
    remaining_seconds: float
    current_import_average_kw: float | None
    current_signed_average_kw: float | None
    rolling_15m_signed: WindowAverage
    rolling_15m_import: WindowAverage
    smoothed_signed: WindowAverage
    smoothed_import: WindowAverage
    projection: Projection
    coverage_seconds: float
    gap_seconds: float
    quality: DataQuality


def quarter_bounds(instant: datetime) -> QuarterBounds:
    """Return the fixed quarter containing ``instant``.

    The canonical calculation is performed on the UTC timeline. Ljubljana's
    civil offset changes by whole hours, so UTC 15-minute boundaries map
    exactly to local :00/:15/:30/:45 boundaries. Repeated autumn clock times
    remain unambiguous because the returned local values retain their offsets
    and ``fold`` information.
    """

    _require_aware(instant, "instant")
    instant_utc = instant.astimezone(UTC)
    epoch_seconds = int(instant_utc.timestamp())
    start_epoch = epoch_seconds - (epoch_seconds % QUARTER_SECONDS)
    start_utc = datetime.fromtimestamp(start_epoch, UTC)
    end_utc = start_utc + timedelta(seconds=QUARTER_SECONDS)
    return QuarterBounds(
        start_utc=start_utc,
        end_utc=end_utc,
        start_local=start_utc.astimezone(LJUBLJANA),
        end_local=end_utc.astimezone(LJUBLJANA),
    )


def quarter_starts_for_local_day(local_date: date) -> tuple[datetime, ...]:
    """Return UTC starts for every local quarter in a Ljubljana civil day."""

    local_start = datetime.combine(local_date, time.min, tzinfo=LJUBLJANA)
    local_end = datetime.combine(local_date + timedelta(days=1), time.min, tzinfo=LJUBLJANA)
    cursor = local_start.astimezone(UTC)
    end_utc = local_end.astimezone(UTC)
    starts: list[datetime] = []
    while cursor < end_utc:
        starts.append(cursor)
        cursor += timedelta(seconds=QUARTER_SECONDS)
    return tuple(starts)


def calculate_projection(
    *,
    target_kw: float,
    safety_margin_kw: float,
    import_kwh: float,
    elapsed_hours: float,
    remaining_hours: float,
    current_signed_power_kw: float | None,
    smoothed_import_power_kw: float | None = None,
    smoothed_signed_power_kw: float | None = None,
) -> Projection:
    """Apply the frozen current-quarter formulas from specification V1.1."""

    for value, label in (
        (target_kw, "target_kw"),
        (safety_margin_kw, "safety_margin_kw"),
        (import_kwh, "import_kwh"),
        (elapsed_hours, "elapsed_hours"),
        (remaining_hours, "remaining_hours"),
    ):
        if not math.isfinite(value) or value < 0:
            raise CalculationError(f"{label} must be finite and nonnegative")
    for value, label in (
        (current_signed_power_kw, "current_signed_power_kw"),
        (smoothed_import_power_kw, "smoothed_import_power_kw"),
        (smoothed_signed_power_kw, "smoothed_signed_power_kw"),
    ):
        if value is not None and not math.isfinite(value):
            raise CalculationError(f"{label} must be finite when provided")

    operational_target_kw = max(0.0, target_kw - safety_margin_kw)
    budget_kwh = operational_target_kw * QUARTER_HOURS
    budget_remaining_kwh = budget_kwh - import_kwh
    unrecoverable = budget_remaining_kwh < -EPSILON
    allowed = max(0.0, budget_remaining_kwh / remaining_hours) if remaining_hours > 0 else None

    forecast_instant = _forecast(import_kwh, remaining_hours, current_signed_power_kw)
    # ``smoothed_signed_power_kw`` is accepted only for V0.1 API compatibility.
    # V0.2 callers must provide the separately integrated import-only average.
    if smoothed_import_power_kw is None and smoothed_signed_power_kw is not None:
        smoothed_import_power_kw = max(0.0, smoothed_signed_power_kw)
    forecast_smoothed = _forecast_import(import_kwh, remaining_hours, smoothed_import_power_kw)
    forecast_instant_utilization = (
        100.0 * forecast_instant / target_kw
        if forecast_instant is not None and target_kw > 0
        else None
    )
    forecast_smoothed_utilization = (
        100.0 * forecast_smoothed / target_kw
        if forecast_smoothed is not None and target_kw > 0
        else None
    )
    current_average = import_kwh / elapsed_hours if elapsed_hours > 0 else None
    current_utilization = (
        100.0 * current_average / target_kw
        if current_average is not None and target_kw > 0
        else None
    )

    if current_signed_power_kw is None or allowed is None:
        can_add = None
        must_reduce = None
    elif unrecoverable:
        can_add = 0.0
        must_reduce = max(0.0, current_signed_power_kw)
    else:
        can_add = max(0.0, allowed - current_signed_power_kw)
        must_reduce = max(0.0, current_signed_power_kw - allowed)

    projected_exceedance = (
        forecast_instant > target_kw + EPSILON if forecast_instant is not None else None
    )
    return Projection(
        operational_target_kw=operational_target_kw,
        budget_kwh=budget_kwh,
        budget_remaining_kwh=budget_remaining_kwh,
        allowed_remaining_import_kw=allowed,
        forecast_instant_kw=forecast_instant,
        forecast_smoothed_kw=forecast_smoothed,
        forecast_instant_utilization_pct=forecast_instant_utilization,
        forecast_smoothed_utilization_pct=forecast_smoothed_utilization,
        current_utilization_pct=current_utilization,
        can_add_kw=can_add,
        must_reduce_kw=must_reduce,
        unrecoverable=unrecoverable,
        projected_exceedance=projected_exceedance,
    )


def _forecast(
    import_kwh: float, remaining_hours: float, signed_power_kw: float | None
) -> float | None:
    if signed_power_kw is None:
        return None
    return (import_kwh + remaining_hours * max(0.0, signed_power_kw)) / QUARTER_HOURS


def _forecast_import(
    import_kwh: float, remaining_hours: float, import_power_kw: float | None
) -> float | None:
    if import_power_kw is None:
        return None
    return (import_kwh + remaining_hours * import_power_kw) / QUARTER_HOURS


class TimeWeightedBuffer:
    """Time-weighted signed/import-only rolling window over live samples."""

    def __init__(self, *, stale_after_seconds: float) -> None:
        if stale_after_seconds <= 0:
            raise CalculationError("stale_after_seconds must be positive")
        self.stale_after = timedelta(seconds=stale_after_seconds)
        self._samples: list[PowerSample] = []

    def add(self, sample: PowerSample) -> None:
        normalized = PowerSample(sample.timestamp_utc, sample.signed_kw)
        if self._samples and normalized.timestamp_utc <= self._samples[-1].timestamp_utc:
            raise CalculationError("sample timestamps must increase strictly")
        self._samples.append(normalized)
        cutoff = normalized.timestamp_utc - timedelta(seconds=900) - self.stale_after
        while len(self._samples) > 1 and self._samples[1].timestamp_utc < cutoff:
            self._samples.pop(0)

    def averages(
        self, *, end: datetime, window_seconds: int
    ) -> tuple[WindowAverage, WindowAverage]:
        _require_aware(end, "end")
        if window_seconds <= 0:
            raise CalculationError("window_seconds must be positive")
        end_utc = end.astimezone(UTC)
        start_utc = end_utc - timedelta(seconds=window_seconds)
        signed_area = 0.0
        import_area = 0.0
        coverage = 0.0

        for index, sample in enumerate(self._samples):
            sample_start = sample.timestamp_utc
            if sample_start >= end_utc:
                break
            next_start = (
                self._samples[index + 1].timestamp_utc
                if index + 1 < len(self._samples)
                else end_utc
            )
            valid_end = min(next_start, sample_start + self.stale_after, end_utc)
            segment_start = max(sample_start, start_utc)
            if valid_end <= segment_start:
                continue
            seconds = (valid_end - segment_start).total_seconds()
            coverage += seconds
            signed_area += sample.signed_kw * seconds
            import_area += max(0.0, sample.signed_kw) * seconds

        gap = max(0.0, float(window_seconds) - coverage)
        complete = gap <= EPSILON
        signed_value = signed_area / coverage if coverage > 0 else None
        import_value = import_area / coverage if coverage > 0 else None
        return (
            WindowAverage(signed_value, coverage, gap, complete),
            WindowAverage(import_value, coverage, gap, complete),
        )

    def segments(self, *, end: datetime, window_seconds: int) -> tuple[PowerSegment, ...]:
        """Return covered signed segments in chronological order for forecasting."""

        _require_aware(end, "end")
        if window_seconds <= 0:
            raise CalculationError("window_seconds must be positive")
        end_utc = end.astimezone(UTC)
        start_utc = end_utc - timedelta(seconds=window_seconds)
        segments: list[PowerSegment] = []
        for index, sample in enumerate(self._samples):
            if sample.timestamp_utc >= end_utc:
                break
            next_start = (
                self._samples[index + 1].timestamp_utc
                if index + 1 < len(self._samples)
                else end_utc
            )
            segment_start = max(sample.timestamp_utc, start_utc)
            segment_end = min(next_start, sample.timestamp_utc + self.stale_after, end_utc)
            if segment_end > segment_start:
                segments.append(
                    PowerSegment((segment_end - segment_start).total_seconds(), sample.signed_kw)
                )
        return tuple(segments)


class FixedQuarterEngine:
    """Integrate signed samples into fixed import/export quarters."""

    def __init__(self, *, stale_after_seconds: float = 60.0, source_id: str = "live") -> None:
        if stale_after_seconds <= 0:
            raise CalculationError("stale_after_seconds must be positive")
        self.stale_after = timedelta(seconds=stale_after_seconds)
        self.source_id = source_id
        self.buffer = TimeWeightedBuffer(stale_after_seconds=stale_after_seconds)
        self.bounds: QuarterBounds | None = None
        self.cursor_utc: datetime | None = None
        self.last_sample: PowerSample | None = None
        self.import_kwh = 0.0
        self.export_kwh = 0.0
        self.coverage_seconds = 0.0
        self.gap_seconds = 0.0
        self.completed: list[CompletedQuarter] = []

    def checkpoint(self) -> dict[str, object] | None:
        """Serialize durable current-quarter state without smoothing history."""

        if self.bounds is None or self.cursor_utc is None:
            return None
        return {
            "schema": 1,
            "source_id": self.source_id,
            "quarter_start_utc": self.bounds.start_utc.isoformat(),
            "cursor_utc": self.cursor_utc.isoformat(),
            "last_sample_utc": (
                self.last_sample.timestamp_utc.isoformat() if self.last_sample is not None else None
            ),
            "last_signed_kw": (
                self.last_sample.signed_kw if self.last_sample is not None else None
            ),
            "import_kwh": self.import_kwh,
            "export_kwh": self.export_kwh,
            "coverage_seconds": self.coverage_seconds,
            "gap_seconds": self.gap_seconds,
        }

    def restore_checkpoint(self, payload: dict[str, object]) -> bool:
        """Restore a same-source current quarter; unknown downtime stays a gap."""

        if payload.get("schema") != 1 or payload.get("source_id") != self.source_id:
            return False
        try:
            start = datetime.fromisoformat(str(payload["quarter_start_utc"]))
            cursor = datetime.fromisoformat(str(payload["cursor_utc"]))
            _require_aware(start, "quarter_start_utc")
            _require_aware(cursor, "cursor_utc")
            bounds = quarter_bounds(cursor)
            if bounds.start_utc != start.astimezone(UTC):
                return False
            last_utc = payload.get("last_sample_utc")
            last_kw = payload.get("last_signed_kw")
            last_sample = (
                PowerSample(datetime.fromisoformat(str(last_utc)), float(last_kw))
                if last_utc is not None and last_kw is not None
                else None
            )
            self.bounds = bounds
            self.cursor_utc = cursor.astimezone(UTC)
            self.last_sample = last_sample
            self.import_kwh = float(payload["import_kwh"])
            self.export_kwh = float(payload["export_kwh"])
            self.coverage_seconds = float(payload["coverage_seconds"])
            self.gap_seconds = float(payload["gap_seconds"])
        except (KeyError, TypeError, ValueError, CalculationError):
            return False
        # Smoothing samples are deliberately not invented after a restart.
        self.buffer = TimeWeightedBuffer(stale_after_seconds=self.stale_after.total_seconds())
        if last_sample is not None:
            self.buffer.add(last_sample)
        return True

    def ingest(self, sample: PowerSample) -> tuple[CompletedQuarter, ...]:
        sample = PowerSample(sample.timestamp_utc, sample.signed_kw)
        before = len(self.completed)
        if self.bounds is None:
            self._initialize(sample.timestamp_utc)
            self.gap_seconds = (sample.timestamp_utc - self.bounds.start_utc).total_seconds()
        elif self.last_sample and sample.timestamp_utc <= self.last_sample.timestamp_utc:
            raise CalculationError("sample timestamps must increase strictly")
        else:
            self.advance(sample.timestamp_utc)

        self.buffer.add(sample)
        self.last_sample = sample
        self.cursor_utc = sample.timestamp_utc
        return tuple(self.completed[before:])

    def advance(self, instant: datetime) -> tuple[CompletedQuarter, ...]:
        _require_aware(instant, "instant")
        instant_utc = instant.astimezone(UTC)
        if self.bounds is None or self.cursor_utc is None:
            return ()
        if instant_utc < self.cursor_utc:
            raise CalculationError("cannot advance backwards in time")
        before = len(self.completed)

        while self.cursor_utc < instant_utc:
            segment_end = min(instant_utc, self.bounds.end_utc)
            self._integrate_segment(self.cursor_utc, segment_end)
            self.cursor_utc = segment_end
            if self.cursor_utc == self.bounds.end_utc:
                self._finalize_current()
                self._initialize(self.cursor_utc)
        return tuple(self.completed[before:])

    def snapshot(
        self,
        *,
        now: datetime,
        target_kw: float,
        safety_margin_kw: float = 0.0,
        smoothing_seconds: int = 120,
    ) -> EngineSnapshot:
        self.advance(now)
        if self.bounds is None:
            raise CalculationError("at least one sample is required")
        now_utc = now.astimezone(UTC)
        elapsed_seconds = (now_utc - self.bounds.start_utc).total_seconds()
        remaining_seconds = (self.bounds.end_utc - now_utc).total_seconds()
        latest = self.last_sample
        input_stale = latest is None or now_utc > latest.timestamp_utc + self.stale_after
        current_power = None if input_stale or latest is None else latest.signed_kw
        rolling_15m_signed, rolling_15m_import = self.buffer.averages(
            end=now_utc, window_seconds=QUARTER_SECONDS
        )
        smoothed_signed, smoothed_import = self.buffer.averages(
            end=now_utc, window_seconds=smoothing_seconds
        )
        smoothed_import_power = smoothed_import.value_kw if smoothed_import.complete else None
        projection = calculate_projection(
            target_kw=target_kw,
            safety_margin_kw=safety_margin_kw,
            import_kwh=self.import_kwh,
            elapsed_hours=max(0.0, elapsed_seconds / 3600.0),
            remaining_hours=max(0.0, remaining_seconds / 3600.0),
            current_signed_power_kw=current_power,
            smoothed_import_power_kw=smoothed_import_power,
        )
        elapsed_hours = elapsed_seconds / 3600.0
        quality = (
            DataQuality.RECONSTRUCTED if self.gap_seconds <= EPSILON else DataQuality.INCOMPLETE
        )
        return EngineSnapshot(
            bounds=self.bounds,
            now_utc=now_utc,
            current_signed_power_kw=current_power,
            input_stale=input_stale,
            quarter_import_kwh=self.import_kwh,
            quarter_export_kwh=self.export_kwh,
            quarter_signed_net_kwh=self.import_kwh - self.export_kwh,
            elapsed_seconds=elapsed_seconds,
            remaining_seconds=remaining_seconds,
            current_import_average_kw=(
                self.import_kwh / elapsed_hours if elapsed_hours > 0 else None
            ),
            current_signed_average_kw=(
                (self.import_kwh - self.export_kwh) / elapsed_hours if elapsed_hours > 0 else None
            ),
            rolling_15m_signed=rolling_15m_signed,
            rolling_15m_import=rolling_15m_import,
            smoothed_signed=smoothed_signed,
            smoothed_import=smoothed_import,
            projection=projection,
            coverage_seconds=self.coverage_seconds,
            gap_seconds=self.gap_seconds,
            quality=quality,
        )

    def _initialize(self, instant_utc: datetime) -> None:
        self.bounds = quarter_bounds(instant_utc)
        self.cursor_utc = instant_utc
        self.import_kwh = 0.0
        self.export_kwh = 0.0
        self.coverage_seconds = 0.0
        self.gap_seconds = 0.0

    def _integrate_segment(self, start: datetime, end: datetime) -> None:
        if end <= start:
            return
        if self.last_sample is None:
            self.gap_seconds += (end - start).total_seconds()
            return
        valid_until = self.last_sample.timestamp_utc + self.stale_after
        covered_end = min(end, valid_until)
        if covered_end > start:
            seconds = (covered_end - start).total_seconds()
            hours = seconds / 3600.0
            self.import_kwh += max(0.0, self.last_sample.signed_kw) * hours
            self.export_kwh += max(0.0, -self.last_sample.signed_kw) * hours
            self.coverage_seconds += seconds
        gap_start = max(start, covered_end)
        if end > gap_start:
            self.gap_seconds += (end - gap_start).total_seconds()

    def _finalize_current(self) -> None:
        if self.bounds is None:
            raise CalculationError("cannot finalize an uninitialized quarter")
        quality = (
            DataQuality.RECONSTRUCTED
            if self.coverage_seconds >= QUARTER_SECONDS - EPSILON and self.gap_seconds <= EPSILON
            else DataQuality.INCOMPLETE
        )
        signed_net_kwh = self.import_kwh - self.export_kwh
        self.completed.append(
            CompletedQuarter(
                start_utc=self.bounds.start_utc,
                end_utc=self.bounds.end_utc,
                import_kwh=self.import_kwh,
                export_kwh=self.export_kwh,
                signed_net_kwh=signed_net_kwh,
                import_demand_kw=self.import_kwh / QUARTER_HOURS,
                signed_average_kw=signed_net_kwh / QUARTER_HOURS,
                coverage_seconds=self.coverage_seconds,
                gap_seconds=self.gap_seconds,
                quality=quality,
                source_id=self.source_id,
            )
        )


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CalculationError(f"{field} must be timezone-aware")


def round_for_display(value: float | None, decimals: int) -> float | None:
    """Round only the published value while keeping engine calculations precise."""

    return None if value is None else round(value, decimals)
