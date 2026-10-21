"""V0.9 beta lifecycle, upgrade, and packaging acceptance tests."""

from __future__ import annotations

import json
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

from custom_components.si_grid_monitor import async_setup_entry, async_unload_entry
from custom_components.si_grid_monitor.archive import ArchiveRecord, QuarterArchive
from custom_components.si_grid_monitor.const import (
    CONF_ALLOW_PROVISIONAL_TARIFF,
    CONF_CONTRACTED_POWER_PERIODS,
    CONF_POSITIVE_MEANS_IMPORT,
    CONF_POWER_ENTITY,
    CONF_SAFETY_MARGIN_KW,
    CONF_SIMULATION_ENABLED,
    CONF_SIMULATION_TARGET_KW,
    CONF_SMOOTHING_SECONDS,
    CONF_SUSTAINED_HORIZON_MINUTES,
    CONF_TARGET_KW,
    DOMAIN,
    VERSION,
)

ROOT = Path(__file__).parents[1]


def _run(coroutine: Any) -> Any:
    """Drive immediate test coroutines without a Windows socketpair event loop."""
    try:
        while True:
            coroutine.send(None)
    except StopIteration as completed:
        return completed.value


def _ensure_homeassistant_stubs() -> None:
    """Install the narrow HA import surface used by lifecycle/runtime tests."""
    if "homeassistant.const" in sys.modules:
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
    event.async_track_state_change_event = lambda *_args, **_kwargs: lambda: None  # type: ignore[attr-defined]
    event.async_track_state_report_event = lambda *_args, **_kwargs: lambda: None  # type: ignore[attr-defined]
    event.async_track_time_interval = lambda *_args, **_kwargs: lambda: None  # type: ignore[attr-defined]
    util = types.ModuleType("homeassistant.util")
    util.__path__ = []  # type: ignore[attr-defined]
    dt = types.ModuleType("homeassistant.util.dt")
    dt.utcnow = lambda: datetime.now(UTC)  # type: ignore[attr-defined]
    util.dt = dt  # type: ignore[attr-defined]
    sys.modules.update(
        {
            "homeassistant": homeassistant,
            "homeassistant.config_entries": config_entries,
            "homeassistant.const": const,
            "homeassistant.core": core,
            "homeassistant.helpers": helpers,
            "homeassistant.helpers.event": event,
            "homeassistant.util": util,
            "homeassistant.util.dt": dt,
        }
    )


class _Entry:
    entry_id = "beta-meter"
    title = "Beta meter"

    def __init__(self) -> None:
        self.data: dict[str, object] = {}
        self.options: dict[str, object] = {}
        self.runtime_data: Any = None
        self.unload_callbacks: list[Any] = []

    def add_update_listener(self, listener: Any) -> Any:
        return listener

    def async_on_unload(self, callback: Any) -> None:
        self.unload_callbacks.append(callback)


class _ConfigEntries:
    def __init__(self, *, fail_forward: bool = False) -> None:
        self.fail_forward = fail_forward
        self.forwarded = 0
        self.unloaded = 0

    async def async_forward_entry_setups(self, _entry: Any, _platforms: Any) -> None:
        self.forwarded += 1
        if self.fail_forward:
            raise RuntimeError("platform setup failed")

    async def async_unload_platforms(self, _entry: Any, _platforms: Any) -> bool:
        self.unloaded += 1
        return True


class _Hass:
    def __init__(self, *, fail_forward: bool = False) -> None:
        self.data: dict[str, Any] = {}
        self.config_entries = _ConfigEntries(fail_forward=fail_forward)


class _Runtime:
    instances: ClassVar[list[_Runtime]] = []
    fail_stop: ClassVar[bool] = False

    def __init__(self, _hass: Any, entry: Any) -> None:
        self.entry = entry
        self.started = 0
        self.stopped = 0
        self.instances.append(self)

    async def async_start(self) -> None:
        self.started += 1

    async def async_stop(self) -> None:
        self.stopped += 1
        if self.fail_stop:
            raise RuntimeError("injected cleanup failure")


