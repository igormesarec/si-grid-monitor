"""Integration-level publishing tests using real SI Grid Monitor entity attributes."""

from __future__ import annotations

import importlib
import json
import math
import sqlite3
import sys
import types
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from custom_components.si_grid_monitor.archive import (
    ConfigurationResolution,
    ConfigurationStatus,
    QuarterArchive,
    archive_record_from_quarter,
)
from custom_components.si_grid_monitor.engine import (
    DataQuality,
    EngineSnapshot,
    FixedQuarterEngine,
    PowerSample,
    Projection,
    WindowAverage,
    quarter_bounds,
)
from custom_components.si_grid_monitor.publishing import (
    FAIL_CLOSED_RECOVERY_KEYS,
    STORAGE_BUDGET_BYTES_PER_YEAR,
    PublicationState,
    PublishingClass,
    PublishingController,
    PublishingSettings,
)
from custom_components.si_grid_monitor.tariffs import SlovenianTariffCalendar


class _Runtime:
    def __init__(self) -> None:
        self.snapshot = None
        self.source_mode = "signed_power"
        self.source_entities = ("sensor.grid",)
        self.instantaneous_power_known = True
        self.export_known = True
        self.source_available = True
        self.source_status_reason = None
        self.current_tariff = None
        self.next_tariff = None
        self.settings = {"simulation_enabled": False}
        self.current_contractual_available = True
        self.current_contractual_confirmed = True
        self.contractual_status_reason = None
        self.current_assignment = None
        self.current_block_targets_kw = (3.5, 3.9, 4.1, 4.2, 4.2)
        self.engine = SimpleNamespace(completed=[])
        self.archived_last_completed = None
        self._last_completed_import_demand_kw = None
        self._last_completed_signed_average_kw = None

    def target_for_tariff(self, tariff):
        if tariff is None or tariff.block is None:
            return None
        return self.current_block_targets_kw[tariff.block - 1]

    @property
    def last_completed_import_demand_kw(self):
        if self.engine.completed:
            return self.engine.completed[-1].import_demand_kw
        return self._last_completed_import_demand_kw

    @last_completed_import_demand_kw.setter
    def last_completed_import_demand_kw(self, value):
        self._last_completed_import_demand_kw = value

    @property
    def last_completed_signed_average_kw(self):
        if self.engine.completed:
            return self.engine.completed[-1].signed_average_kw
        return self._last_completed_signed_average_kw

    @last_completed_signed_average_kw.setter
    def last_completed_signed_average_kw(self, value):
        self._last_completed_signed_average_kw = value


@pytest.fixture(scope="module")
def sensor_module():
    """Load the real sensor module against the minimal HA entity surface."""

    homeassistant = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    homeassistant.__path__ = []
    config_entries = sys.modules.setdefault(
        "homeassistant.config_entries", types.ModuleType("homeassistant.config_entries")
    )
    const = sys.modules.setdefault("homeassistant.const", types.ModuleType("homeassistant.const"))
    core = sys.modules.setdefault("homeassistant.core", types.ModuleType("homeassistant.core"))
    helpers = sys.modules.setdefault(
        "homeassistant.helpers", types.ModuleType("homeassistant.helpers")
    )
    helpers.__path__ = []
    sensor_component = types.ModuleType("homeassistant.components.sensor")

    @dataclass(frozen=True, kw_only=True)
    class _Description:
        key: str
        translation_key: str | None = None
        native_unit_of_measurement: str | None = None
        device_class: str | None = None
        state_class: str | None = None

    class _Entity:
        async def async_added_to_hass(self) -> None:
            return None

        def async_on_remove(self, _callback) -> None:
            return None

    sensor_component.SensorDeviceClass = SimpleNamespace(
        POWER="power", ENERGY="energy", DURATION="duration"
    )
    sensor_component.SensorEntity = _Entity
    sensor_component.SensorEntityDescription = _Description
    sensor_component.SensorStateClass = SimpleNamespace(MEASUREMENT="measurement", TOTAL="total")
    binary_component = types.ModuleType("homeassistant.components.binary_sensor")
    binary_component.BinarySensorEntity = _Entity
    binary_component.BinarySensorEntityDescription = _Description
    components = sys.modules.setdefault(
        "homeassistant.components", types.ModuleType("homeassistant.components")
    )
    components.__path__ = []
    sys.modules["homeassistant.components.sensor"] = sensor_component
    sys.modules["homeassistant.components.binary_sensor"] = binary_component

    config_entries.ConfigEntry = object
    const.PERCENTAGE = "%"
    const.UnitOfEnergy = SimpleNamespace(KILO_WATT_HOUR="kWh")
    const.UnitOfPower = SimpleNamespace(KILO_WATT="kW")
    const.UnitOfTime = SimpleNamespace(SECONDS="s")
    core.HomeAssistant = object
    core.callback = lambda function: function
    device_registry = types.ModuleType("homeassistant.helpers.device_registry")
    device_registry.DeviceInfo = lambda **kwargs: kwargs
    entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")
    entity_platform.AddEntitiesCallback = object
    sys.modules["homeassistant.helpers.device_registry"] = device_registry
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform
    fake_runtime = types.ModuleType("custom_components.si_grid_monitor.runtime")
    fake_runtime.GridMonitorRuntime = object
    existing_runtime = sys.modules.get("custom_components.si_grid_monitor.runtime")
    sys.modules["custom_components.si_grid_monitor.runtime"] = fake_runtime

    module = importlib.import_module("custom_components.si_grid_monitor.sensor")
    binary_module = importlib.import_module("custom_components.si_grid_monitor.binary_sensor")
    yield SimpleNamespace(sensor=module, binary=binary_module)
    sys.modules.pop("custom_components.si_grid_monitor.sensor", None)
    sys.modules.pop("custom_components.si_grid_monitor.binary_sensor", None)
    if existing_runtime is None:
        sys.modules.pop("custom_components.si_grid_monitor.runtime", None)
    else:
        sys.modules["custom_components.si_grid_monitor.runtime"] = existing_runtime


