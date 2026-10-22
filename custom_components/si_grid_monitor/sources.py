"""Source-mode normalization and cumulative-counter conversion."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from .adapters import AdapterError, NormalizedPower, energy_to_kwh
from .const import COUNTER_BEHAVIORS, COUNTER_IMPORT_ONLY, COUNTER_NET


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
    contractual_import_evidence: bool = True


@dataclass(frozen=True, slots=True)
class _ChannelInterval:
    start: datetime
    end: datetime
    average_kw: float


class CounterPowerConverter:
    """Convert cumulative readings without extrapolating through unknown time.

    Separate import/export channels keep independent baselines and interval
    queues. Their deltas are joined only over time ranges evidenced by both
    channels, so asynchronous state events cannot lose or repeat either delta.
    """

    def __init__(
        self,
        *,
        behavior: str = COUNTER_IMPORT_ONLY,
        positive_means_import: bool = True,
        export_expected: bool = False,
    ) -> None:
        if behavior not in COUNTER_BEHAVIORS:
            raise ValueError(f"unsupported counter behavior: {behavior}")
        self.behavior = behavior
        self.positive_means_import = positive_means_import
        self.export_expected = export_expected
        self._previous: dict[str, CounterReading | None] = {"import": None, "export": None}
        self._queues: dict[str, deque[_ChannelInterval]] = {
            "import": deque(),
            "export": deque(),
        }
        self.last_warnings: tuple[str, ...] = ()

    @staticmethod
    def _validate(reading: CounterReading) -> None:
        if reading.timestamp.tzinfo is None or reading.timestamp.utcoffset() is None:
            raise AdapterError("counter timestamp must be timezone-aware")

    def _channel_delta(
        self,
        channel: str,
        reading: CounterReading,
        *,
        allow_negative: bool,
    ) -> _ChannelInterval | None:
        self._validate(reading)
        previous = self._previous[channel]
        if previous is None:
            self._previous[channel] = reading
            return None
        start = previous.timestamp.astimezone(UTC)
        end = reading.timestamp.astimezone(UTC)
        if end < start:
            raise AdapterError(f"backwards cumulative {channel} reading")
        if end == start:
            if reading.kwh == previous.kwh:
                return None
            raise AdapterError(f"conflicting duplicate-timestamp cumulative {channel} reading")
        self._previous[channel] = reading
        delta = reading.kwh - previous.kwh
        if delta < 0 and not allow_negative:
            self._queues[channel].clear()
            raise AdapterError(f"cumulative {channel} counter reset or rolled over")
        hours = (end - start).total_seconds() / 3600.0
        return _ChannelInterval(start, end, delta / hours)

    @staticmethod
    def _derived(
        interval: _ChannelInterval,
        *,
        import_kw: float,
        export_kw: float | None,
        contractual_import_evidence: bool,
    ) -> DerivedInterval:
        duration_hours = (interval.end - interval.start).total_seconds() / 3600.0
        return DerivedInterval(
            start=interval.start,
            end=interval.end,
            normalized=NormalizedPower(
                signed_kw=import_kw - (export_kw or 0.0),
                import_kw=import_kw,
                export_kw=export_kw,
                export_known=export_kw is not None,
            ),
            import_kwh=import_kw * duration_hours,
            export_kwh=None if export_kw is None else export_kw * duration_hours,
            contractual_import_evidence=contractual_import_evidence,
        )

    def _join_separate_queues(self) -> list[DerivedInterval]:
        results: list[DerivedInterval] = []
        imports = self._queues["import"]
        exports = self._queues["export"]
        while imports and exports:
            imported = imports[0]
            exported = exports[0]
            start = max(imported.start, exported.start)
            end = min(imported.end, exported.end)
            if end <= start:
                if imported.end <= exported.start:
                    imports.popleft()
                if exported.end <= imported.start:
                    exports.popleft()
                continue
            shared = _ChannelInterval(start, end, imported.average_kw)
            results.append(
                self._derived(
                    shared,
                    import_kw=imported.average_kw,
                    export_kw=exported.average_kw,
                    contractual_import_evidence=True,
                )
            )
            if imported.end == end:
                imports.popleft()
            else:
                imports[0] = replace(imported, start=end)
            if exported.end == end:
                exports.popleft()
            else:
                exports[0] = replace(exported, start=end)
        return results

    def update_intervals(
        self,
        primary_reading: CounterReading,
        export_reading: CounterReading | None = None,
    ) -> tuple[DerivedInterval, ...]:
        """Accept new states and return every newly evidenced interval once."""

        warnings: list[str] = []
        if self.behavior == COUNTER_NET:
            try:
                interval = self._channel_delta("import", primary_reading, allow_negative=True)
            except AdapterError as err:
                self.last_warnings = (str(err),)
                raise
            if interval is None:
                self.last_warnings = ()
                return ()
            signed_kw = interval.average_kw * (1.0 if self.positive_means_import else -1.0)
            import_kw = max(0.0, signed_kw)
            export_kw = max(0.0, -signed_kw)
            self.last_warnings = ()
            return (
                self._derived(
                    interval,
                    import_kw=import_kw,
                    export_kw=export_kw,
                    contractual_import_evidence=False,
                ),
            )

        try:
            imported = self._channel_delta("import", primary_reading, allow_negative=False)
        except AdapterError as err:
            imported = None
            warnings.append(str(err))

        if self.behavior == COUNTER_IMPORT_ONLY or not self.export_expected:
            self.last_warnings = tuple(warnings)
            if imported is None:
                if warnings:
                    raise AdapterError(warnings[0])
                return ()
            return (
                self._derived(
                    imported,
                    import_kw=imported.average_kw,
                    export_kw=None,
                    contractual_import_evidence=True,
                ),
            )

        if export_reading is None:
            # Preserve independently evidenced import while export is absent.
            # Reset the export baseline so a later recovery cannot smear its
            # unknown gap over a newly measured import interval.
            self._previous["export"] = None
            self._queues["export"].clear()
            self._queues["import"].clear()
            self.last_warnings = (*warnings, "cumulative export counter is unavailable")
            if imported is None:
                if warnings:
                    raise AdapterError(warnings[0])
                return ()
            return (
                self._derived(
                    imported,
                    import_kw=imported.average_kw,
                    export_kw=None,
                    contractual_import_evidence=True,
                ),
            )

        exported: _ChannelInterval | None = None
        try:
            exported = self._channel_delta("export", export_reading, allow_negative=False)
        except AdapterError as err:
            warnings.append(str(err))
        if imported is not None:
            self._queues["import"].append(imported)
        if exported is not None:
            self._queues["export"].append(exported)

        if any("export counter reset" in warning for warning in warnings):
            results = tuple(
                self._derived(
                    item,
                    import_kw=item.average_kw,
                    export_kw=None,
                    contractual_import_evidence=True,
                )
                for item in self._queues["import"]
            )
            self._queues["import"].clear()
        else:
            results = tuple(self._join_separate_queues())
        self.last_warnings = tuple(warnings)
        if not results and warnings and imported is None and exported is None:
            raise AdapterError(warnings[0])
        return results

    def update(
        self,
        import_reading: CounterReading,
        export_reading: CounterReading | None = None,
    ) -> DerivedInterval | None:
        """Backward-compatible single-interval facade used by pure tests."""

        intervals = self.update_intervals(import_reading, export_reading)
        if len(intervals) > 1:
            raise AdapterError("counter update produced multiple intervals; use update_intervals")
        return intervals[0] if intervals else None


CAPABILITIES = {
    "signed_power": SourceCapabilities(True, True, True),
    "separate_power": SourceCapabilities(True, True, True),
    "import_only": SourceCapabilities(True, False, True),
    "cumulative_energy": SourceCapabilities(False, False, False),
}
