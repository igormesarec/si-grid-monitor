"""Pure-Python source adapters for SI Grid Monitor.

Every adapter normalizes the grid sign to positive import and negative export.
The adapters intentionally do not depend on Home Assistant so their behavior is
portable and directly unit-testable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from .engine import QUARTER_HOURS, CompletedQuarter, DataQuality, quarter_bounds


class AdapterError(ValueError):
    """Raised when source data cannot be safely normalized."""


class SourceMode(StrEnum):
    """Supported source designs."""

    SIGNED_POWER = "signed_power"
    SEPARATE_POWER = "separate_power"
    IMPORT_ONLY = "import_only"
    CUMULATIVE_ENERGY = "cumulative_energy"
    ALIGNED_QUARTER = "aligned_quarter"


@dataclass(frozen=True, slots=True)
class NormalizedPower:
    """Normalized instantaneous power."""

    signed_kw: float
    import_kw: float
    export_kw: float | None
    export_known: bool


@dataclass(frozen=True, slots=True)
class CounterDelta:
    """Validated cumulative energy delta."""

    start: datetime
    end: datetime
    import_kwh: float
    export_kwh: float | None
    quality: DataQuality
    aligned_to_one_quarter: bool


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool):
        raise AdapterError(f"{field} must be numeric")
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as err:
        raise AdapterError(f"{field} must be numeric") from err
    if not math.isfinite(result):
        raise AdapterError(f"{field} must be finite")
    return result


def power_to_kw(value: object, unit: str) -> float:
    """Convert W/kW to kW."""

    numeric = _finite_number(value, "power")
    normalized = unit.strip().lower()
    if normalized == "w":
        return numeric / 1000.0
    if normalized == "kw":
        return numeric
    raise AdapterError(f"unsupported power unit: {unit!r}")


def energy_to_kwh(value: object, unit: str) -> float:
    """Convert Wh/kWh to kWh."""

    numeric = _finite_number(value, "energy")
    normalized = unit.strip().lower()
    if normalized == "wh":
        return numeric / 1000.0
    if normalized == "kwh":
        return numeric
    raise AdapterError(f"unsupported energy unit: {unit!r}")


class SignedPowerAdapter:
    """Normalize one signed live power source."""

    def __init__(self, *, positive_means_import: bool = True) -> None:
        self.positive_means_import = positive_means_import

    def normalize(self, value: object, unit: str) -> NormalizedPower:
        signed_kw = power_to_kw(value, unit)
        if not self.positive_means_import:
            signed_kw = -signed_kw
        return NormalizedPower(
            signed_kw=signed_kw,
            import_kw=max(0.0, signed_kw),
            export_kw=max(0.0, -signed_kw),
            export_known=True,
        )


class SeparatePowerAdapter:
    """Combine separate nonnegative live import and export sources."""

    def __init__(self, *, simultaneous_tolerance_kw: float = 0.001) -> None:
        if simultaneous_tolerance_kw < 0:
            raise AdapterError("simultaneous tolerance must be nonnegative")
        self.simultaneous_tolerance_kw = simultaneous_tolerance_kw

    def normalize(
        self,
        import_value: object,
        import_unit: str,
        export_value: object,
        export_unit: str,
    ) -> NormalizedPower:
        import_kw = power_to_kw(import_value, import_unit)
        export_kw = power_to_kw(export_value, export_unit)
        if import_kw < 0 or export_kw < 0:
            raise AdapterError("separate import/export sources must be nonnegative")
        if (
            import_kw > self.simultaneous_tolerance_kw
            and export_kw > self.simultaneous_tolerance_kw
        ):
            raise AdapterError("conflicting simultaneous import and export values")
        return NormalizedPower(
            signed_kw=import_kw - export_kw,
            import_kw=import_kw,
            export_kw=export_kw,
            export_known=True,
        )


class ImportOnlyPowerAdapter:
    """Normalize a nonnegative import-only source without inventing export."""

    def normalize(self, value: object, unit: str) -> NormalizedPower:
        import_kw = power_to_kw(value, unit)
        if import_kw < 0:
            raise AdapterError("import-only source must be nonnegative")
        return NormalizedPower(
            signed_kw=import_kw,
            import_kw=import_kw,
            export_kw=None,
            export_known=False,
        )


class CumulativeEnergyAdapter:
    """Validate deltas from cumulative import and optional export counters.

    V0.1 deliberately does not distribute a counter delta across more than one
    fixed quarter. Such a delta is returned as ``incomplete`` for a later archive
    stage to apportion only when supporting timestamp evidence exists.
    """

    def delta(
        self,
        *,
        previous_import: object,
        current_import: object,
        import_unit: str,
        start: datetime,
        end: datetime,
        previous_export: object | None = None,
        current_export: object | None = None,
        export_unit: str | None = None,
    ) -> CounterDelta:
        _require_aware_utc_convertible(start, "start")
        _require_aware_utc_convertible(end, "end")
        if end <= start:
            raise AdapterError("counter end must be after start")

        import_delta = energy_to_kwh(current_import, import_unit) - energy_to_kwh(
            previous_import, import_unit
        )
        if import_delta < 0:
            raise AdapterError("cumulative import counter reset or rolled over")

        export_delta: float | None = None
        if previous_export is not None or current_export is not None:
            if previous_export is None or current_export is None or export_unit is None:
                raise AdapterError("both export counter values and unit are required")
            export_delta = energy_to_kwh(current_export, export_unit) - energy_to_kwh(
                previous_export, export_unit
            )
            if export_delta < 0:
                raise AdapterError("cumulative export counter reset or rolled over")

        start_utc = start.astimezone(UTC)
        end_utc = end.astimezone(UTC)
        bounds = quarter_bounds(start_utc)
        aligned = start_utc == bounds.start_utc and end_utc == bounds.end_utc
        return CounterDelta(
            start=start_utc,
            end=end_utc,
            import_kwh=import_delta,
            export_kwh=export_delta,
            quality=DataQuality.COUNTER_DERIVED if aligned else DataQuality.INCOMPLETE,
            aligned_to_one_quarter=aligned,
        )


class AlignedQuarterAdapter:
    """Validate an already aligned, completed 15-minute record."""

    def from_import_demand(
        self,
        *,
        start: datetime,
        end: datetime,
        value: object,
        unit: str,
        export_kwh: object | None = None,
        source_id: str = "aligned_quarter",
    ) -> CompletedQuarter:
        start_utc, end_utc = self._validate_bounds(start, end)
        normalized_unit = unit.strip().lower()
        if normalized_unit == "kw":
            import_kwh = _finite_number(value, "quarter demand") * QUARTER_HOURS
        elif normalized_unit in {"kwh", "wh"}:
            import_kwh = energy_to_kwh(value, unit)
        else:
            raise AdapterError(f"unsupported aligned quarter unit: {unit!r}")
        if import_kwh < 0:
            raise AdapterError("aligned import value must be nonnegative")

        normalized_export = 0.0 if export_kwh is None else _finite_number(export_kwh, "export_kwh")
        if normalized_export < 0:
            raise AdapterError("aligned export value must be nonnegative")
        return CompletedQuarter(
            start_utc=start_utc,
            end_utc=end_utc,
            import_kwh=import_kwh,
            export_kwh=normalized_export,
            signed_net_kwh=import_kwh - normalized_export,
            import_demand_kw=import_kwh / QUARTER_HOURS,
            signed_average_kw=(import_kwh - normalized_export) / QUARTER_HOURS,
            coverage_seconds=900.0,
            gap_seconds=0.0,
            quality=DataQuality.MEASURED_ALIGNED,
            source_id=source_id,
        )

    @staticmethod
    def _validate_bounds(start: datetime, end: datetime) -> tuple[datetime, datetime]:
        _require_aware_utc_convertible(start, "start")
        _require_aware_utc_convertible(end, "end")
        start_utc = start.astimezone(UTC)
        end_utc = end.astimezone(UTC)
        bounds = quarter_bounds(start_utc)
        if start_utc != bounds.start_utc or end_utc != bounds.end_utc:
            raise AdapterError("record must span exactly one aligned fixed quarter")
        return start_utc, end_utc


def _require_aware_utc_convertible(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AdapterError(f"{field} must be timezone-aware")