def _entity(key: str, runtime: _Runtime, sensor_module):
    description = next(item for item in sensor_module.sensor.SENSORS if item.key == key)
    entry = SimpleNamespace(entry_id="entry-real", title="Real entity meter")
    return sensor_module.sensor.SIGridSensor(runtime, entry, description)


def _binary_entity(key: str, runtime: _Runtime, sensor_module):
    description = next(item for item in sensor_module.binary.BINARY_SENSORS if item.key == key)
    entry = SimpleNamespace(entry_id="entry-real", title="Real entity meter")
    return sensor_module.binary.SIGridBinarySensor(runtime, entry, description)


def _run_entity(
    entity,
    runtime: _Runtime,
    instants: list[datetime],
    calendar: SlovenianTariffCalendar,
) -> list[PublicationState]:
    writes: list[PublicationState] = []
    controller = PublishingController(PublishingSettings.from_mapping({}))
    controller.register(
        entity.entity_description.key,
        PublishingClass.CONFIGURATION,
        entity._publication_state,
        lambda: writes.append(entity._publication_state()),
    )
    for instant in instants:
        runtime.current_tariff = calendar.classify(instant)
        controller.process(instant)
    return writes


def test_real_tariff_entity_is_stable_for_one_second_classification_hour(sensor_module) -> None:
    runtime = _Runtime()
    entity = _entity("current_tariff_block", runtime, sensor_module)
    calendar = SlovenianTariffCalendar()
    start = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
    writes = _run_entity(
        entity,
        runtime,
        [start + timedelta(seconds=second) for second in range(3600)],
        calendar,
    )

    assert len(writes) == 1
    assert "local_datetime" not in writes[0].attributes
    assert writes[0].attributes["utc_offset_seconds"] == 3600


def test_real_tariff_entity_publishes_material_tariff_contract_and_dst_boundaries(
    sensor_module,
) -> None:
    calendar = SlovenianTariffCalendar()

    runtime = _Runtime()
    block_entity = _entity("current_tariff_block", runtime, sensor_module)
    transition = calendar.next_transition(datetime(2026, 1, 5, 5, 0, tzinfo=UTC))
    assert transition is not None
    tariff_writes = _run_entity(
        block_entity,
        runtime,
        [transition.timestamp_utc + timedelta(seconds=offset) for offset in (-2, -1, 0, 1)],
        calendar,
    )
    assert len(tariff_writes) == 2
    assert tariff_writes[0].value != tariff_writes[1].value

    contract_runtime = _Runtime()
    contract_entity = _entity("current_block_contracted_power", contract_runtime, sensor_module)
    contract_controller = PublishingController(PublishingSettings.from_mapping({}))
    contract_writes: list[float | None] = []
    contract_controller.register(
        "current_block_contracted_power",
        PublishingClass.CONFIGURATION,
        contract_entity._publication_state,
        lambda: contract_writes.append(contract_entity.native_value),
    )
    contract_time = datetime(2026, 10, 25, 11, 0, tzinfo=UTC)
    contract_runtime.current_tariff = calendar.classify(contract_time)
    contract_controller.process(contract_time)
    block = contract_runtime.current_tariff.block
    assert block is not None
    changed = list(contract_runtime.current_block_targets_kw)
    changed[block - 1] += 1.0
    contract_runtime.current_block_targets_kw = tuple(changed)
    contract_controller.process(contract_time + timedelta(seconds=1))
    assert len(contract_writes) == 2
    assert contract_writes[0] != contract_writes[1]

    dst_runtime = _Runtime()
    dst_entity = _entity("current_tariff_block", dst_runtime, sensor_module)
    fallback = datetime(2026, 10, 25, 1, 0, tzinfo=UTC)
    dst_writes = _run_entity(
        dst_entity,
        dst_runtime,
        [fallback + timedelta(seconds=offset) for offset in (-2, -1, 0, 1)],
        calendar,
    )
    assert len(dst_writes) == 2
    assert [item.attributes["utc_offset_seconds"] for item in dst_writes] == [7200, 3600]
    assert [item.attributes["fold"] for item in dst_writes] == [0, 1]


def test_real_day_type_entity_changes_at_local_midnight_without_heartbeat(sensor_module) -> None:
    runtime = _Runtime()
    entity = _entity("current_tariff_day_type", runtime, sensor_module)
    calendar = SlovenianTariffCalendar()
    midnight = datetime(2026, 1, 4, 23, 0, tzinfo=UTC)
    writes = _run_entity(
        entity,
        runtime,
        [midnight + timedelta(seconds=offset) for offset in (-2, -1, 0, 1, 2)],
        calendar,
    )
    assert [item.value for item in writes] == ["nonworking", "working"]


@pytest.mark.parametrize(
    ("source_mode", "export_known"),
    (("signed_power", True), ("separate_power", True), ("import_only", False)),
    ids=("mode-a", "mode-b", "mode-c"),
)
def test_explicit_source_unavailability_immediately_hides_advice(
    sensor_module, source_mode: str, export_known: bool
) -> None:
    runtime = _Runtime()
    runtime.source_mode = source_mode
    runtime.export_known = export_known
    now = datetime(2026, 10, 25, 12, 1, tzinfo=UTC)
    # A genuine measured zero is valid in every active source mode and must not
    # be conflated with the explicit unavailable transition below.
    _prepare_live_runtime(runtime, now, 0.0, stale=False)
    advice = _entity("can_add_power", runtime, sensor_module)
    export_energy = _entity("quarter_export_kwh_so_far", runtime, sensor_module)
    projected = _binary_entity("projected_exceedance", runtime, sensor_module)
    stale = _binary_entity("input_stale", runtime, sensor_module)
    assert advice.available is True
    assert export_energy.available is export_known
    assert projected.available is True
    assert stale.is_on is False

    # No elapsed stale timeout is required: the explicit HA source failure is
    # authoritative immediately, while the last evidenced engine snapshot is
    # retained for archive integrity.
    runtime.source_available = False
    runtime.source_status_reason = "source unavailable"
    assert advice.available is False
    assert export_energy.available is export_known
    assert projected.available is False
    assert stale.is_on is True

    runtime.source_available = True
    runtime.source_status_reason = None
    assert advice.available is True
    assert projected.available is True
    assert stale.is_on is False


