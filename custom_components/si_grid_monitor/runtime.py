"""Home Assistant runtime bridge for the pure calculation engine."""

from __future__ import annotations

import asyncio
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
from .archive import (
    ArchivedQuarterSnapshot,
    ConfigurationEpoch,
    ConfigurationResolution,
    ConfigurationStatus,
    QuarterArchive,
    archive_record_from_quarter,
    tariff_for_configuration,
)
from .backfill import (
    HistoricalPowerReading,
    normalize_historical_readings,
    reconstruct_quarters,
)
from .const import (
    CONF_ALLOW_PROVISIONAL_TARIFF,
    CONF_CONTRACTED_POWER_PERIODS,
    CONF_POSITIVE_MEANS_IMPORT,
    CONF_POWER_ENTITY,
    CONF_RETENTION,
    CONF_SAFETY_MARGIN_KW,
    CONF_SIMULATION_ENABLED,
    CONF_SIMULATION_TARGET_KW,
    CONF_SMOOTHING_SECONDS,
    CONF_SUSTAINED_HORIZON_MINUTES,
    CONF_TARGET_B1_KW,
    CONF_TARGET_B2_KW,
    CONF_TARGET_B3_KW,
    CONF_TARGET_B4_KW,
    CONF_TARGET_B5_KW,
    CONF_TARGET_KW,
    DEFAULT_RETENTION,
    DEFAULT_SAFETY_MARGIN_KW,
    DEFAULT_SMOOTHING_SECONDS,
    DEFAULT_STALE_AFTER_SECONDS,
    DEFAULT_SUSTAINED_HORIZON_MINUTES,
)
from .contracted_power import (
    ContractedPowerPeriod,
    ContractedPowerSchedule,
    contracted_power_schedule_from_json,
)
from .engine import (
    EPSILON,
    CalculationError,
    CompletedQuarter,
    DataQuality,
    EngineSnapshot,
    FixedQuarterEngine,
    PowerSample,
    quarter_bounds,
)
from .sustained import SustainedForecast, calculate_sustained_forecast
from .tariffs import SlovenianTariffCalendar, TariffClassification
from .tariffs.models import RuleStatus
from .task_queue import ArchiveTaskQueue

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
        self.source_semantics_id = (
            f"{self.power_entity}|positive_means_import={self.positive_means_import}"
        )
        self.engine = FixedQuarterEngine(
            stale_after_seconds=DEFAULT_STALE_AFTER_SECONDS,
            source_id=self.source_semantics_id,
        )
        self.snapshot: EngineSnapshot | None = None
        self.sustained_forecast: SustainedForecast | None = None
        self.tariff_calendar = SlovenianTariffCalendar(
            allow_provisional=bool(configured.get(CONF_ALLOW_PROVISIONAL_TARIFF, False))
        )
        try:
            self.contracted_power_schedule = contracted_power_schedule_from_json(
                configured.get(CONF_CONTRACTED_POWER_PERIODS, "[]")
            )
            self._contracted_power_configuration_error: str | None = None
        except ValueError as err:
            self.contracted_power_schedule = ContractedPowerSchedule(())
            self._contracted_power_configuration_error = str(err)
        self.current_tariff: TariffClassification | None = None
        self.next_tariff: TariffClassification | None = None
        self.time_to_next_tariff_seconds: float | None = None
        self._tariff_signature: tuple[object, ...] | None = None
        self.current_contractual_available = False
        self.current_contractual_confirmed = False
        self.contractual_status_reason: str | None = None
        self.sustained_status_reason: str | None = None
        self.archived_last_completed: ArchivedQuarterSnapshot | None = None
        self._listeners: set[Callable[[], None]] = set()
        self._unsubscribers: list[Callable[[], None]] = []
        self.namespace = entry.entry_id
        self.archive = QuarterArchive(
            hass.config.path(".storage", f"si_grid_monitor_{entry.entry_id}.db")
        )
        self.configuration_epoch: ConfigurationEpoch | None = None
        self._stored_completed = 0
        self._last_checkpoint_utc: datetime | None = None
        self._backfill_task: asyncio.Task[None] | None = None
        self._completed_store_task: asyncio.Task[None] | None = None
        self._archive_tasks = ArchiveTaskQueue()
        self._archive_operation_lock = asyncio.Lock()

    @property
    def settings(self) -> dict[str, float | int | bool | str]:
        """Return effective editable settings."""

        data = {**self.entry.data, **self.entry.options}
        legacy_target = float(data[CONF_TARGET_KW])
        return {
            CONF_TARGET_KW: float(data[CONF_TARGET_KW]),
            CONF_TARGET_B1_KW: float(data.get(CONF_TARGET_B1_KW, legacy_target)),
            CONF_TARGET_B2_KW: float(data.get(CONF_TARGET_B2_KW, legacy_target)),
            CONF_TARGET_B3_KW: float(data.get(CONF_TARGET_B3_KW, legacy_target)),
            CONF_TARGET_B4_KW: float(data.get(CONF_TARGET_B4_KW, legacy_target)),
            CONF_TARGET_B5_KW: float(data.get(CONF_TARGET_B5_KW, legacy_target)),
            CONF_ALLOW_PROVISIONAL_TARIFF: bool(data.get(CONF_ALLOW_PROVISIONAL_TARIFF, False)),
            CONF_CONTRACTED_POWER_PERIODS: str(data.get(CONF_CONTRACTED_POWER_PERIODS, "[]")),
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
    def effective_target_kw(self) -> float | None:
        settings = self.settings
        if settings[CONF_SIMULATION_ENABLED]:
            return float(settings[CONF_SIMULATION_TARGET_KW])
        tariff = self.current_tariff or self.tariff_calendar.classify(dt_util.utcnow())
        target = self.target_for_tariff(tariff)
        return target

    @property
    def last_completed_import_demand_kw(self) -> float | None:
        if self.engine.completed:
            return self.engine.completed[-1].import_demand_kw
        if self.archived_last_completed is not None:
            return self.archived_last_completed.import_demand_kw
        return None

    @property
    def last_completed_signed_average_kw(self) -> float | None:
        if self.engine.completed:
            return self.engine.completed[-1].signed_average_kw
        if self.archived_last_completed is not None:
            return self.archived_last_completed.signed_average_kw
        return None

    @property
    def current_assignment(self) -> ContractedPowerPeriod | None:
        tariff = self.current_tariff or self.tariff_calendar.classify(dt_util.utcnow())
        return self.contracted_power_schedule.period_for(tariff.local_datetime.date())

    @property
    def current_block_targets_kw(self) -> tuple[float, ...] | None:
        assignment = self.current_assignment
        return assignment.block_targets_kw if assignment is not None else None

    def target_for_tariff(self, tariff: TariffClassification) -> float | None:
        return self.contracted_power_schedule.target_for(tariff)

    def _operational_target_for_quarter(
        self, start: datetime, _end: datetime, safety_margin_kw: float
    ) -> float:
        settings = self.settings
        if settings[CONF_SIMULATION_ENABLED]:
            contracted = float(settings[CONF_SIMULATION_TARGET_KW])
        else:
            tariff = self.tariff_calendar.classify(start)
            selected = self.target_for_tariff(tariff)
            if selected is None:
                raise CalculationError(
                    f"tariff target unavailable for {start.astimezone(UTC).isoformat()}"
                )
            contracted = selected
        return max(0.0, contracted - safety_margin_kw)

    async def async_start(self) -> None:
        """Read the current state and register state/timer listeners."""

        await self.hass.async_add_executor_job(self.archive.open)
        startup_settings = self.settings
        targets = self.current_block_targets_kw or (None, None, None, None, None)
        self.configuration_epoch = await self.hass.async_add_executor_job(
            partial(
                self.archive.register_configuration_epoch,
                namespace=self.namespace,
                source_id=self.power_entity,
                positive_means_import=self.positive_means_import,
                contractual_target_kw=targets[0],
                safety_margin_kw=float(startup_settings[CONF_SAFETY_MARGIN_KW]),
                block_targets_kw=targets,
                allow_provisional_tariff=bool(startup_settings[CONF_ALLOW_PROVISIONAL_TARIFF]),
                contracted_power_schedule=self.contracted_power_schedule,
                effective_utc=dt_util.utcnow(),
            )
        )
        await self.hass.async_add_executor_job(
            self.archive.classify_existing_quarters,
            self.namespace,
            self.tariff_calendar.classify_rule,
        )
        checkpoint, self.archived_last_completed = await asyncio.gather(
            self.hass.async_add_executor_job(self.archive.load_checkpoint, self.namespace),
            self.hass.async_add_executor_job(self.archive.load_latest_quarter, self.namespace),
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
        self._backfill_task = self._archive_tasks.track(
            self.hass.async_create_task(
                self._async_backfill_recorder(), "SI Grid Monitor recorder backfill"
            )
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
        await self._archive_tasks.cancel_and_wait(self._backfill_task)
        self._drain_completed()
        await self._archive_tasks.drain()
        # A prior executor/database failure leaves the durable cursor unchanged.
        # Retry outstanding quarters synchronously before the connection closes.
        await self._async_store_pending_completed()
        payload = self.engine.checkpoint()
        if payload is not None:
            await self._async_save_checkpoint(payload)
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
        settings = self.settings
        now_utc = now.astimezone(UTC)
        current_tariff = self.tariff_calendar.classify(now_utc)
        signature = (
            current_tariff.block,
            current_tariff.rule_version,
            current_tariff.rule_status,
        )
        if (
            signature != self._tariff_signature
            or self.next_tariff is None
            or self.next_tariff.timestamp_utc <= now_utc
        ):
            self.next_tariff = self.tariff_calendar.next_transition(now_utc)
            self._tariff_signature = signature
        self.current_tariff = current_tariff
        self.time_to_next_tariff_seconds = (
            max(0.0, (self.next_tariff.timestamp_utc - now_utc).total_seconds())
            if self.next_tariff is not None
            else None
        )
        if self.engine.last_sample is None:
            for listener in tuple(self._listeners):
                listener()
            return
        target_kw = self.effective_target_kw
        simulation_enabled = bool(settings[CONF_SIMULATION_ENABLED])
        self.current_contractual_available = target_kw is not None
        self.current_contractual_confirmed = (
            target_kw is not None
            and not simulation_enabled
            and current_tariff.rule_status == RuleStatus.OFFICIAL
        )
        if simulation_enabled:
            self.contractual_status_reason = (
                "simulation threshold is active; results are not contractual"
            )
        elif target_kw is None:
            if self._contracted_power_configuration_error is not None:
                self.contractual_status_reason = self._contracted_power_configuration_error
            elif (
                self.contracted_power_schedule.period_for(current_tariff.local_datetime.date())
                is None
            ):
                self.contractual_status_reason = (
                    "no confirmed contracted-power assignment covers "
                    f"{current_tariff.local_datetime.date().isoformat()}"
                )
            else:
                self.contractual_status_reason = (
                    f"tariff rule status is {current_tariff.rule_status.value}; "
                    "no enabled contractual target is available"
                )
        elif current_tariff.rule_status == RuleStatus.PROVISIONAL:
            self.contractual_status_reason = "tariff rule is provisional and not legally confirmed"
        else:
            self.contractual_status_reason = None
        self.sustained_status_reason = self.contractual_status_reason
        try:
            self.snapshot = self.engine.snapshot(
                now=now,
                target_kw=target_kw,
                safety_margin_kw=float(settings[CONF_SAFETY_MARGIN_KW]),
                smoothing_seconds=int(settings[CONF_SMOOTHING_SECONDS]),
            )
        except CalculationError as err:
            _LOGGER.warning("Could not refresh SI Grid Monitor: %s", err)
            self.snapshot = None
            self.sustained_forecast = None
        else:
            self.sustained_forecast = None
            if self.current_contractual_available:
                latest = self.engine.last_sample
                smoothing_seconds = int(settings[CONF_SMOOTHING_SECONDS])
                try:
                    self.sustained_forecast = calculate_sustained_forecast(
                        now=now_utc,
                        current_import_kwh=self.snapshot.quarter_import_kwh,
                        current_unrecoverable=bool(self.snapshot.projection.unrecoverable),
                        current_quarter_complete=self.snapshot.gap_seconds <= EPSILON,
                        recent_segments=self.engine.buffer.segments(
                            end=now_utc, window_seconds=smoothing_seconds
                        ),
                        latest_signed_kw=self.snapshot.current_signed_power_kw,
                        measurement_age_seconds=(
                            (now_utc - latest.timestamp_utc).total_seconds()
                            if latest is not None
                            else None
                        ),
                        smoothing_seconds=smoothing_seconds,
                        horizon_minutes=int(settings[CONF_SUSTAINED_HORIZON_MINUTES]),
                        target_for_quarter=lambda start, end: self._operational_target_for_quarter(
                            start,
                            end,
                            float(settings[CONF_SAFETY_MARGIN_KW]),
                        ),
                        stale_after_seconds=DEFAULT_STALE_AFTER_SECONDS,
                    )
                except CalculationError as err:
                    self.sustained_status_reason = str(err)
                    _LOGGER.info("Sustained forecast unavailable: %s", err)
        self._drain_completed()
        self._checkpoint_if_due(now)
        for listener in tuple(self._listeners):
            listener()

    @callback
    def _drain_completed(self) -> None:
        if self._completed_store_task is not None and not self._completed_store_task.done():
            return
        if self._stored_completed >= len(self.engine.completed):
            return
        self._completed_store_task = self._archive_tasks.track(
            self.hass.async_create_task(
                self._async_store_pending_completed(),
                "SI Grid Monitor store completed quarters",
            )
        )

    async def _async_store_pending_completed(self) -> None:
        """Store quarters serially and advance only after durable success."""

        while self._stored_completed < len(self.engine.completed):
            quarter = self.engine.completed[self._stored_completed]
            await self._async_store_quarter(quarter)
            self._stored_completed += 1

    async def _async_store_quarter(
        self,
        quarter: CompletedQuarter,
        provenance: str = "live_reconstructed",
        configuration: ConfigurationResolution | None = None,
    ) -> None:
        if configuration is None:
            configuration = await self.hass.async_add_executor_job(
                self.archive.resolve_configuration,
                self.namespace,
                quarter.start_utc,
                quarter.end_utc,
            )
        record = archive_record_from_quarter(
            namespace=self.namespace,
            quarter=quarter,
            configuration=configuration,
            provenance=provenance,
            tariff=tariff_for_configuration(quarter.start_utc, configuration),
        )
        async with self._archive_operation_lock:
            await self.hass.async_add_executor_job(self.archive.upsert_quarter, record)
        self.archived_last_completed = ArchivedQuarterSnapshot(
            start_utc=quarter.start_utc,
            end_utc=quarter.end_utc,
            import_demand_kw=quarter.import_demand_kw,
            signed_average_kw=quarter.signed_average_kw,
            quality=quarter.quality.value,
            provenance=provenance,
        )

    async def _async_backfill_recorder(self) -> None:
        """Backfill missing completed quarters from detailed recorder states."""

        try:
            from homeassistant.components.recorder.history import get_significant_states
            from homeassistant.helpers.recorder import get_instance

            end = dt_util.utcnow()
            latest, epochs = await asyncio.gather(
                self.hass.async_add_executor_job(self.archive.latest_quarter_end, self.namespace),
                self.hass.async_add_executor_job(
                    self.archive.list_configuration_epochs, self.namespace
                ),
            )
            if not epochs:
                return
            # Revisit the newest stored quarter so detailed recorder states can
            # improve a crash-affected incomplete live record.
            requested_start = (
                latest - timedelta(minutes=15) if latest is not None else epochs[0].effective_utc
            )
            start = max(requested_start, epochs[0].effective_utc)
            recorder = get_instance(self.hass)
            for index, epoch in enumerate(epochs):
                epoch_end = epochs[index + 1].effective_utc if index + 1 < len(epochs) else end
                segment_start = max(start, epoch.effective_utc)
                segment_end = min(end, epoch_end)
                if segment_end <= segment_start:
                    continue
                history = await recorder.async_add_executor_job(
                    partial(
                        get_significant_states,
                        self.hass,
                        segment_start,
                        segment_end,
                        entity_ids=[epoch.source_id],
                        include_start_time_state=True,
                        significant_changes_only=False,
                        minimal_response=False,
                        no_attributes=False,
                    )
                )
                readings: list[HistoricalPowerReading] = []
                for state in history.get(epoch.source_id, []):
                    unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
                    if not isinstance(unit, str) or state.state in {
                        "unknown",
                        "unavailable",
                        "none",
                        "",
                    }:
                        continue
                    readings.append(
                        HistoricalPowerReading(
                            timestamp=state.last_reported or state.last_updated,
                            value=state.state,
                            unit=unit,
                        )
                    )
                samples = normalize_historical_readings(
                    readings,
                    positive_means_import=epoch.positive_means_import,
                )
                quarters = reconstruct_quarters(
                    samples,
                    end_utc=segment_end,
                    source_id=(
                        f"{epoch.source_id}|positive_means_import={epoch.positive_means_import}"
                    ),
                    stale_after_seconds=DEFAULT_STALE_AFTER_SECONDS,
                )
                configuration = _resolution_for_epoch(epoch)
                for quarter in quarters:
                    if quarter.start_utc < segment_start or quarter.end_utc > segment_end:
                        continue
                    await self._async_store_quarter(
                        quarter,
                        provenance="recorder_reconstructed",
                        configuration=configuration,
                    )

            # A mid-quarter configuration boundary cannot safely inherit either
            # side's target. Store an unavailable marker only when no better row
            # exists; quality-ranked upsert protects live/observed data.
            for epoch in epochs[1:]:
                if not (start < epoch.effective_utc < end):
                    continue
                bounds = quarter_bounds(epoch.effective_utc)
                if epoch.effective_utc == bounds.start_utc:
                    continue
                unknown = CompletedQuarter(
                    start_utc=bounds.start_utc,
                    end_utc=bounds.end_utc,
                    import_kwh=0.0,
                    export_kwh=0.0,
                    signed_net_kwh=0.0,
                    import_demand_kw=0.0,
                    signed_average_kw=0.0,
                    coverage_seconds=0.0,
                    gap_seconds=900.0,
                    quality=DataQuality.UNAVAILABLE,
                    source_id="configuration_boundary",
                )
                configuration = await self.hass.async_add_executor_job(
                    self.archive.resolve_configuration,
                    self.namespace,
                    bounds.start_utc,
                    bounds.end_utc,
                )
                await self._async_store_quarter(
                    unknown,
                    provenance="configuration_boundary_unavailable",
                    configuration=configuration,
                )
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
        self._archive_tasks.track(
            self.hass.async_create_task(
                self._async_save_checkpoint(payload),
                "SI Grid Monitor save checkpoint",
            )
        )

    async def _async_save_checkpoint(self, payload: dict[str, object]) -> None:
        async with self._archive_operation_lock:
            await self.hass.async_add_executor_job(
                self.archive.save_checkpoint, self.namespace, payload
            )


def _resolution_for_epoch(epoch: ConfigurationEpoch) -> ConfigurationResolution:
    if epoch.contracted_power_periods is not None:
        known = bool(epoch.contracted_power_periods) and epoch.safety_margin_kw is not None
    else:
        known = (
            epoch.contractual_target_kw is not None
            and epoch.safety_margin_kw is not None
            and all(target is not None for target in epoch.block_targets_kw)
        )
    status = ConfigurationStatus.KNOWN if known else ConfigurationStatus.TARGET_UNKNOWN
    return ConfigurationResolution(
        status=status,
        source_id=epoch.source_id,
        positive_means_import=epoch.positive_means_import,
        source_epoch=epoch.epoch,
        contractual_target_kw=epoch.contractual_target_kw,
        safety_margin_kw=epoch.safety_margin_kw,
        block_targets_kw=epoch.block_targets_kw,
        allow_provisional_tariff=epoch.allow_provisional_tariff,
        contracted_power_periods=epoch.contracted_power_periods,
    )
