"""Runtime regression for date-bound contracted-power assignments."""

from __future__ import annotations

import sys
import types
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest


def _install_homeassistant_import_stubs() -> None:
    """Provide only the HA import surface needed by the runtime module."""

    if "homeassistant" in sys.modules:
        return
    homeassistant = types.ModuleType("homeassistant")
    homeassistant.__path__ = []  # type: ignore[attr-defined]
    config_entries = types.ModuleType("homeassistant.config_entries")
    config_entries.ConfigEntry = object  # type: ignore[attr-defined]
    const = types.ModuleType("homeassistant.const")
    const.ATTR_UNIT_OF_MEASUREMENT = "unit_of_measurement"  # type: ignore[attr-defined]
    core = types.ModuleType("homeassistant.core")
    core.Event = object  # type: ignore[attr-defined]
    core.HomeAssistant = object  # type: ignore[attr-defined]
    core.State = object  # type: ignore[attr-defined]
    core.callback = lambda function: function  # type: ignore[attr-defined]
    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []  # type: ignore[attr-defined]
    event = types.ModuleType("homeassistant.helpers.event")
    event.async_track_state_change_event = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]
    event.async_track_state_report_event = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]
    event.async_track_time_interval = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]
    util = types.ModuleType("homeassistant.util")
    util.__path__ = []  # type: ignore[attr-defined]
    dt = types.ModuleType("homeassistant.util.dt")
    dt.utcnow = lambda: datetime.now(UTC)  # type: ignore[attr-defined]
    util.dt = dt  # type: ignore[attr-defined]
    modules = {
        "homeassistant": homeassistant,
        "homeassistant.config_entries": config_entries,
        "homeassistant.const": const,
        "homeassistant.core": core,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.event": event,
        "homeassistant.util": util,
        "homeassistant.util.dt": dt,
    }
    sys.modules.update(modules)


_install_homeassistant_import_stubs()

from custom_components.si_grid_monitor.archive import (  # noqa: E402
    ConfigurationStatus,
    archive_record_from_quarter,
)
from custom_components.si_grid_monitor.const import (  # noqa: E402
    CONF_ALLOW_PROVISIONAL_TARIFF,
    CONF_CONTRACTED_POWER_PERIODS,
    CONF_POSITIVE_MEANS_IMPORT,
    CONF_POWER_ENTITY,
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
)
from custom_components.si_grid_monitor.contracted_power import (  # noqa: E402
    ContractedPowerPeriod,
    ContractedPowerSchedule,
)
from custom_components.si_grid_monitor.engine import (  # noqa: E402
    CompletedQuarter,
    DataQuality,
    FixedQuarterEngine,
    PowerSample,
    quarter_bounds,
)
from custom_components.si_grid_monitor.runtime import GridMonitorRuntime  # noqa: E402
from custom_components.si_grid_monitor.tariffs.calendar import LJUBLJANA  # noqa: E402


class _Config:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, *parts: str) -> str:
        return str(self.root.joinpath(*parts))


class _Hass:
    def __init__(self, root: Path) -> None:
        self.config = _Config(root)


class _Entry:
    entry_id = "runtime-period-test"
    title = "SI Grid Monitor test"

    def __init__(self, data: dict[str, object]) -> None:
        self.data = data
        self.options: dict[str, object] = {}


def _local_utc(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=LJUBLJANA).astimezone(UTC)