def test_natural_staleness_hides_projected_exceedance_without_false_clear(
    sensor_module,
) -> None:
    runtime = _Runtime()
    start = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
    projected = _binary_entity("projected_exceedance", runtime, sensor_module)
    stale = _binary_entity("input_stale", runtime, sensor_module)
    projected_writes: list[tuple[int, bool, bool | None]] = []
    stale_writes: list[tuple[int, bool, bool | None]] = []
    now = start
    projected_controller = PublishingController(PublishingSettings.from_mapping({}))
    stale_controller = PublishingController(PublishingSettings.from_mapping({}))
    projected_controller.register(
        "projected_exceedance",
        PublishingClass.CRITICAL,
        projected._publication_state,
        lambda: projected_writes.append(
            (int((now - start).total_seconds()), projected.available, projected.is_on)
        ),
    )
    stale_controller.register(
        "input_stale",
        PublishingClass.CRITICAL,
        stale._publication_state,
        lambda: stale_writes.append(
            (int((now - start).total_seconds()), stale.available, stale.is_on)
        ),
    )

    for second, is_stale in ((0, False), (59, False), (60, False), (61, True)):
        now = start + timedelta(seconds=second)
        _prepare_live_runtime(runtime, now, 5.0, stale=is_stale)
        runtime.source_available = True  # HA retains the last state silently.
        projected_controller.process(now)
        stale_controller.process(now)

    assert projected_writes == [(0, True, True), (61, False, True)]
    assert stale_writes == [(0, True, False), (61, True, True)]

    for second in range(62, 93):
        now = start + timedelta(seconds=second)
        _prepare_live_runtime(runtime, now, 2.0, stale=False)
        projected_controller.process(now)
        stale_controller.process(now)
    assert projected_writes[-1] == (92, True, False)
    assert stale_writes[-1] == (92, True, False)


def test_natural_staleness_immediately_unpublishes_real_numeric_advice(
    sensor_module,
) -> None:
    """A retained HA source state must not leave optimistic advice available."""

    runtime = _Runtime()
    start = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
    engine = FixedQuarterEngine(stale_after_seconds=60, source_id="mode=signed_power")
    engine.ingest(PowerSample(start, 1.0))
    runtime.engine = engine
    runtime.current_tariff = SlovenianTariffCalendar().classify(start)
    entities = {
        key: _entity(key, runtime, sensor_module)
        for key in (
            "current_power",
            "import_power",
            "export_power",
            "can_add_power",
            "must_reduce_power",
            "forecast_instant_kw",
        )
    }
    projected = _binary_entity("projected_exceedance", runtime, sensor_module)
    stale = _binary_entity("input_stale", runtime, sensor_module)
    writes: dict[str, list[tuple[int, bool, object]]] = {
        key: [] for key in (*entities, "projected_exceedance", "input_stale")
    }
    controller = PublishingController(PublishingSettings.from_mapping({}))
    now = start
    for key, entity in entities.items():
        controller.register(
            key,
            sensor_module.sensor.SENSOR_PUBLISHING_POLICIES[key],
            entity._publication_state,
            lambda key=key, entity=entity: writes[key].append(
                (int((now - start).total_seconds()), entity.available, entity.native_value)
            ),
        )
    for key, entity in (("projected_exceedance", projected), ("input_stale", stale)):
        controller.register(
            key,
            sensor_module.binary.BINARY_SENSOR_PUBLISHING_POLICIES[key],
            entity._publication_state,
            lambda key=key, entity=entity: writes[key].append(
                (int((now - start).total_seconds()), entity.available, entity.is_on)
            ),
        )

    for second in (0, 59, 60, 61):
        now = start + timedelta(seconds=second)
        engine.advance(now)
        runtime.snapshot = engine.snapshot(now=now, target_kw=4.2)
        controller.process(now)

    for key in entities:
        assert writes[key][-1][0:2] == (61, False)
        assert writes[key][-1][2] is None
    assert writes["projected_exceedance"][-1][0:2] == (61, False)
    assert writes["input_stale"][-1] == (61, True, True)

    for second in range(62, 93):
        now = start + timedelta(seconds=second)
        engine.ingest(PowerSample(now, 1.0))
        runtime.snapshot = engine.snapshot(now=now, target_kw=4.2)
        controller.process(now)
    for key in entities:
        assert writes[key][-1][0:2] == (92, True)


def test_every_live_advice_entity_fails_closed_while_static_and_observed_values_remain(
    sensor_module,
) -> None:
    runtime = _Runtime()
    now = datetime(2026, 10, 25, 12, 5, tzinfo=UTC)
    _prepare_live_runtime(runtime, now, 3.0, stale=True)
    runtime.source_available = True
    runtime.current_tariff = SlovenianTariffCalendar().classify(now)
    runtime.sustained_forecast = SimpleNamespace(can_add_kw=1.0, must_reduce_kw=0.0)

    assert sensor_module.sensor.LIVE_ADVICE_SENSOR_KEYS <= FAIL_CLOSED_RECOVERY_KEYS
    for key in sensor_module.sensor.LIVE_ADVICE_SENSOR_KEYS:
        assert _entity(key, runtime, sensor_module).available is False, key

    # Known configuration and already observed partial energy remain truthful;
    # they are not live permission or a fabricated zero measurement.
    assert _entity("target_kw", runtime, sensor_module).available is True
    assert _entity("operational_target_kw", runtime, sensor_module).available is True
    accumulated = _entity("quarter_import_kwh_so_far", runtime, sensor_module)
    assert accumulated.available is True
    assert accumulated.native_value > 0

    unrecoverable = _binary_entity("unrecoverable_interval", runtime, sensor_module)
    assert unrecoverable.is_on is False
    assert unrecoverable.available is False

    _prepare_live_runtime(runtime, now.replace(minute=14), 5.0, stale=True)
    runtime.source_available = True
    proven_unrecoverable = _binary_entity("unrecoverable_interval", runtime, sensor_module)
    assert proven_unrecoverable.is_on is True
    assert proven_unrecoverable.available is True