def _install_lifecycle_doubles(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    _ensure_homeassistant_stubs()
    calls = {"setup": 0, "register": 0, "unregister": 0}
    dashboard = types.ModuleType("custom_components.si_grid_monitor.dashboard")
    dashboard.DATA_RUNTIMES = "runtimes"  # type: ignore[attr-defined]

    async def setup(hass: Any) -> None:
        calls["setup"] += 1
        hass.data.setdefault(DOMAIN, {}).setdefault("runtimes", {})

    async def register(_hass: Any) -> bool:
        calls["register"] += 1
        return True

    def unregister(_hass: Any) -> None:
        calls["unregister"] += 1

    dashboard.async_setup_dashboard = setup  # type: ignore[attr-defined]
    dashboard.async_register_panel = register  # type: ignore[attr-defined]
    dashboard.async_unregister_panel = unregister  # type: ignore[attr-defined]
    runtime = types.ModuleType("custom_components.si_grid_monitor.runtime")
    runtime.GridMonitorRuntime = _Runtime  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "custom_components.si_grid_monitor.dashboard", dashboard)
    monkeypatch.setitem(sys.modules, "custom_components.si_grid_monitor.runtime", runtime)

    const = sys.modules["homeassistant.const"]
    monkeypatch.setattr(
        const,
        "Platform",
        SimpleNamespace(SENSOR="sensor", BINARY_SENSOR="binary_sensor"),
        raising=False,
    )
    return calls


