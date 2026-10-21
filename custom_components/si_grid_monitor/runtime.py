"""Home Assistant runtime bridge for the pure calculation engine."""

from __future__ import annotations

import asyncio
import logging
import uuid
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
from .reconstruction import audit_summary, plan_reconstruction
from .sustained import SustainedForecast, calculate_sustained_forecast
from .tariffs import SlovenianTariffCalendar, TariffClassification
from .tariffs.models import RuleStatus
from .task_queue import ArchiveTaskQueue

_LOGGER = logging.getLogger(__name__)

SHUTDOWN_CANCELLATION_GRACE_SECONDS = 10.0


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
        self._reconstruction_plans: dict[str, dict[str, object]] = {}
        self._shutdown_task: asyncio.Task[None] | None = None
        self._shutdown_complete = False

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

    def dashboard_current(self) -> dict[str, object]:
        """Return a bounded, serializable live view for the authenticated panel."""

        snapshot = self.snapshot
        tariff = self.current_tariff
        assignment = self.current_assignment
        if snapshot is None:
            return {
                "entry_id": self.entry.entry_id,
                "title": self.entry.title,
                "available": False,
                "reason": self.contractual_status_reason or "waiting_for_valid_measurement",
                "trace": [],
            }
        projection = snapshot.projection
        sustained = self.sustained_forecast
        quarter_start = snapshot.bounds.start_utc
        settings = self.settings
        safety_margin_kw = float(settings[CONF_SAFETY_MARGIN_KW])
        simulation_enabled = bool(settings[CONF_SIMULATION_ENABLED])
        confirmed_contractual_target_kw = (
            self.target_for_tariff(tariff)
            if tariff is not None and tariff.rule_status == RuleStatus.OFFICIAL
            else None
        )
        contractual_operational_target_kw = (
            max(0.0, confirmed_contractual_target_kw - safety_margin_kw)
            if confirmed_contractual_target_kw is not None
            else None
        )
        smoothed_future_import_kw = (
            snapshot.smoothed_import.value_kw
            if projection.forecast_smoothed_kw is not None and snapshot.smoothed_import.complete
            else None
        )
        if smoothed_future_import_kw is not None and (
            simulation_enabled
            or (tariff is not None and tariff.rule_status == RuleStatus.PROVISIONAL)
        ):
            smoothed_forecast_reason = self.contractual_status_reason
        elif smoothed_future_import_kw is not None:
            smoothed_forecast_reason = None
        elif projection.forecast_smoothed_kw is None and self.contractual_status_reason:
            smoothed_forecast_reason = self.contractual_status_reason
        elif snapshot.input_stale:
            smoothed_forecast_reason = "latest source measurement is stale"
        else:
            smoothed_forecast_reason = (
                "smoothing window has insufficient valid coverage: "
                f"{snapshot.smoothed_import.coverage_seconds:.1f}/"
                f"{int(settings[CONF_SMOOTHING_SECONDS])} seconds"
            )
        trace = [
            {"timestamp": sample.timestamp_utc.isoformat(), "signed_kw": sample.signed_kw}
            for sample in self.engine.buffer.samples
            if sample.timestamp_utc >= quarter_start
        ]
        source_age_seconds = (
            max(
                0.0,
                (snapshot.now_utc - self.engine.buffer.samples[-1].timestamp_utc).total_seconds(),
            )
            if self.engine.buffer.samples
            else None
        )
        return {
            "entry_id": self.entry.entry_id,
            "title": self.entry.title,
            "available": True,
            "now_utc": snapshot.now_utc.isoformat(),
            "quarter": {
                "start_utc": quarter_start.isoformat(),
                "end_utc": snapshot.bounds.end_utc.isoformat(),
                "start_local": snapshot.bounds.start_local.isoformat(),
                "end_local": snapshot.bounds.end_local.isoformat(),
                "elapsed_seconds": snapshot.elapsed_seconds,
                "remaining_seconds": snapshot.remaining_seconds,
                "import_kwh": snapshot.quarter_import_kwh,
                "export_kwh": snapshot.quarter_export_kwh,
                "signed_net_kwh": snapshot.quarter_signed_net_kwh,
                "import_average_kw": snapshot.current_import_average_kw,
                "signed_average_kw": snapshot.current_signed_average_kw,
                "coverage_seconds": snapshot.coverage_seconds,
                "gap_seconds": snapshot.gap_seconds,
                "quality": snapshot.quality.value,
            },
            "power": {
                "signed_kw": snapshot.current_signed_power_kw,
                "import_kw": (
                    max(0.0, snapshot.current_signed_power_kw)
                    if snapshot.current_signed_power_kw is not None
                    else None
                ),
                "export_kw": (
                    max(0.0, -snapshot.current_signed_power_kw)
                    if snapshot.current_signed_power_kw is not None
                    else None
                ),
                "input_stale": snapshot.input_stale,
                "source_age_seconds": source_age_seconds,
            },
            "tariff": {
                "block": tariff.block if tariff else None,
                "season": tariff.season.value if tariff else None,
                "day_type": tariff.day_type.value if tariff else None,
                "rule_status": tariff.rule_status.value if tariff else None,
                "rule_version": tariff.rule_version if tariff else None,
                "target_kw": self.effective_target_kw,
                "contractual_target_kw": confirmed_contractual_target_kw,
                "contractual_operational_target_kw": contractual_operational_target_kw,
                "safety_margin_kw": safety_margin_kw,
                "simulation_enabled": simulation_enabled,
                "simulation_target_kw": (
                    float(settings[CONF_SIMULATION_TARGET_KW]) if simulation_enabled else None
                ),
                "assignment_effective_from": (
                    assignment.effective_from.isoformat() if assignment else None
                ),
                "assignment_effective_to": (
                    assignment.effective_to.isoformat() if assignment else None
                ),
            },
            "projection": {
                "operational_target_kw": projection.operational_target_kw,
                "budget_kwh": projection.budget_kwh,
                "budget_remaining_kwh": projection.budget_remaining_kwh,
                "allowed_remaining_import_kw": projection.allowed_remaining_import_kw,
                "forecast_instant_kw": projection.forecast_instant_kw,
                "forecast_smoothed_kw": projection.forecast_smoothed_kw,
                "smoothed_future_import_kw": smoothed_future_import_kw,
                "smoothed_future_anchor_utc": (
                    snapshot.now_utc.isoformat() if smoothed_future_import_kw is not None else None
                ),
                "smoothed_future_end_utc": (
                    snapshot.bounds.end_utc.isoformat()
                    if smoothed_future_import_kw is not None
                    else None
                ),
                "smoothed_future_quality": (
                    "simulation"
                    if smoothed_future_import_kw is not None and simulation_enabled
                    else "provisional"
                    if smoothed_future_import_kw is not None
                    and tariff is not None
                    and tariff.rule_status == RuleStatus.PROVISIONAL
                    else "estimated"
                    if smoothed_future_import_kw is not None
                    else "unavailable"
                ),
                "smoothed_future_reason": smoothed_forecast_reason,
                "forecast_instant_utilization_pct": (projection.forecast_instant_utilization_pct),
                "forecast_smoothed_utilization_pct": (projection.forecast_smoothed_utilization_pct),
                "current_utilization_pct": projection.current_utilization_pct,
                "can_add_kw": projection.can_add_kw,
                "must_reduce_kw": projection.must_reduce_kw,
                "unrecoverable": projection.unrecoverable,
                "projected_exceedance": projection.projected_exceedance,
            },
            "sustained": (
                {
                    "can_add_kw": sustained.can_add_kw,
                    "must_reduce_kw": sustained.must_reduce_kw,
                    "quality": sustained.quality.value,
                    "horizon_minutes": sustained.horizon_minutes,
                    "smoothing_seconds": sustained.smoothing_seconds,
                    "coverage_seconds": sustained.coverage_seconds,
                    "limiting_quarter_start_utc": (
                        sustained.limiting_quarter_start_utc.isoformat()
                        if sustained.limiting_quarter_start_utc
                        else None
                    ),
                    "limiting_target_kw": sustained.limiting_target_kw,
                    "reason": sustained.reason,
                    "assumption": sustained.assumption,
                }
                if sustained
                else {"quality": "unavailable", "reason": self.sustained_status_reason}
            ),
            "contractual_available": self.current_contractual_available,
            "contractual_confirmed": self.current_contractual_confirmed,
            "contractual_status_reason": self.contractual_status_reason,
            "last_completed_import_demand_kw": self.last_completed_import_demand_kw,
            "last_completed_signed_average_kw": self.last_completed_signed_average_kw,
            "trace": trace,
            "trace_stale_after_seconds": DEFAULT_STALE_AFTER_SECONDS,
            "detailed_trace_provenance": "bounded_runtime_samples",
        }

    def dashboard_transitions(
        self, *, limit: int = 3, lookahead_days: int = 31
    ) -> dict[str, object]:
        """Return tariff changes and the next verified lower contracted target."""

        now = (self.snapshot.now_utc if self.snapshot else dt_util.utcnow()).astimezone(UTC)
        current = self.tariff_calendar.classify(now)
        current_target = self.target_for_tariff(current)
        transitions: list[dict[str, object]] = []
        lower: dict[str, object] | None = None
        previous = current
        cursor = quarter_bounds(now).end_utc
        end = now + timedelta(days=lookahead_days)
        while cursor <= end and (len(transitions) < limit or lower is None):
            candidate = self.tariff_calendar.classify(cursor)
            if (candidate.block, candidate.rule_status) != (
                previous.block,
                previous.rule_status,
            ):
                target = self.target_for_tariff(candidate)
                item = {
                    "timestamp_utc": cursor.isoformat(),
                    "local_datetime": candidate.local_datetime.isoformat(),
                    "from_block": previous.block,
                    "to_block": candidate.block,
                    "from_target_kw": self.target_for_tariff(previous),
                    "to_target_kw": target,
                    "rule_status": candidate.rule_status.value,
                    "seconds_until": max(0.0, (cursor - now).total_seconds()),
                    "difference_kw": (
                        target - self.target_for_tariff(previous)
                        if target is not None and self.target_for_tariff(previous) is not None
                        else None
                    ),
                    "direction": (
                        "decrease"
                        if target is not None
                        and self.target_for_tariff(previous) is not None
                        and target < self.target_for_tariff(previous)
                        else "increase"
                        if target is not None
                        and self.target_for_tariff(previous) is not None
                        and target > self.target_for_tariff(previous)
                        else "unchanged"
                        if target is not None and self.target_for_tariff(previous) is not None
                        else "unknown"
                    ),
                }
                if len(transitions) < limit:
                    transitions.append(item)
                if (
                    lower is None
                    and current_target is not None
                    and target is not None
                    and target < current_target
                    and candidate.rule_status == RuleStatus.OFFICIAL
                ):
                    lower = {
                        **item,
                        "decrease_kw": current_target - target,
                        "inside_sustained_horizon": (
                            (cursor - now).total_seconds()
                            <= int(self.settings[CONF_SUSTAINED_HORIZON_MINUTES]) * 60
                        ),
                        "forecast_status": (
                            "reduction_needed"
                            if self.sustained_forecast is not None
                            and self.sustained_forecast.quality.value == "available"
                            and (self.sustained_forecast.must_reduce_kw or 0.0) > EPSILON
                            else "no_reduction_projected"
                            if self.sustained_forecast is not None
                            and self.sustained_forecast.quality.value == "available"
                            else "unavailable"
                        ),
                        "forecast_reason": (
                            self.sustained_forecast.reason
                            if self.sustained_forecast is not None
                            else self.sustained_status_reason
                        ),
                    }
                previous = candidate
            cursor += timedelta(minutes=15)
        return {
            "current_block": current.block,
            "current_target_kw": current_target,
            "transitions": transitions,
            "next_lower_target": lower,
            "lookahead_days": lookahead_days,
            "sustained_horizon_minutes": int(self.settings[CONF_SUSTAINED_HORIZON_MINUTES]),
            "sustained_limiting_quarter_start_utc": (
                self.sustained_forecast.limiting_quarter_start_utc.isoformat()
                if self.sustained_forecast is not None
                and self.sustained_forecast.limiting_quarter_start_utc is not None
                else None
            ),
        }

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
        try:
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
        except (Exception, asyncio.CancelledError):
            for unsubscribe in self._unsubscribers:
                try:
                    unsubscribe()
                except Exception:
                    _LOGGER.exception("Failed to remove listener after runtime startup failure")
            self._unsubscribers.clear()
            try:
                await self._archive_tasks.cancel_and_wait(self._backfill_task)
                await self._archive_tasks.drain()
            except Exception:
                _LOGGER.exception("Failed to drain archive tasks after runtime startup failure")
            try:
                await self.hass.async_add_executor_job(self.archive.close)
            except Exception:
                _LOGGER.exception("Failed to close archive after runtime startup failure")
            raise

    async def async_stop(self) -> None:
        """Finish durable teardown while preserving caller cancellation."""

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # Narrow synchronous test doubles do not provide an event loop.
            await self._async_stop_impl()
            return

        if self._shutdown_task is None:
            self._shutdown_task = asyncio.create_task(
                self._async_stop_impl(), name="SI Grid Monitor durable shutdown"
            )
        try:
            await asyncio.shield(self._shutdown_task)
        except asyncio.CancelledError:
            # Do not let caller cancellation abandon SQLite work. Give the
            # independently running teardown a finite grace period, then
            # propagate cancellation either way. A timed-out task remains
            # registered and can be joined by a later unload/restart attempt.
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._shutdown_task),
                    timeout=SHUTDOWN_CANCELLATION_GRACE_SECONDS,
                )
            except TimeoutError:
                _LOGGER.warning(
                    "SI Grid Monitor shutdown exceeded %.1f second cancellation grace; "
                    "archive cleanup continues in the background",
                    SHUTDOWN_CANCELLATION_GRACE_SECONDS,
                )
            except Exception:
                _LOGGER.exception("SI Grid Monitor shutdown failed after cancellation")
            raise

    @property
    def shutdown_complete(self) -> bool:
        """Return whether archive tasks finished and SQLite closed."""

        return self._shutdown_complete

    async def _async_stop_impl(self) -> None:
        """Run one best-effort durable shutdown sequence."""

        errors: list[Exception] = []
        archive_closed = False
        for unsubscribe in self._unsubscribers:
            try:
                unsubscribe()
            except Exception as err:
                errors.append(err)
                _LOGGER.exception("Failed to remove SI Grid Monitor runtime listener")
        self._unsubscribers.clear()
        self._listeners.clear()
        try:
            await self._archive_tasks.cancel_and_wait(self._backfill_task)
        except Exception as err:
            errors.append(err)
            _LOGGER.exception("Failed to stop SI Grid Monitor recorder backfill")
        try:
            self._drain_completed()
            errors.extend(
                failure
                for failure in await self._archive_tasks.drain()
                if isinstance(failure, Exception)
            )
        except Exception as err:
            errors.append(err)
            _LOGGER.exception("Failed to drain SI Grid Monitor archive tasks")
        # A prior executor/database failure leaves the durable cursor unchanged.
        # Retry outstanding quarters synchronously before the connection closes.
        try:
            await self._async_store_pending_completed()
        except Exception as err:
            errors.append(err)
            _LOGGER.exception("Failed to store pending completed quarters during shutdown")
        try:
            payload = self.engine.checkpoint()
            if payload is not None:
                await self._async_save_checkpoint(payload)
        except Exception as err:
            errors.append(err)
            _LOGGER.exception("Failed to save SI Grid Monitor checkpoint during shutdown")
        try:
            await self.hass.async_add_executor_job(self.archive.close)
            archive_closed = True
        except Exception as err:
            errors.append(err)
            _LOGGER.exception("Failed to close SI Grid Monitor archive during shutdown")
        self._shutdown_complete = archive_closed and not self._archive_tasks.has_active_tasks
        if errors:
            raise ExceptionGroup("SI Grid Monitor shutdown encountered errors", errors)

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

    async def async_audit_recorder_history(
        self, start_utc: datetime, end_utc: datetime
    ) -> dict[str, object]:
        """Dry-run bounded detailed-state reconstruction for known source epochs."""

        from homeassistant.components.recorder.history import get_significant_states
        from homeassistant.helpers.recorder import get_instance

        start = start_utc.astimezone(UTC)
        end = min(end_utc.astimezone(UTC), dt_util.utcnow())
        if end <= start:
            raise ValueError("Recorder audit range is empty")
        epochs = await self.hass.async_add_executor_job(
            self.archive.list_configuration_epochs, self.namespace
        )
        existing = await self.hass.async_add_executor_job(
            self.archive.list_quarters, self.namespace, start, end
        )
        recorder = get_instance(self.hass)
        candidates: dict[str, object] = {}
        queried_chunks = 0
        known_segments = 0
        for index, epoch in enumerate(epochs):
            epoch_end = epochs[index + 1].effective_utc if index + 1 < len(epochs) else end
            segment_start = max(start, epoch.effective_utc)
            segment_end = min(end, epoch_end)
            if segment_end <= segment_start:
                continue
            known_segments += 1
            cursor = segment_start
            while cursor < segment_end:
                desired_end = cursor + timedelta(days=7)
                aligned_end = quarter_bounds(desired_end).start_utc
                chunk_end = min(segment_end, aligned_end)
                if chunk_end <= cursor:
                    chunk_end = segment_end
                history = await recorder.async_add_executor_job(
                    partial(
                        get_significant_states,
                        self.hass,
                        cursor,
                        chunk_end,
                        entity_ids=[epoch.source_id],
                        include_start_time_state=True,
                        significant_changes_only=False,
                        minimal_response=False,
                        no_attributes=False,
                    )
                )
                queried_chunks += 1
                readings = []
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
                    readings, positive_means_import=epoch.positive_means_import
                )
                quarters = reconstruct_quarters(
                    samples,
                    end_utc=chunk_end,
                    source_id=(
                        f"{epoch.source_id}|positive_means_import={epoch.positive_means_import}"
                    ),
                    stale_after_seconds=DEFAULT_STALE_AFTER_SECONDS,
                )
                configuration = _resolution_for_epoch(epoch)
                for quarter in quarters:
                    if quarter.start_utc < cursor or quarter.end_utc > chunk_end:
                        continue
                    record = archive_record_from_quarter(
                        namespace=self.namespace,
                        quarter=quarter,
                        configuration=configuration,
                        provenance="user_confirmed_recorder_reconstruction",
                        tariff=tariff_for_configuration(quarter.start_utc, configuration),
                    )
                    candidates[quarter.start_utc.isoformat()] = record
                cursor = chunk_end
        records = tuple(candidates.values())
        decisions = plan_reconstruction(existing, records)
        summary = audit_summary(decisions)
        token = uuid.uuid4().hex
        self._reconstruction_plans = {
            token: {
                "start_utc": start,
                "end_utc": end,
                "records": records,
                "decisions": decisions,
                "source_id": self.power_entity,
            }
        }
        return {
            "audit_token": token,
            "range": {"start_utc": start.isoformat(), "end_utc": end.isoformat()},
            "summary": summary,
            "candidates": [
                {
                    "start_utc": item.start_utc,
                    "action": item.action,
                    "reason": item.reason,
                    "existing_quality": item.existing_quality,
                    "proposed_quality": item.proposed_quality,
                    "existing_coverage_seconds": item.existing_coverage_seconds,
                    "proposed_coverage_seconds": item.proposed_coverage_seconds,
                    "import_difference_kwh": item.import_difference_kwh,
                    "contractual_status": item.contractual_status,
                }
                for item in decisions
            ],
            "diagnostics": {
                "recorder_query_chunks": queried_chunks,
                "known_configuration_segments": known_segments,
                "unknown_configuration_before": (
                    epochs[0].effective_utc.isoformat()
                    if epochs and start < epochs[0].effective_utc
                    else None
                ),
                "long_term_statistics_used": False,
            },
        }

    async def async_apply_recorder_reconstruction(self, audit_token: str) -> dict[str, object]:
        """Apply one in-memory dry run after a consistent SQLite backup."""

        plan = self._reconstruction_plans.pop(audit_token, None)
        if plan is None:
            raise ValueError("audit token is missing, expired, or already used")
        decisions = plan["decisions"]
        records = plan["records"]
        selected = {
            item.start_utc: item for item in decisions if item.action in {"insert", "improve"}
        }
        summary = audit_summary(decisions)
        job_id = await self.hass.async_add_executor_job(
            lambda: self.archive.begin_reconstruction_job(
                self.namespace,
                plan["start_utc"],
                plan["end_utc"],
                str(plan["source_id"]),
                mode="confirmed_reconstruction",
                summary=summary,
            )
        )
        backup_path = self.archive.path.with_name(
            f"{self.archive.path.stem}.before-reconstruction-{job_id[:12]}.db"
        )
        applied = 0
        try:
            async with self._archive_operation_lock:
                backup = await self.hass.async_add_executor_job(self.archive.backup, backup_path)
                backup_id = await self.hass.async_add_executor_job(
                    self.archive.register_backup, self.namespace, job_id, backup
                )
                for record in records:
                    decision = selected.get(record.start_utc.isoformat())
                    if decision is None:
                        continue
                    changed = await self.hass.async_add_executor_job(
                        lambda record=record, decision=decision: (
                            self.archive.apply_reconstructed_record(
                                job_id,
                                record,
                                reason=decision.reason,
                                expected_fingerprint=decision.expected_fingerprint,
                                planned_action=decision.action,
                            )
                        )
                    )
                    applied += int(changed)
            result = {**summary, "applied_count": applied, "backup_id": backup_id}
            await self.hass.async_add_executor_job(
                self.archive.finish_reconstruction_job, job_id, "completed", result
            )
            return {"job_id": job_id, **result}
        except asyncio.CancelledError:
            await self.hass.async_add_executor_job(
                self.archive.finish_reconstruction_job,
                job_id,
                "cancelled_partial",
                {**summary, "applied_count": applied},
            )
            raise
        except Exception:
            await self.hass.async_add_executor_job(
                self.archive.finish_reconstruction_job,
                job_id,
                "failed_or_partial",
                {**summary, "applied_count": applied},
            )
            raise

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