def test_fresh_live_advice_with_no_numeric_result_is_ha_unavailable(sensor_module) -> None:
    runtime = _Runtime()
    now = datetime(2026, 10, 25, 12, 0, 1, tzinfo=UTC)
    _prepare_live_runtime(runtime, now, 2.0, stale=False)
    smoothed = _entity("forecast_smoothed_kw", runtime, sensor_module)
    assert smoothed.native_value is None
    assert smoothed.available is False


def test_real_entity_fault_callback_publishes_unavailable_and_recovers(sensor_module) -> None:
    runtime = _Runtime()
    now = datetime(2026, 10, 25, 12, 5, tzinfo=UTC)
    _prepare_live_runtime(runtime, now, 3.0, stale=False)
    entity = _entity("can_add_power", runtime, sensor_module)
    writes: list[bool] = []
    entity.async_write_ha_state = lambda: writes.append(entity.available)

    entity._handle_publication_failure()
    assert writes == [False]
    assert entity._publication_state().available is True
    entity._handle_update()
    assert writes == [False, True]


def _live_snapshot(now: datetime, signed_kw: float, *, stale: bool) -> EngineSnapshot:
    bounds = quarter_bounds(now)
    elapsed = max(1.0, (now - bounds.start_utc).total_seconds())
    remaining = max(0.0, (bounds.end_utc - now).total_seconds())
    imported = max(0.0, signed_kw) * elapsed / 3600
    exported = max(0.0, -signed_kw) * elapsed / 3600
    import_average = imported / (elapsed / 3600)
    signed_average = signed_kw
    rolling_coverage = min(900.0, elapsed)
    smoothing_coverage = min(120.0, elapsed)
    return EngineSnapshot(
        bounds=bounds,
        now_utc=now,
        current_signed_power_kw=signed_kw,
        input_stale=stale,
        quarter_import_kwh=imported,
        quarter_export_kwh=exported,
        quarter_signed_net_kwh=imported - exported,
        elapsed_seconds=elapsed,
        remaining_seconds=remaining,
        current_import_average_kw=import_average,
        current_signed_average_kw=signed_average,
        rolling_15m_signed=WindowAverage(
            signed_average, rolling_coverage, 900 - rolling_coverage, elapsed >= 900
        ),
        rolling_15m_import=WindowAverage(
            import_average, rolling_coverage, 900 - rolling_coverage, elapsed >= 900
        ),
        smoothed_signed=WindowAverage(
            signed_average, smoothing_coverage, 120 - smoothing_coverage, elapsed >= 120
        ),
        smoothed_import=WindowAverage(
            import_average, smoothing_coverage, 120 - smoothing_coverage, elapsed >= 120
        ),
        projection=Projection(
            operational_target_kw=3.7,
            budget_kwh=0.925,
            budget_remaining_kwh=0.925 - imported,
            allowed_remaining_import_kw=(
                max(0.0, 0.925 - imported) / (remaining / 3600) if remaining else None
            ),
            forecast_instant_kw=max(0.0, signed_kw),
            forecast_smoothed_kw=max(0.0, signed_kw) if elapsed >= 120 else None,
            forecast_instant_utilization_pct=max(0.0, signed_kw) / 3.9 * 100,
            forecast_smoothed_utilization_pct=(
                max(0.0, signed_kw) / 3.9 * 100 if elapsed >= 120 else None
            ),
            current_utilization_pct=import_average / 3.9 * 100,
            can_add_kw=max(0.0, 3.7 - max(0.0, signed_kw)),
            must_reduce_kw=max(0.0, max(0.0, signed_kw) - 3.7),
            unrecoverable=imported > 0.925,
            projected_exceedance=max(0.0, signed_kw) > 3.9,
        ),
        coverage_seconds=elapsed if not stale else max(0.0, elapsed - 60),
        gap_seconds=0.0 if not stale else min(60.0, elapsed),
        quality=DataQuality.INCOMPLETE if stale else DataQuality.MEASURED_ALIGNED,
    )


def _prepare_live_runtime(runtime: _Runtime, now: datetime, signed_kw: float, stale: bool) -> None:
    runtime.snapshot = _live_snapshot(now, signed_kw, stale=stale)
    runtime.current_tariff = SlovenianTariffCalendar().classify(now)
    runtime.next_tariff = SlovenianTariffCalendar().next_transition(now)
    runtime.time_to_next_tariff_seconds = (
        (runtime.next_tariff.timestamp_utc - now).total_seconds()
        if runtime.next_tariff is not None
        else None
    )
    runtime.source_available = not stale
    runtime.source_status_reason = "source_measurement_stale" if stale else None
    runtime.effective_target_kw = 3.9
    runtime.last_completed_import_demand_kw = 1.5
    runtime.last_completed_signed_average_kw = 1.2
    runtime.current_assignment = SimpleNamespace(
        effective_from="2026-01-01",
        effective_to="2026-12-31",
        provenance="benchmark assignment",
        recorded_on=None,
    )
    runtime.sustained_status_reason = None
    runtime.sustained_forecast = SimpleNamespace(
        can_add_kw=max(0.0, 3.7 - max(0.0, signed_kw)),
        must_reduce_kw=max(0.0, max(0.0, signed_kw) - 3.7),
        quality=SimpleNamespace(value="valid"),
        horizon_minutes=60,
        smoothing_seconds=120,
        measurement_age_seconds=0,
        coverage_seconds=120,
        limiting_quarter_start_utc=quarter_bounds(now).start_utc,
        limiting_quarter_end_utc=quarter_bounds(now).end_utc,
        limiting_target_kw=3.7,
        current_quarter_unrecoverable=False,
        assumption="persistence",
        reason=None,
    )


