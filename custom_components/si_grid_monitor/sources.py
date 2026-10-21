"""Source-mode normalization and cumulative-counter conversion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from .adapters import AdapterError, NormalizedPower, energy_to_kwh


@dataclass(frozen=True, slots=True)
class SourceCapabilities:
    """Truthful capabilities of one configured input design."""

    instantaneous_power: bool
    export_known: bool
    directly_measured: bool


@dataclass(frozen=True, slots=True)
class CounterReading:
    """One cumulative counter state."""

    value: float
    unit: str
    timestamp: datetime

    @property
    def kwh(self) -> float:
        return energy_to_kwh(self.value, self.unit)


@dataclass(frozen=True, slots=True)
class DerivedInterval:
    """Power derived from an evidenced cumulative-counter interval."""

    start: datetime
    end: datetime
    normalized: NormalizedPower
    import_kwh: float
    export_kwh: float | None


class CounterPowerConverter:
    """Convert cumulative readings without extrapolating through unknown time."""

    def __init__(self) -> None:
        self._previous_import: CounterReading | None = None
        self._previous_export: CounterReading | None = None
        self._last_signature: tuple[object, ...] | None = None

    def update(
        self,
        import_reading: CounterReading,
        export_reading: CounterReading | None = None,
    ) -> DerivedInterval | None:
        for reading in (import_reading, export_reading):
            if reading is not None and (
                reading.timestamp.tzinfo is None or reading.timestamp.utcoffset() is None
            ):
                raise AdapterError("counter timestamp must be timezone-aware")
        signature = (
            import_reading.value,
            import_reading.unit,
            import_reading.timestamp.astimezone(UTC),
            export_reading.value if export_reading else None,
            export_reading.unit if export_reading else None,
            export_reading.timestamp.astimezone(UTC) if export_reading else None,
        )
        if signature == self._last_signature:
            return None
        self._last_signature = signature
        previous_import = self._previous_import
        previous_export = self._previous_export
        self._previous_import = import_reading
        if export_reading is not None:
            self._previous_export = export_reading
        if previous_import is None:
            return None

        start = previous_import.timestamp.astimezone(UTC)
        end = import_reading.timestamp.astimezone(UTC)
        if end <= start:
            raise AdapterError("duplicate or backwards cumulative import reading")
        import_delta = import_reading.kwh - previous_import.kwh
        if import_delta < 0:
            # Establish a fresh baseline after reset; never turn the reset into power.
            raise AdapterError("cumulative import counter reset or rolled over")

        export_delta: float | None = None
        if export_reading is not None and previous_export is not None:
            export_start = previous_export.timestamp.astimezone(UTC)
            export_end = export_reading.timestamp.astimezone(UTC)
            if export_start == start and export_end == end:
                export_delta = export_reading.kwh - previous_export.kwh
                if export_delta < 0:
                    # Import remains independently evidenced. Treat export as
                    # unknown for this interval and use the reset reading as its
                    # new baseline instead of discarding valid imported energy.
                    export_delta = None

        hours = (end - start).total_seconds() / 3600.0
        import_kw = import_delta / hours
        export_kw = export_delta / hours if export_delta is not None else None
        signed_kw = import_kw - (export_kw or 0.0)
        return DerivedInterval(
            start=start,
            end=end,
            normalized=NormalizedPower(
                signed_kw=signed_kw,
                import_kw=import_kw,
                export_kw=export_kw,
                export_known=export_kw is not None,
            ),
            import_kwh=import_delta,
            export_kwh=export_delta,
        )


CAPABILITIES = {
    "signed_power": SourceCapabilities(True, True, True),
    "separate_power": SourceCapabilities(True, True, True),
    "import_only": SourceCapabilities(True, False, True),
    "cumulative_energy": SourceCapabilities(False, False, False),
}