def _runtime(tmp_path: Path) -> tuple[GridMonitorRuntime, ContractedPowerSchedule]:
    targets = (3.50, 3.90, 4.10, 4.20, 4.20)
    schedule = ContractedPowerSchedule(
        (
            ContractedPowerPeriod(
                effective_from=date(2026, 1, 1),
                effective_to=date(2026, 12, 31),
                block_targets_kw=targets,
                provenance="distributor assignment based on 15-minute measurements",
                recorded_on=date(2025, 10, 17),
            ),
        )
    )
    data: dict[str, object] = {
        CONF_POWER_ENTITY: "sensor.grid",
        CONF_POSITIVE_MEANS_IMPORT: True,
        CONF_TARGET_KW: 4.8,
        CONF_TARGET_B1_KW: 4.8,
        CONF_TARGET_B2_KW: 4.8,
        CONF_TARGET_B3_KW: 4.8,
        CONF_TARGET_B4_KW: 4.8,
        CONF_TARGET_B5_KW: 4.8,
        CONF_CONTRACTED_POWER_PERIODS: schedule.to_json(),
        CONF_ALLOW_PROVISIONAL_TARIFF: False,
        CONF_SAFETY_MARGIN_KW: 0.0,
        CONF_SMOOTHING_SECONDS: 120,
        CONF_SUSTAINED_HORIZON_MINUTES: 15,
        CONF_SIMULATION_ENABLED: False,
        CONF_SIMULATION_TARGET_KW: 4.8,
    }
    return GridMonitorRuntime(_Hass(tmp_path), _Entry(data)), schedule  # type: ignore[arg-type]


def _feed_fresh_history(runtime: GridMonitorRuntime, now: datetime) -> None:
    runtime.engine = FixedQuarterEngine(stale_after_seconds=60, source_id="sensor.grid")
    cursor = quarter_bounds(now).start_utc
    while cursor <= now:
        runtime.engine.ingest(PowerSample(cursor, 3.0))
        cursor += timedelta(seconds=30)
    runtime._last_checkpoint_utc = now


def test_dashboard_finds_real_fixture_b4_to_b3_lower_target(tmp_path) -> None:
    runtime, _schedule = _runtime(tmp_path)
    now = _local_utc(2026, 10, 18, 20, 0)
    _feed_fresh_history(runtime, now)
    runtime._refresh(now)

    result = runtime.dashboard_transitions()
    assert result["current_block"] == 4
    assert result["current_target_kw"] == 4.20
    assert result["next_lower_target"]["to_block"] == 3
    assert result["next_lower_target"]["from_target_kw"] == 4.20
    assert result["next_lower_target"]["to_target_kw"] == 4.10
    assert result["next_lower_target"]["decrease_kw"] == pytest.approx(0.10)
    assert result["next_lower_target"]["direction"] == "decrease"
    assert result["next_lower_target"]["forecast_status"] in {
        "reduction_needed",
        "no_reduction_projected",
        "unavailable",
    }
    assert result["sustained_horizon_minutes"] == 15