def test_constant_load_current_energy_is_fresh_and_completed_energy_is_exact(
    sensor_module,
) -> None:
    """A public current-quarter value stays bounded while archive truth stays exact."""

    runtime = _Runtime()
    engine = FixedQuarterEngine(stale_after_seconds=60, source_id="mode=signed_power")
    entity = _entity("quarter_import_kwh_so_far", runtime, sensor_module)
    controller = PublishingController(PublishingSettings.from_mapping({}))
    start = datetime(2026, 4, 2, 10, 0, tzinfo=UTC)
    now = start
    writes: list[tuple[datetime, float, str]] = []
    controller.register(
        "quarter_import_kwh_so_far",
        PublishingClass.QUARTER_ACCUMULATION,
        entity._publication_state,
        lambda: writes.append(
            (
                now,
                float(entity.native_value),
                entity.extra_state_attributes["quarter_start_utc"],
            )
        ),
    )

    for second in range(901):
        now = start + timedelta(seconds=second)
        engine.ingest(PowerSample(now, 3.0))
        runtime.snapshot = engine.snapshot(now=now, target_kw=4.2)
        runtime.current_tariff = SlovenianTariffCalendar().classify(now)
        controller.process(now)

    for minute in (1, 5, 10, 14):
        checkpoint = start + timedelta(minutes=minute)
        published_at, public_value, _quarter_id = max(
            item for item in writes if item[0] <= checkpoint and item[2] == start.isoformat()
        )
        assert (checkpoint - published_at).total_seconds() <= 180
        assert public_value == pytest.approx(
            3.0 * (published_at - start).total_seconds() / 3600,
            abs=1e-9,
        )

    assert engine.completed[-1].import_kwh == pytest.approx(0.750, abs=1e-9)
    boundary_write = writes[-1]
    assert boundary_write[0] == start + timedelta(minutes=15)
    assert boundary_write[2] == (start + timedelta(minutes=15)).isoformat()
    assert boundary_write[1] == pytest.approx(0.0, abs=1e-9)


def test_constant_export_current_energy_is_fresh_and_completed_energy_is_exact(
    sensor_module,
    tmp_path: Path,
) -> None:
    """Export accumulation has the same bounded public freshness as import."""

    runtime = _Runtime()
    engine = FixedQuarterEngine(stale_after_seconds=60, source_id="mode=signed_power")
    runtime.engine = engine
    entity = _entity("quarter_export_kwh_so_far", runtime, sensor_module)
    controller = PublishingController(PublishingSettings.from_mapping({}))
    start = datetime(2026, 4, 2, 10, 0, tzinfo=UTC)
    now = start
    writes: list[tuple[datetime, float, str]] = []
    controller.register(
        "quarter_export_kwh_so_far",
        sensor_module.sensor.SENSOR_PUBLISHING_POLICIES["quarter_export_kwh_so_far"],
        entity._publication_state,
        lambda: writes.append(
            (
                now,
                float(entity.native_value),
                entity.extra_state_attributes["quarter_start_utc"],
            )
        ),
    )

    for second in range(901):
        now = start + timedelta(seconds=second)
        engine.ingest(PowerSample(now, -3.0))
        runtime.snapshot = engine.snapshot(now=now, target_kw=4.2)
        runtime.current_tariff = SlovenianTariffCalendar().classify(now)
        controller.process(now)

    expected_public = {
        1: (start + timedelta(minutes=1), 0.050),
        5: (start + timedelta(minutes=4), 0.200),
        10: (start + timedelta(minutes=10), 0.500),
        14: (start + timedelta(minutes=13), 0.650),
    }
    for minute, expected_energy in ((1, 0.050), (5, 0.250), (10, 0.500), (14, 0.700)):
        checkpoint = start + timedelta(minutes=minute)
        published_at, public_value, _quarter_id = max(
            item for item in writes if item[0] <= checkpoint and item[2] == start.isoformat()
        )
        assert (checkpoint - published_at).total_seconds() <= 180
        expected_published_at, expected_public_value = expected_public[minute]
        assert published_at == expected_published_at
        assert public_value == pytest.approx(expected_public_value, abs=1e-9)
        # The authoritative engine value at the requested elapsed instant is
        # exact even when the bounded public mirror is intentionally older.
        assert 3.0 * (checkpoint - start).total_seconds() / 3600 == pytest.approx(
            expected_energy, abs=1e-9
        )

    completed = engine.completed[-1]
    assert completed.export_kwh == pytest.approx(0.750, abs=1e-9)
    assert completed.import_kwh == pytest.approx(0.0, abs=1e-9)
    assert completed.import_demand_kw == pytest.approx(0.0, abs=1e-9)
    archive = QuarterArchive(tmp_path / "export-quarter.db")
    archive.open()
    configuration = ConfigurationResolution(
        status=ConfigurationStatus.KNOWN,
        source_id="mode=signed_power",
        positive_means_import=True,
        source_epoch=1,
        contractual_target_kw=4.2,
        safety_margin_kw=0.0,
        block_targets_kw=(4.2, 4.2, 4.2, 4.2, 4.2),
    )
    record = archive_record_from_quarter(
        namespace="meter-export",
        quarter=completed,
        configuration=configuration,
        provenance="live",
    )
    assert archive.upsert_quarter(record)
    archived = archive.list_quarters("meter-export", completed.start_utc, completed.end_utc)[0]
    assert archived["export_kwh"] == pytest.approx(0.750, abs=1e-9)
    assert archived["import_kwh"] == pytest.approx(0.0, abs=1e-9)
    archive.close()
    boundary_write = writes[-1]
    assert boundary_write[0] == start + timedelta(minutes=15)
    assert boundary_write[2] == (start + timedelta(minutes=15)).isoformat()
    assert boundary_write[1] == pytest.approx(0.0, abs=1e-9)


def test_import_export_reversal_accumulates_independently() -> None:
    """Contractual import demand never nets measured export against import."""

    engine = FixedQuarterEngine(stale_after_seconds=60, source_id="mode=signed_power")
    start = datetime(2026, 4, 2, 10, 0, tzinfo=UTC)
    for offset in range(901):
        signed_kw = 4.0 if offset < 300 else -3.0 if offset < 600 else 2.0
        engine.ingest(PowerSample(start + timedelta(seconds=offset), signed_kw))

    completed = engine.completed[-1]
    assert completed.import_kwh == pytest.approx(0.500, abs=1e-9)
    assert completed.export_kwh == pytest.approx(0.250, abs=1e-9)
    assert completed.signed_net_kwh == pytest.approx(0.250, abs=1e-9)
    assert completed.import_demand_kw == pytest.approx(2.000, abs=1e-9)
    assert completed.signed_average_kw == pytest.approx(1.000, abs=1e-9)


