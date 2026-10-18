"""Home Assistant runtime bridge for the pure calculation engine."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import partial

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_state_report_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .adapters import AdapterError, SignedPowerAdapter
from .archive import ArchiveRecord, QuarterArchive
from .backfill import reconstruct_quarters
from .const import (
    CONF_POSITIVE_MEANS_IMPORT,
    CONF_POWER_ENTITY,
    CONF_RETENTION,
    CONF_SAFETY_MARGIN_KW,
    CONF_SIMULATION_ENABLED,
    CONF_SIMULATION_TARGET_KW,
    CONF_SMOOTHING_SECONDS,
    CONF_SUSTAINED_HORIZON_MINUTES,
    CONF_TARGET_KW,
    DEFAULT_RETENTION,
    DEFAULT_SAFETY_MARGIN_KW,
    DEFAULT_SMOOTHING_SECONDS,
    DEFAULT_STALE_AFTER_SECONDS,
    DEFAULT_SUSTAINED_HORIZON_MINUTES,
)
from .engine import (
    EPSILON,
    CalculationError,
    CompletedQuarter,
    DataQuality,
    EngineSnapshot,
    FixedQuarterEngine,
    PowerSample,
)
from .sustained import SustainedForecast, calculate_sustained_forecast

_LOGGER = logging.getLogger(__name__)


class GridMonitorRuntime:
    """Translate HA state changes into normalized engine samples."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        configured = {**entry.data, **entry.options}
        self.power_entity = str(configured[CONF_POWER_ENTITY])
        self.positive_means_import = bool(configured[CONF_POSITIVE_MEANS_IMPORT])
        self.adapter = SignedPowerAdapter(positive_means_import=self.positive_means_import)
        self.engine = FixedQuarterEngine(
            stale_after_seconds=DEFAULT_STALE_AFTER_SECONDS,
            source_id=self.power_entity,
        )
        self.snapshot: EngineSnapshot | None = None
        self.sustained_forecast: SustainedForecast | None = None
        self._listeners: set[Callable[[], None]] = set()
        self._unsubscribers: list[Callable[[], None]] = []
        self.namespace = entry.entry_id
        self.archive = QuarterArchive(
            hass.config.path(".storage", f"si_grid_monitor_{entry.entry_id}.db")
        )
        self.source_epoch = 0
        self._stored_completed = 0
        self._last_checkpoint_utc: datetime | None = None
        self._backfill_task = None

    @property
    def settings(self) -> dict[str, float | int | bool | str]:
        """Return effective editable settings."""

        data = {**self.entry.data, **self.entry.options}
        return {
            CONF_TARGET_KW: float(data[CONF_TARGET_KW]),
            CONF_SAFETY_MARGIN_KW: float(data.get(CONF_SAFETY_MARGIN_KW, DEFAULT_SAFETY_MARGIN_KW)),
            CONF_SMOOTHING_SECONDS: int(
                data.get(CONF_SMOOTHING_SECONDS, DEFAULT_SMOOTHING_SECONDS)
            ),
            CONF_RETENTION: str(data.get(CONF_RETENTION, DEFAULT_RETENTION)),
            CONF_SIMULATION_ENABLED: bool(data.get(CONF_SIMULATION_ENABLED, False)),
            CONF_SIMULATION_TARGET_KW: float(
                data.get(CONF_SIMULATION_TARGET_KW, data[CONF_TARGET_KW])
            ),
            CONF_SUSTAINED_HORIZON_MINUTES: int(
                data.get(
                    CONF_SUSTAINED_HORIZON_MINUTES,
                    DEFAULT_SUSTAINED_HORIZON_MINUTES,
                )
            ),
        }

    @property
    def effective_target_kw(self) -> float:
        settings = self.settings
        return float(
            settings[CONF_SIMULATION_TARGET_KW]
            if settings[CONF_SIMULATION_ENABLED]
            else settings[CONF_TARGET_KW]
        )

    async def async_start(self) -> None:
        """Read the current state and register state/timer listeners."""

        await self.hass.async_add_executor_job(self.archive.open)
        self.source_epoch = await self.hass.async_add_executor_job(
            partial(
                self.archive.register_source_epoch,
                namespace=self.namespace,
                source_id=self.power_entity,
                positive_means_import=self.positive_means_import,
                effective_utc=dt_util.utcnow(),
            )
        )
        checkpoint = await self.hass.async_add_executor_job(
            self.archive.load_checkpoint, self.namespace
        )
        if checkpoint is not None:
            self.engine.restore_checkpoint(checkpoint)

        current = self.hass.states.get(self.power_entity)
        if current is not None:
            self._ingest_state(current)

        self._unsubscribers.append(
            async_track_state_change_event(
                self.hass, [self.power_entity], self._async_state_changed
            )
        )
        self._unsubscribers.append(
            async_track_state_report_event(
                self.hass, [self.power_entity], self._async_state_changed
            )
        )
        self._backfill_task = self.hass.async_create_task(
            self._async_backfill_recorder(), "SI Grid Monitor recorder backfill"
        )
        self._unsubscribers.append(
            async_track_time_interval(self.hass, self._async_tick, timedelta(seconds=1))
        )

    async def async_stop(self) -> None:
        """Remove runtime listeners."""

        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        self._listeners.clear()
        if self._backfill_task is not None and not self._backfill_task.done():
            self._backfill_task.cancel()
        await self.hass.async_add_executor_job(self.archive.close)

    @callback
    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register an entity state listener."""

        self._listeners.add(listener)

        @callback
        def remove() -> None:
            self._listeners.discard(listener)

        return remove

    @callback
    def _async_state_changed(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        if isinstance(new_state, State):
            self._ingest_state(new_state)

    @callback
    def _async_tick(self, now) -> None:
        self._refresh(now)

    @callback
    def _ingest_state(self, state: State) -> None:
        if state.state in {"unknown", "unavailable", "none", ""}:
            return
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        if not isinstance(unit, str):
            _LOGGER.warning("Power source %s has no W/kW unit", self.power_entity)
            return
        try:
            normalized = self.adapter.normalize(state.state, unit)
            timestamp = state.last_reported or state.last_updated
            self.engine.ingest(PowerSample(timestamp, normalized.signed_kw))
        except (AdapterError, CalculationError) as err:
            _LOGGER.warning("Rejected power sample from %s: %s", self.power_entity, err)
            return
        self._refresh(dt_util.utcnow())

    @callback
    def _refresh(self, now) -> None:
        if self.engine.last_sample is None:
            return
        settings = self.settings
        try:
            self.snapshot = self.engine.snapshot(
                now=now,
                target_kw=self.effective_target_kw,
                safety_margin_kw=float(settings[CONF_SAFETY_MARGIN_KW]),
                smoothing_seconds=int(settings[CONF_SMOOTHING_SECONDS]),
            )
            latest = self.engine.last_sample
            now_utc = now.astimezone(UTC)
            smoothing_seconds = int(settings[CONF_SMOOTHING_SECONDS])
            operational_target = max(
                0.0,
                self.effective_target_kw - float(settings[CONF_SAFETY_MARGIN_KW]),
            )
            self.sustained_forecast = calculate_sustained_forecast(
                now=now_utc,
                current_import_kwh=self.snapshot.quarter_import_kwh,
                current_unrecoverable=self.snapshot.projection.unrecoverable,
                recent_segments=self.engine.buffer.segments(
                    end=now_utc, window_seconds=smoothing_seconds
                ),
                latest_signed_kw=self.snapshot.current_signed_power_kw,
                measurement_age_seconds=(
                    (now_utc - latest.timestamp_utc).total_seconds() if latest is not None else None
                ),
                smoothing_seconds=smoothing_seconds,
                horizon_minutes=int(settings[CONF_SUSTAINED_HORIZON_MINUTES]),
                target_for_quarter=lambda _start, _end: operational_target,
                stale_after_seconds=DEFAULT_STALE_AFTER_SECONDS,
            )
        except CalculationError as err:
            _LOGGER.warning("Could not refresh SI Grid Monitor: %s", err)
            return
        self._drain_completed()
        self._checkpoint_if_due(now)
        for listener in tuple(self._listeners):
            listener()

    @callback
    def _drain_completed(self) -> None:
        while self._stored_completed < len(self.engine.completed):
            quarter = self.engine.completed[self._stored_completed]
            self._stored_completed += 1
            self.hass.async_create_task(self._async_store_quarter(quarter))

    async def _async_store_quarter(
        self, quarter: CompletedQuarter, provenance: str = "live_reconstructed"
    ) -> None:
        settings = self.settings
        # Permanent history always stores the genuine configured target. A live
        # simulation threshold may drive entities, but never contaminates records.
        target = float(settings[CONF_TARGET_KW])
        complete = quarter.quality not in {
            DataQuality.INCOMPLETE,
            DataQuality.UNAVAILABLE,
        }
        utilization = 100.0 * quarter.import_demand_kw / target if complete and target > 0 else None
        exceeded = quarter.import_demand_kw > target + EPSILON if complete else None
        record = ArchiveRecord(
            namespace=self.namespace,
            start_utc=quarter.start_utc,
            end_utc=quarter.end_utc,
            import_kwh=quarter.import_kwh,
            export_kwh=quarter.export_kwh,
            signed_average_kw=quarter.signed_average_kw,
            import_demand_kw=quarter.import_demand_kw,
            coverage_seconds=quarter.coverage_seconds,
            gap_seconds=quarter.gap_seconds,
            quality=quarter.quality.value,
            provenance=provenance,
            source_id=quarter.source_id,
            source_epoch=self.source_epoch,
            contractual_target_kw=float(settings[CONF_TARGET_KW]),
            safety_margin_kw=float(settings[CONF_SAFETY_MARGIN_KW]),
            operational_target_kw=max(0.0, target - float(settings[CONF_SAFETY_MARGIN_KW])),
            utilization_pct=utilization,
            exceeded=exceeded,
            excess_kw=(
                max(0.0, quarter.import_demand_kw - target) if exceeded is not None else None
            ),
            simulation=False,
        )
        await self.hass.async_add_executor_job(self.archive.upsert_quarter, record)

    async def _async_backfill_recorder(self) -> None:
        """Backfill missing completed quarters from detailed recorder states."""

        try:
            from homeassistant.components.recorder.history import get_significant_states
            from homeassistant.helpers.recorder import get_instance

            end = dt_util.utcnow()
            latest = await self.hass.async_add_executor_job(
                self.archive.latest_quarter_end, self.namespace
            )
            start = latest or datetime(1970, 1, 1, tzinfo=UTC)
            history = await get_instance(self.hass).async_add_executor_job(
                partial(
                    get_significant_states,
                    self.hass,
                    start,
                    end,
                    entity_ids=[self.power_entity],
                    include_start_time_state=True,
                    significant_changes_only=False,
                    minimal_response=False,
                    no_attributes=False,
                )
            )
            samples: list[PowerSample] = []
            for state in history.get(self.power_entity, []):
                unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
                if not isinstance(unit, str) or state.state in {
                    "unknown",
                    "unavailable",
                    "none",
                    "",
                }:
                    continue
                try:
                    normalized = self.adapter.normalize(state.state, unit)
                    timestamp = state.last_reported or state.last_updated
                    samples.append(PowerSample(timestamp, normalized.signed_kw))
                except (AdapterError, CalculationError):
                    continue
            quarters = reconstruct_quarters(
                samples,
                end_utc=end,
                source_id=self.power_entity,
                stale_after_seconds=DEFAULT_STALE_AFTER_SECONDS,
            )
            for quarter in quarters:
                await self._async_store_quarter(quarter, provenance="recorder_reconstructed")
        except Exception:  # recorder availability/API failures must not stop live data
            _LOGGER.exception("SI Grid Monitor recorder backfill did not complete")

    @callback
    def _checkpoint_if_due(self, now: datetime) -> None:
        now_utc = now.astimezone(UTC)
        if self._last_checkpoint_utc is not None and (
            now_utc - self._last_checkpoint_utc
        ) < timedelta(seconds=30):
            return
        payload = self.engine.checkpoint()
        if payload is None:
            return
        self._last_checkpoint_utc = now_utc
        self.hass.async_create_task(self._async_save_checkpoint(payload))

    async def _async_save_checkpoint(self, payload: dict[str, object]) -> None:
        await self.hass.async_add_executor_job(
            self.archive.save_checkpoint, self.namespace, payload
        )