def test_clean_setup_reload_and_unload_are_symmetric(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _install_lifecycle_doubles(monkeypatch)
    _Runtime.instances.clear()
    _Runtime.fail_stop = False
    hass = _Hass()
    entry = _Entry()

    assert _run(async_setup_entry(hass, entry))
    runtime = _Runtime.instances[-1]
    assert runtime.started == 1
    assert hass.data[DOMAIN]["runtimes"] == {entry.entry_id: runtime}
    assert hass.config_entries.forwarded == 1
    assert len(entry.unload_callbacks) == 1
    assert _run(async_unload_entry(hass, entry))
    assert runtime.stopped == 1
    assert hass.data[DOMAIN]["runtimes"] == {}
    assert hass.config_entries.unloaded == 1
    assert calls == {"setup": 1, "register": 1, "unregister": 1}


def test_failed_platform_setup_rolls_back_runtime_and_panel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_lifecycle_doubles(monkeypatch)
    _Runtime.instances.clear()
    _Runtime.fail_stop = False
    hass = _Hass(fail_forward=True)
    entry = _Entry()

    with pytest.raises(RuntimeError, match="platform setup failed"):
        _run(async_setup_entry(hass, entry))

    runtime = _Runtime.instances[-1]
    assert runtime.started == 1
    assert runtime.stopped == 1
    assert hass.data[DOMAIN]["runtimes"] == {}
    assert entry.unload_callbacks == []
    assert calls == {"setup": 1, "register": 1, "unregister": 1}


def test_cleanup_failure_does_not_mask_platform_setup_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_lifecycle_doubles(monkeypatch)
    _Runtime.instances.clear()
    _Runtime.fail_stop = True
    hass = _Hass(fail_forward=True)
    entry = _Entry()

    try:
        with pytest.raises(RuntimeError, match="platform setup failed"):
            _run(async_setup_entry(hass, entry))
        assert _Runtime.instances[-1].stopped == 1
        assert hass.data[DOMAIN]["runtimes"] == {}
        assert calls["unregister"] == 1
    finally:
        _Runtime.fail_stop = False


def _archive_record(namespace: str, start: datetime) -> ArchiveRecord:
    return ArchiveRecord(
        namespace=namespace,
        start_utc=start,
        end_utc=start + timedelta(minutes=15),
        import_kwh=0.25,
        export_kwh=0.05,
        signed_average_kw=0.8,
        import_demand_kw=1.0,
        coverage_seconds=900,
        gap_seconds=0,
        quality="measured_aligned",
        provenance="live_reconstructed",
        source_id=f"sensor.{namespace}",
        source_epoch=1,
        configuration_status="known",
        contractual_target_kw=4.0,
        safety_margin_kw=0.0,
        operational_target_kw=4.0,
        utilization_pct=25.0,
        exceeded=False,
        excess_kw=0.0,
    )


def test_upgrade_reopen_and_reinstall_preserve_each_meter_namespace(tmp_path: Path) -> None:
    """Code removal/reinstall is modeled by closing and reopening the external DB."""
    path = tmp_path / ".storage" / "si_grid_monitor_shared-test.db"
    archive = QuarterArchive(path)
    archive.open()
    start = datetime(2026, 10, 25, 0, 0, tzinfo=UTC)
    archive.upsert_quarter(_archive_record("meter-a", start))
    archive.upsert_quarter(_archive_record("meter-b", start))
    archive.save_checkpoint("meter-a", {"schema": 1, "import_kwh": 0.25})
    archive.close()

    reopened = QuarterArchive(path)
    reopened.open()
    assert reopened.schema_version == 6
    assert len(reopened.list_quarters("meter-a", start, start + timedelta(hours=1))) == 1
    assert len(reopened.list_quarters("meter-b", start, start + timedelta(hours=1))) == 1
    assert reopened.load_checkpoint("meter-a") == {"schema": 1, "import_kwh": 0.25}
    assert reopened.list_quarters("missing-meter", start, start + timedelta(hours=1)) == []
    reopened.close()


def test_beta_version_frontend_and_hacs_package_are_consistent() -> None:
    manifest = json.loads(
        (ROOT / "custom_components/si_grid_monitor/manifest.json").read_text(encoding="utf-8")
    )
    dashboard = (ROOT / "custom_components/si_grid_monitor/frontend/dashboard.js").read_text(
        encoding="utf-8"
    )
    hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
    assert manifest["version"] == VERSION == "0.9.0"
    assert "dashboard-model.mjs?v=0.9.0" in dashboard
    assert "dashboard-i18n.mjs?v=0.9.0" in dashboard
    assert hacs["name"] == "SI Grid Monitor"
    assert not any(ROOT.joinpath(name).exists() for name in ("release.zip", "dist.zip"))


def test_signed_mode_is_only_implemented_source_mode_and_is_documented_truthfully() -> None:
    config_flow = (ROOT / "custom_components/si_grid_monitor/config_flow.py").read_text(
        encoding="utf-8"
    )
    acceptance = (ROOT / "V0.9_BETA_ACCEPTANCE.md").read_text(encoding="utf-8")
    assert 'errors["base"] = "mode_not_available_v0_4"' in config_flow
    assert "Modes B-E" in acceptance
    assert "Unsupported" in acceptance


def test_runtime_startup_failure_closes_open_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ensure_homeassistant_stubs()
    from custom_components.si_grid_monitor.runtime import GridMonitorRuntime

    class Config:
        def path(self, *parts: str) -> str:
            return str(tmp_path.joinpath(*parts))

    class States:
        @staticmethod
        def get(_entity_id: str) -> None:
            return None

    class Hass:
        config = Config()
        states = States()

        @staticmethod
        async def async_add_executor_job(function: Any, *args: Any) -> Any:
            return function(*args)

    entry = SimpleNamespace(
        entry_id="startup-failure",
        title="Startup failure",
        data={
            CONF_POWER_ENTITY: "sensor.grid",
            CONF_POSITIVE_MEANS_IMPORT: True,
            CONF_TARGET_KW: 4.8,
            CONF_CONTRACTED_POWER_PERIODS: "[]",
            CONF_ALLOW_PROVISIONAL_TARIFF: False,
            CONF_SAFETY_MARGIN_KW: 0.0,
            CONF_SMOOTHING_SECONDS: 120,
            CONF_SUSTAINED_HORIZON_MINUTES: 60,
            CONF_SIMULATION_ENABLED: False,
            CONF_SIMULATION_TARGET_KW: 4.8,
        },
        options={},
    )
    runtime = GridMonitorRuntime(Hass(), entry)  # type: ignore[arg-type]

    def fail_registration(**_kwargs: Any) -> None:
        raise RuntimeError("injected startup failure")

    monkeypatch.setattr(runtime.archive, "register_configuration_epoch", fail_registration)
    with pytest.raises(RuntimeError, match="injected startup failure"):
        _run(runtime.async_start())
    assert runtime.archive._connection is None
    assert runtime._unsubscribers == []