def test_export_outage_preserves_evidence_without_fabricating_zero(sensor_module) -> None:
    """A source gap preserves measured export and remains incomplete."""

    runtime = _Runtime()
    engine = FixedQuarterEngine(stale_after_seconds=60, source_id="mode=signed_power")
    runtime.engine = engine
    entity = _entity("quarter_export_kwh_so_far", runtime, sensor_module)
    start = datetime(2026, 4, 2, 10, 0, tzinfo=UTC)
    engine.ingest(PowerSample(start, -3.0))
    engine.advance(start + timedelta(minutes=10))
    runtime.snapshot = engine.snapshot(now=start + timedelta(minutes=10), target_kw=4.2)
    runtime.source_available = False
    runtime.source_status_reason = "source_measurement_stale"
    assert entity.available is True
    assert entity.native_value == pytest.approx(0.050, abs=1e-9)

    engine.advance(start + timedelta(minutes=15))

    completed = engine.completed[-1]
    assert completed.export_kwh == pytest.approx(0.050, abs=1e-9)
    assert completed.import_kwh == pytest.approx(0.0, abs=1e-9)
    assert completed.coverage_seconds == pytest.approx(60.0)
    assert completed.gap_seconds == pytest.approx(840.0)
    assert completed.quality is DataQuality.INCOMPLETE


@pytest.mark.parametrize(
    ("start", "expected_local_starts", "expected_folds"),
    (
        (
            datetime(2026, 3, 29, 0, 45, tzinfo=UTC),
            ("2026-03-29T01:45:00+01:00", "2026-03-29T03:00:00+02:00"),
            (0, 0),
        ),
        (
            datetime(2026, 10, 25, 0, 45, tzinfo=UTC),
            ("2026-10-25T02:45:00+02:00", "2026-10-25T02:00:00+01:00"),
            (0, 1),
        ),
    ),
)
def test_export_quarter_rollover_keeps_dst_utc_identity(
    start: datetime,
    expected_local_starts: tuple[str, str],
    expected_folds: tuple[int, int],
) -> None:
    """Spring and repeated-autumn civil hours retain canonical UTC quarters."""

    engine = FixedQuarterEngine(stale_after_seconds=60, source_id="mode=signed_power")
    for second in range(1801):
        engine.ingest(PowerSample(start + timedelta(seconds=second), -3.0))

    completed = engine.completed[-2:]
    assert [item.start_utc for item in completed] == [
        start,
        start + timedelta(minutes=15),
    ]
    local_starts = [item.start_utc.astimezone(ZoneInfo("Europe/Ljubljana")) for item in completed]
    assert tuple(item.isoformat() for item in local_starts) == expected_local_starts
    assert tuple(item.fold for item in local_starts) == expected_folds
    assert [item.export_kwh for item in completed] == pytest.approx([0.750, 0.750])
    assert [item.import_kwh for item in completed] == pytest.approx([0.0, 0.0])


def test_completed_quarter_entities_publish_distinct_equal_value_quarters_once(
    sensor_module,
) -> None:
    """Equal completed values remain distinct canonical completion events."""

    runtime = _Runtime()
    engine = FixedQuarterEngine(stale_after_seconds=60, source_id="mode=signed_power")
    runtime.engine = engine
    demand = _entity("last_completed_15m_import_demand", runtime, sensor_module)
    signed = _entity("last_completed_15m_signed_average", runtime, sensor_module)
    controller = PublishingController(PublishingSettings.from_mapping({}))
    writes: dict[str, list[PublicationState]] = {"demand": [], "signed": []}
    controller.register(
        demand.entity_description.key,
        sensor_module.sensor.SENSOR_PUBLISHING_POLICIES[demand.entity_description.key],
        demand._publication_state,
        lambda: writes["demand"].append(demand._publication_state()),
    )
    controller.register(
        signed.entity_description.key,
        sensor_module.sensor.SENSOR_PUBLISHING_POLICIES[signed.entity_description.key],
        signed._publication_state,
        lambda: writes["signed"].append(signed._publication_state()),
    )
    start = datetime(2026, 10, 25, 0, 0, tzinfo=UTC)
    for second in range(1802):
        now = start + timedelta(seconds=second)
        engine.ingest(PowerSample(now, 2.0))
        runtime.snapshot = engine.snapshot(now=now, target_kw=4.2)
        controller.process(now)

    for states in writes.values():
        completed = [state for state in states if state.available]
        assert [state.value for state in completed] == pytest.approx([2.0, 2.0])
        assert [state.attributes["quarter_start_utc"] for state in completed] == [
            "2026-10-25T00:00:00+00:00",
            "2026-10-25T00:15:00+00:00",
        ]
        assert [state.attributes["quarter_end_utc"] for state in completed] == [
            "2026-10-25T00:15:00+00:00",
            "2026-10-25T00:30:00+00:00",
        ]