def test_runtime_expires_2026_assignment_without_reusing_it_in_2027(tmp_path) -> None:
    runtime, schedule = _runtime(tmp_path)

    in_2026 = _local_utc(2026, 1, 5, 7, 10)
    _feed_fresh_history(runtime, in_2026)
    runtime._refresh(in_2026)
    assert runtime.current_tariff is not None
    assert runtime.current_tariff.block == 1
    assert runtime.effective_target_kw == 3.50
    assert runtime.current_block_targets_kw == (3.50, 3.90, 4.10, 4.20, 4.20)
    assert runtime.current_contractual_available is True
    assert runtime.current_contractual_confirmed is True
    assert runtime.snapshot is not None
    assert runtime.snapshot.projection.operational_target_kw == 3.50
    assert runtime.sustained_forecast is not None
    dashboard = runtime.dashboard_current()
    assert dashboard["available"] is True
    assert dashboard["tariff"]["target_kw"] == 3.50
    assert dashboard["quarter"]["import_kwh"] == pytest.approx(runtime.snapshot.quarter_import_kwh)
    assert dashboard["trace"]
    assert (
        runtime._operational_target_for_quarter(in_2026, in_2026 + timedelta(minutes=15), 0.0)
        == 3.50
    )

    boundary = _local_utc(2026, 12, 31, 23, 50)
    _feed_fresh_history(runtime, boundary)
    runtime._refresh(boundary)
    assert runtime.effective_target_kw == 4.10
    assert runtime.current_contractual_available is True
    assert runtime.sustained_forecast is None
    assert "tariff target unavailable" in (runtime.sustained_status_reason or "")

    in_2027 = _local_utc(2027, 1, 4, 7, 10)
    _feed_fresh_history(runtime, in_2027)
    runtime._refresh(in_2027)
    assert runtime.current_tariff is not None
    assert runtime.current_tariff.block == 1
    assert runtime.current_block_targets_kw is None
    assert runtime.effective_target_kw is None
    assert runtime.current_contractual_available is False
    assert runtime.current_contractual_confirmed is False
    assert runtime.contractual_status_reason == (
        "no confirmed contracted-power assignment covers 2027-01-04"
    )
    assert runtime.snapshot is not None
    assert runtime.snapshot.current_signed_power_kw == 3.0
    assert runtime.snapshot.projection.operational_target_kw is None
    assert runtime.sustained_forecast is None
    dashboard_2027 = runtime.dashboard_current()
    assert dashboard_2027["available"] is True
    assert dashboard_2027["power"]["signed_kw"] == 3.0
    assert dashboard_2027["tariff"]["target_kw"] is None
    assert dashboard_2027["contractual_available"] is False
    with pytest.raises(ValueError, match="tariff target unavailable"):
        runtime._operational_target_for_quarter(in_2027, in_2027 + timedelta(minutes=15), 0.0)

    runtime.archive.open()
    epoch = runtime.archive.register_configuration_epoch(
        namespace=runtime.namespace,
        source_id=runtime.power_entity,
        positive_means_import=True,
        contractual_target_kw=None,
        safety_margin_kw=0.0,
        block_targets_kw=(None, None, None, None, None),
        allow_provisional_tariff=False,
        contracted_power_schedule=schedule,
        effective_utc=_local_utc(2025, 12, 1, 0, 0),
    )
    assert epoch.contracted_power_periods == schedule.periods
    resolved_2026 = runtime.archive.resolve_configuration(
        runtime.namespace,
        _local_utc(2026, 7, 6, 7, 0),
        _local_utc(2026, 7, 6, 7, 15),
    )
    resolved_2027 = runtime.archive.resolve_configuration(
        runtime.namespace,
        _local_utc(2027, 1, 4, 7, 0),
        _local_utc(2027, 1, 4, 7, 15),
    )
    assert resolved_2026.status == ConfigurationStatus.KNOWN
    assert resolved_2027.status == ConfigurationStatus.TARGET_UNKNOWN

    quarter = CompletedQuarter(
        start_utc=_local_utc(2027, 1, 4, 7, 0),
        end_utc=_local_utc(2027, 1, 4, 7, 15),
        import_kwh=0.75,
        export_kwh=0.0,
        signed_net_kwh=0.75,
        import_demand_kw=3.0,
        signed_average_kw=3.0,
        coverage_seconds=900,
        gap_seconds=0,
        quality=DataQuality.RECONSTRUCTED,
        source_id="sensor.grid",
    )
    record = archive_record_from_quarter(
        namespace=runtime.namespace,
        quarter=quarter,
        configuration=resolved_2027,
        provenance="live_reconstructed",
        tariff=runtime.tariff_calendar.classify(quarter.start_utc),
    )
    assert record.import_kwh == pytest.approx(0.75)
    assert record.contractual_target_kw is None
    assert record.exceeded is None
    assert record.contractual_status == "target_assignment_unavailable"
    runtime.archive.upsert_quarter(record)
    row = runtime.archive.list_quarters(runtime.namespace, quarter.start_utc, quarter.end_utc)[0]
    assert row["import_kwh"] == pytest.approx(0.75)
    assert row["contractual_target_kw"] is None
    assert row["target_provenance"] is None
    runtime.archive.close()
