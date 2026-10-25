"""Integration-level publishing tests using real SI Grid Monitor entity attributes."""

from __future__ import annotations

import importlib
import json
import math
import sqlite3
import sys
import types
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.si_grid_monitor.engine import (
    DataQuality,
    EngineSnapshot,
    Projection,
    WindowAverage,
    quarter_bounds,
)
from custom_components.si_grid_monitor.publishing import (
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

    def target_for_tariff(self, tariff):
        if tariff is None or tariff.block is None:
            return None
        return self.current_block_targets_kw[tariff.block - 1]


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


def test_real_two_meter_full_day_storage_projection(sensor_module, tmp_path: Path) -> None:
    """Exercise real entity readers for a DST day; Influx remains unverified."""

    database = sqlite3.connect(tmp_path / "real-publishing-benchmark.sqlite")
    database.executescript(
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE state_attributes(
            attributes_id INTEGER PRIMARY KEY,
            shared_attrs TEXT NOT NULL UNIQUE
        );
        CREATE TABLE states(
            state_id INTEGER PRIMARY KEY,
            meter INTEGER NOT NULL,
            entity_key TEXT NOT NULL,
            state TEXT,
            attributes_id INTEGER NOT NULL,
            updated_ts REAL NOT NULL
        );
        CREATE INDEX ix_states_meter_time ON states(meter, updated_ts);
        CREATE INDEX ix_states_entity_time ON states(entity_key, updated_ts);
        """
    )
    current_time = datetime(2026, 10, 25, tzinfo=UTC)
    counts: dict[tuple[int, str], int] = {}

    def write_state(meter: int, key: str, reader, unrecorded: frozenset[str]) -> None:
        state = reader()
        attributes = json.dumps(
            {key: value for key, value in state.attributes.items() if key not in unrecorded},
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
            "INSERT INTO states(meter, entity_key, state, attributes_id, updated_ts) "
            "VALUES (?, ?, ?, ?, ?)",
            (meter, key, str(state.value), attributes_id, current_time.timestamp()),
        )
        counts[(meter, key)] = counts.get((meter, key), 0) + 1

    controllers: list[PublishingController] = []
    runtimes: list[_Runtime] = []
    for meter in range(2):
        runtime = _Runtime()
        runtime.engine = SimpleNamespace(completed=[])
        _prepare_live_runtime(runtime, current_time, 1.0 + meter * 0.1, False)
        runtimes.append(runtime)
        controller = PublishingController(PublishingSettings.from_mapping({}))
        controller.started_utc = current_time
        controllers.append(controller)
        entry = SimpleNamespace(entry_id=f"meter-{meter}", title=f"Meter {meter + 1}")
        for description in sensor_module.sensor.SENSORS:
            entity = sensor_module.sensor.SIGridSensor(runtime, entry, description)
            reader = entity._publication_state
            unrecorded = entity._unrecorded_attributes
            controller.register(
                description.key,
                sensor_module.sensor.SENSOR_PUBLISHING_POLICIES[description.key],
                reader,
                lambda meter=meter, key=description.key, reader=reader, unrecorded=unrecorded: (
                    write_state(meter, key, reader, unrecorded)
                ),
            )
        for description in sensor_module.binary.BINARY_SENSORS:
            entity = sensor_module.binary.SIGridBinarySensor(runtime, entry, description)
            reader = entity._publication_state
            unrecorded = entity._unrecorded_attributes
            controller.register(
                description.key,
                sensor_module.binary.BINARY_SENSOR_PUBLISHING_POLICIES[description.key],
                reader,
                lambda meter=meter, key=description.key, reader=reader, unrecorded=unrecorded: (
                    write_state(meter, key, reader, unrecorded)
                ),
            )

    start = current_time
    for second in range(24 * 60 * 60):
        current_time = start + timedelta(seconds=second)
        hour = second / 3600
        signed_kw = 1.6 + 1.1 * math.sin(hour * math.pi / 6)
        if 10 <= hour < 15:
            signed_kw = 0.018 * math.sin(second * math.pi / 2)
        if second % 7200 < 60:
            signed_kw += 4.0
        stale = 18 * 3600 <= second < 18 * 3600 + 60
        for meter, (runtime, controller) in enumerate(zip(runtimes, controllers, strict=True)):
            meter_kw = signed_kw + meter * 0.05
            _prepare_live_runtime(runtime, current_time, meter_kw, stale)
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

    annual_recorder_like = day_sqlite_bytes * 365
    unverified_influx_allowance = event_count * 365 * 140
    projected_total = annual_recorder_like + unverified_influx_allowance + 80_000_000
    assert projected_total < STORAGE_BUDGET_BYTES_PER_YEAR, {
        "day_sqlite_bytes": day_sqlite_bytes,
        "event_count": event_count,
        "projected_total": projected_total,
        "top_counts": sorted(counts.items(), key=lambda item: item[1], reverse=True)[:10],
    }
    assert all(controller.internal_timer_ticks == 86_400 for controller in controllers)
    assert all(controller.publishing_evaluations == 87_600 for controller in controllers)
    assert all(
        controller.diagnostics(start + timedelta(days=1))["estimate_status"] == "ready"
        for controller in controllers
    )
    assert all(
        controller.diagnostics(start + timedelta(days=1))["influxdb_physical_storage_verified"]
        is False
        for controller in controllers
    )
    assert counts
    assert max(counts.values()) < 86_400

    # These real-entity counts make the before/after evidence reviewable.  The
    # workload executes 87,600 publishing evaluations per meter; the values
    # below are emitted state rows across both meters after deduplication.
    def count_for(key: str) -> int:
        return sum(count for (_meter, entity_key), count in counts.items() if entity_key == key)

    assert count_for("sustained_can_add_power") == 216
    assert count_for("sustained_must_reduce_power") == 216
    assert count_for("current_interval_import_average") == 192
    assert count_for("quarter_import_kwh_so_far") == 192