def test_restored_completed_quarter_is_stable_until_new_completion(sensor_module) -> None:
    """Restart restoration emits once and a later equal live quarter has a new identity."""

    runtime = _Runtime()
    runtime.archived_last_completed = SimpleNamespace(
        import_demand_kw=2.0,
        signed_average_kw=2.0,
        quality="measured_aligned",
        provenance="archive:test",
        start_utc=datetime(2026, 10, 25, 0, 0, tzinfo=UTC),
        end_utc=datetime(2026, 10, 25, 0, 15, tzinfo=UTC),
    )
    entity = _entity("last_completed_15m_import_demand", runtime, sensor_module)
    controller = PublishingController(PublishingSettings.from_mapping({}))
    states: list[PublicationState] = []
    controller.register(
        entity.entity_description.key,
        sensor_module.sensor.SENSOR_PUBLISHING_POLICIES[entity.entity_description.key],
        entity._publication_state,
        lambda: states.append(entity._publication_state()),
    )
    start = datetime(2026, 10, 25, 0, 15, tzinfo=UTC)
    controller.process(start)
    controller.process(start + timedelta(seconds=1))
    assert len(states) == 1
    assert states[0].attributes["restored_from_archive"] is True

    engine = FixedQuarterEngine(stale_after_seconds=60, source_id="mode=signed_power")
    runtime.engine = engine
    for second in range(901):
        now = start + timedelta(seconds=second)
        engine.ingest(PowerSample(now, 2.0))
        runtime.snapshot = engine.snapshot(now=now, target_kw=4.2)
        controller.process(now)
    controller.process(start + timedelta(seconds=901))

    assert len(states) == 2
    assert states[-1].value == pytest.approx(2.0)
    assert states[-1].attributes["quarter_start_utc"] == start.isoformat()
    assert states[-1].attributes["restored_from_archive"] is False


def test_resetting_quarter_energy_entities_do_not_claim_lifetime_total_statistics(
    sensor_module,
) -> None:
    """A value resetting every quarter is not a HA lifetime total counter."""

    descriptions = {
        item.key: item
        for item in sensor_module.sensor.SENSORS
        if item.key in {"quarter_import_kwh_so_far", "quarter_export_kwh_so_far"}
    }
    assert set(descriptions) == {
        "quarter_import_kwh_so_far",
        "quarter_export_kwh_so_far",
    }
    assert all(item.state_class is None for item in descriptions.values())


@pytest.mark.parametrize(
    ("local_day", "expected_seconds", "expected_quarters"),
    (
        (date(2026, 3, 29), 82_800, 92),
        (date(2026, 4, 2), 86_400, 96),
        (date(2026, 10, 25), 90_000, 100),
    ),
)
def test_real_two_meter_full_day_storage_projection(
    sensor_module,
    tmp_path: Path,
    local_day: date,
    expected_seconds: int,
    expected_quarters: int,
) -> None:
    """Exercise real entities on 23/24/25-hour local days."""

    database = sqlite3.connect(tmp_path / f"real-publishing-{local_day}.sqlite")
    database.executescript(
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE state_attributes(
            attributes_id INTEGER PRIMARY KEY,
            shared_attrs TEXT NOT NULL UNIQUE
        );
        CREATE TABLE states(
            state_id INTEGER PRIMARY KEY,
            metadata_id INTEGER NOT NULL,
            meter INTEGER NOT NULL,
            entity_key TEXT NOT NULL,
            state TEXT,
            attributes_id INTEGER NOT NULL,
            last_changed_ts REAL NOT NULL,
            last_updated_ts REAL NOT NULL,
            last_reported_ts REAL NOT NULL,
            old_state_id INTEGER,
            context_id_bin BLOB
        );
        CREATE INDEX ix_states_meter_time ON states(meter, last_updated_ts);
        CREATE INDEX ix_states_entity_time ON states(entity_key, last_updated_ts);
        CREATE INDEX ix_states_metadata_time ON states(metadata_id, last_updated_ts);
        """
    )
    ljubljana = ZoneInfo("Europe/Ljubljana")
    current_time = datetime.combine(local_day, time.min, tzinfo=ljubljana).astimezone(UTC)
    end_time = datetime.combine(
        local_day + timedelta(days=1), time.min, tzinfo=ljubljana
    ).astimezone(UTC)
    assert int((end_time - current_time).total_seconds()) == expected_seconds
    counts: dict[tuple[int, str], int] = {}

    def write_state(
        meter: int,
        key: str,
        reader,
        unrecorded: frozenset[str],
        standard_attributes: dict[str, object],
    ) -> None:
        state = reader()
        recorded_attributes = {
            key: value for key, value in state.attributes.items() if key not in unrecorded
        }
        recorded_attributes.update(standard_attributes)
        attributes = json.dumps(
            recorded_attributes,
            sort_keys=True,
            default=str,
        )
        database.execute(
            "INSERT OR IGNORE INTO state_attributes(shared_attrs) VALUES (?)", (attributes,)
        )
        attributes_id = database.execute(
            "SELECT attributes_id FROM state_attributes WHERE shared_attrs = ?", (attributes,)
        ).fetchone()[0]
        database.execute(
            "INSERT INTO states(metadata_id, meter, entity_key, state, attributes_id, "
            "last_changed_ts, last_updated_ts, last_reported_ts, context_id_bin) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                meter * 1000 + abs(hash(key)) % 1000,
                meter,
                key,
                str(state.value),
                attributes_id,
                current_time.timestamp(),
                current_time.timestamp(),
                current_time.timestamp(),
                b"benchmark-context",
            ),
        )
        counts[(meter, key)] = counts.get((meter, key), 0) + 1

    controllers: list[PublishingController] = []
    runtimes: list[_Runtime] = []
    previous_quarters: list[datetime] = []
    for meter in range(2):
        runtime = _Runtime()
        runtime.engine = SimpleNamespace(completed=[])
        _prepare_live_runtime(runtime, current_time, 1.0 + meter * 0.1, False)
        runtimes.append(runtime)
        previous_quarters.append(runtime.snapshot.bounds.start_utc)
        controller = PublishingController(PublishingSettings.from_mapping({}))
        controller.started_utc = current_time
        controllers.append(controller)
        entry = SimpleNamespace(entry_id=f"meter-{meter}", title=f"Meter {meter + 1}")
        for description in sensor_module.sensor.SENSORS:
            entity = sensor_module.sensor.SIGridSensor(runtime, entry, description)
            reader = entity._publication_state
            unrecorded = entity._unrecorded_attributes
            standard_attributes = {
                "friendly_name": f"Meter {meter + 1} {description.key}",
                "unit_of_measurement": description.native_unit_of_measurement,
                "device_class": description.device_class,
                "state_class": description.state_class,
            }
            controller.register(
                description.key,
                sensor_module.sensor.SENSOR_PUBLISHING_POLICIES[description.key],
                reader,
                partial(
                    write_state,
                    meter,
                    description.key,
                    reader,
                    unrecorded,
                    standard_attributes,
                ),
            )
        for description in sensor_module.binary.BINARY_SENSORS:
            entity = sensor_module.binary.SIGridBinarySensor(runtime, entry, description)
            reader = entity._publication_state
            unrecorded = entity._unrecorded_attributes
            standard_attributes = {
                "friendly_name": f"Meter {meter + 1} {description.key}",
            }
            controller.register(
                description.key,
                sensor_module.binary.BINARY_SENSOR_PUBLISHING_POLICIES[description.key],
                reader,
                partial(
                    write_state,
                    meter,
                    description.key,
                    reader,
                    unrecorded,
                    standard_attributes,
                ),
            )

    start = current_time
    quarter_starts: set[datetime] = set()
    for second in range(expected_seconds):
        current_time = start + timedelta(seconds=second)
        hour = second / 3600
        signed_kw = 1.6 + 1.1 * math.sin(hour * math.pi / 6)
        if 9.5 <= hour < 10:
            # Frequent import/export reversals around the solar crossover.
            signed_kw = 0.35 * math.sin(second * math.pi / 20)
        elif 10 <= hour < 15:
            # Sustained solar export exercises current-quarter export-energy
            # publishing rather than a permanently-zero export trace.
            signed_kw = -3.0 + 0.6 * math.sin(hour * math.pi)
        if second % 7200 < 60:
            signed_kw += 4.0
        stale = 18 * 3600 <= second < 18 * 3600 + 60
        for meter, (runtime, controller) in enumerate(zip(runtimes, controllers, strict=True)):
            meter_kw = signed_kw + meter * 0.05
            _prepare_live_runtime(runtime, current_time, meter_kw, stale)
            current_quarter = runtime.snapshot.bounds.start_utc
            if current_quarter != previous_quarters[meter]:
                runtime.engine.completed = [
                    SimpleNamespace(
                        start_utc=previous_quarters[meter],
                        end_utc=current_quarter,
                        import_demand_kw=1.5,
                        signed_average_kw=1.2,
                        quality=DataQuality.MEASURED_ALIGNED,
                        source_id=f"benchmark-meter-{meter}",
                    )
                ]
                previous_quarters[meter] = current_quarter
            if meter == 0:
                quarter_starts.add(runtime.snapshot.bounds.start_utc)
            if second == 12 * 3600:
                runtime.current_block_targets_kw = (3.6, 4.0, 4.2, 4.3, 4.3)
            # Exercise a ten-minute burst with two source reports per second;
            # the remaining day follows the normal one-second timer path.
            if second < 600:
                controller.process(current_time + timedelta(milliseconds=100))
                controller.process(current_time + timedelta(milliseconds=600))
            controller.record_internal_timer_tick()
            controller.process(current_time + timedelta(milliseconds=900))

    database.commit()
    database.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    page_count = int(database.execute("PRAGMA page_count").fetchone()[0])
    page_size = int(database.execute("PRAGMA page_size").fetchone()[0])
    day_sqlite_bytes = page_count * page_size
    event_count = int(database.execute("SELECT COUNT(*) FROM states").fetchone()[0])
    database.close()

    annual_factor = 365 * 86_400 / expected_seconds
    annual_recorder_like = day_sqlite_bytes * annual_factor
    unverified_influx_allowance = event_count * annual_factor * 140
    projected_total = annual_recorder_like + unverified_influx_allowance + 80_000_000
    benchmark = {
        "local_day": local_day.isoformat(),
        "seconds": expected_seconds,
        "quarters": expected_quarters,
        "events": event_count,
        "recorder_like_bytes_per_year": round(annual_recorder_like),
        "influxdb_allowance_bytes_per_year": round(unverified_influx_allowance),
        "archive_allowance_bytes_per_year": 80_000_000,
        "combined_bytes_per_year": round(projected_total),
        "counts": {
            key: sum(count for (_meter, entity_key), count in counts.items() if entity_key == key)
            for key in sorted({entity_key for (_meter, entity_key) in counts})
        },
    }
    print("STORAGE_BENCHMARK " + json.dumps(benchmark, sort_keys=True))
    assert projected_total < STORAGE_BUDGET_BYTES_PER_YEAR, {
        "day_sqlite_bytes": day_sqlite_bytes,
        "event_count": event_count,
        "projected_total": projected_total,
        "top_counts": sorted(counts.items(), key=lambda item: item[1], reverse=True)[:10],
    }
    assert len(quarter_starts) == expected_quarters
    assert all(controller.internal_timer_ticks == expected_seconds for controller in controllers)
    assert all(
        controller.publishing_evaluations == expected_seconds + 1200 for controller in controllers
    )
    assert all(
        controller.diagnostics(end_time)["estimate_status"] == "ready" for controller in controllers
    )
    assert all(
        controller.diagnostics(end_time)["influxdb_physical_storage_verified"] is False
        for controller in controllers
    )
    assert counts
    assert max(counts.values()) < expected_seconds

    # These real-entity counts make the before/after evidence reviewable.  The
    # workload executes 87,600 publishing evaluations per meter; the values
    # below are emitted state rows across both meters after deduplication.
    def count_for(key: str) -> int:
        return sum(count for (_meter, entity_key), count in counts.items() if entity_key == key)

    assert 0 < count_for("sustained_can_add_power") < expected_seconds
    assert 0 < count_for("sustained_must_reduce_power") < expected_seconds
    # Current-quarter accumulation is intentionally fresher than the general
    # 15-minute monitoring cadence. It remains bounded and resets immediately
    # at every canonical quarter boundary.
    assert count_for("current_interval_import_average") == expected_quarters * 2
    assert (
        expected_quarters * 2 < count_for("quarter_import_kwh_so_far") <= (expected_quarters * 12)
    )
    assert (
        expected_quarters * 2 < count_for("quarter_export_kwh_so_far") <= (expected_quarters * 12)
    )
    assert count_for("last_completed_15m_import_demand") == expected_quarters * 2
    assert count_for("last_completed_15m_signed_average") == expected_quarters * 2
