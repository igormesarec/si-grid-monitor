"""V0.9 beta lifecycle, upgrade, and packaging acceptance tests."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import types
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

from custom_components.si_grid_monitor import (
    _archive_deletion_authorized,
    _remove_meter_archive,
    async_migrate_entry,
    async_remove_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.si_grid_monitor.archive import ArchiveRecord, QuarterArchive
from custom_components.si_grid_monitor.const import (
    ARCHIVE_REMOVAL_CONFIRMATION_TTL_SECONDS,
    CONF_ALLOW_PROVISIONAL_TARIFF,
    CONF_ARCHIVE_REMOVAL_CONFIRMED_AT,
    CONF_ASSIGNMENT_END_DATE,
    CONF_ASSIGNMENT_PROVENANCE,
    CONF_ASSIGNMENT_RECORDED_ON,
    CONF_ASSIGNMENT_START_DATE,
    CONF_CONTRACTED_POWER_PERIODS,
    CONF_EXPORT_POWER_ENTITY,
    CONF_IMPORT_POWER_ENTITY,
    CONF_POSITIVE_MEANS_IMPORT,
    CONF_POWER_ENTITY,
    CONF_SAFETY_MARGIN_KW,
    CONF_SIMULATION_ENABLED,
    CONF_SIMULATION_TARGET_KW,
    CONF_SMOOTHING_SECONDS,
    CONF_SOURCE_MODE,
    CONF_SUSTAINED_HORIZON_MINUTES,
    CONF_TARGET_B1_KW,
    CONF_TARGET_B2_KW,
    CONF_TARGET_B3_KW,
    CONF_TARGET_B4_KW,
    CONF_TARGET_B5_KW,
    CONF_TARGET_KW,
    DOMAIN,
    SOURCE_CUMULATIVE_ENERGY,
    SOURCE_IMPORT_ONLY,
    SOURCE_SEPARATE_POWER,
    VERSION,
)
from custom_components.si_grid_monitor.contracted_power import (
    ContractedPowerPeriod,
    ContractedPowerSchedule,
    contracted_power_schedule_from_json,
)

ROOT = Path(__file__).parents[1]
REAL_LOOP_UNAVAILABLE = (
    sys.platform == "win32" and os.environ.get("SI_GRID_MONITOR_FORCE_REAL_LOOP_TESTS") != "1"
)


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
        if "homeassistant.exceptions" not in sys.modules:
            exceptions = types.ModuleType("homeassistant.exceptions")

            class ConfigEntryNotReady(Exception):
                pass

            exceptions.ConfigEntryNotReady = ConfigEntryNotReady  # type: ignore[attr-defined]
            sys.modules["homeassistant.exceptions"] = exceptions
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
    exceptions = types.ModuleType("homeassistant.exceptions")

    class ConfigEntryNotReady(Exception):
        pass

    exceptions.ConfigEntryNotReady = ConfigEntryNotReady  # type: ignore[attr-defined]
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
            "homeassistant.exceptions": exceptions,
            "homeassistant.helpers": helpers,
            "homeassistant.helpers.event": event,
            "homeassistant.util": util,
            "homeassistant.util.dt": dt,
        }
    )


def _ensure_config_flow_stubs() -> None:
    """Extend the lifecycle stubs enough to execute the reconfigure step."""

    _ensure_homeassistant_stubs()
    voluptuous = sys.modules.get("voluptuous")
    if voluptuous is None:
        voluptuous = types.ModuleType("voluptuous")

    class Schema:
        def __init__(self, value: Any) -> None:
            self.schema = value

    def marker(key: Any, **_kwargs: Any) -> Any:
        return key

    voluptuous.Schema = Schema  # type: ignore[attr-defined]
    voluptuous.Required = marker  # type: ignore[attr-defined]
    voluptuous.Optional = marker  # type: ignore[attr-defined]
    sys.modules["voluptuous"] = voluptuous
    config_entries = sys.modules["homeassistant.config_entries"]
    const = sys.modules["homeassistant.const"]
    const.STATE_UNAVAILABLE = "unavailable"  # type: ignore[attr-defined]
    const.STATE_UNKNOWN = "unknown"  # type: ignore[attr-defined]

    class ConfigFlow:
        def __init_subclass__(cls, **_kwargs: Any) -> None:
            return super().__init_subclass__()

    class OptionsFlow:
        pass

    config_entries.ConfigFlow = ConfigFlow  # type: ignore[attr-defined]
    config_entries.OptionsFlow = OptionsFlow  # type: ignore[attr-defined]
    data_entry_flow = types.ModuleType("homeassistant.data_entry_flow")
    data_entry_flow.FlowResult = dict  # type: ignore[attr-defined]
    selector = types.ModuleType("homeassistant.helpers.selector")

    class DummySelector:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

    class DummyMode:
        BOX = "box"
        DROPDOWN = "dropdown"

    for name in (
        "BooleanSelector",
        "DateSelector",
        "EntitySelector",
        "EntitySelectorConfig",
        "NumberSelector",
        "NumberSelectorConfig",
        "SelectSelector",
        "SelectSelectorConfig",
        "TextSelector",
    ):
        setattr(selector, name, DummySelector)
    selector.NumberSelectorMode = DummyMode  # type: ignore[attr-defined]
    selector.SelectSelectorMode = DummyMode  # type: ignore[attr-defined]
    sys.modules["homeassistant.data_entry_flow"] = data_entry_flow
    sys.modules["homeassistant.helpers.selector"] = selector
    sys.modules["homeassistant.helpers"].selector = selector  # type: ignore[attr-defined]


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
    def __init__(
        self,
        *,
        fail_forward: bool = False,
        fail_platform: str | None = None,
        forward_order: tuple[str, ...] | None = None,
    ) -> None:
        self.fail_forward = fail_forward
        self.fail_platform = fail_platform
        self.forward_order = forward_order
        self.forwarded = 0
        self.unloaded = 0
        self.loaded_platforms: list[str] = []

    async def async_forward_entry_setups(self, _entry: Any, platforms: Any) -> None:
        self.forwarded += 1
        order = self.forward_order or tuple(platforms)
        for platform in order:
            if self.fail_forward or platform == self.fail_platform:
                raise RuntimeError(f"platform setup failed: {platform}")
            self.loaded_platforms.append(platform)

    async def async_unload_platforms(self, _entry: Any, _platforms: Any) -> bool:
        self.unloaded += 1
        self.loaded_platforms.clear()
        return True


class _Hass:
    def __init__(self, **config_entry_options: Any) -> None:
        self.data: dict[str, Any] = {}
        self.config_entries = _ConfigEntries(**config_entry_options)


class _Runtime:
    instances: ClassVar[list[_Runtime]] = []
    fail_stop: ClassVar[bool] = False

    def __init__(self, _hass: Any, entry: Any) -> None:
        self.entry = entry
        self.started = 0
        self.stopped = 0
        self.callbacks_registered = False
        self.instances.append(self)

    async def async_start(self) -> None:
        self.started += 1
        self.callbacks_registered = True

    async def async_stop(self) -> None:
        self.stopped += 1
        self.callbacks_registered = False
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
    assert entry.runtime_data is None
    assert calls == {"setup": 1, "register": 1, "unregister": 1}


def test_legacy_mode_d_is_disabled_without_mutation_and_other_meter_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V1.0 must stop before runtime construction or Wh/kWh interpretation."""

    _install_lifecycle_doubles(monkeypatch)
    _Runtime.instances.clear()
    hass = _Hass()
    legacy = _Entry()
    legacy.data = {
        CONF_SOURCE_MODE: SOURCE_CUMULATIVE_ENERGY,
        "import_energy_entity": "sensor.legacy_import_kwh",
    }
    original = dict(legacy.data)

    assert _run(async_setup_entry(hass, legacy)) is False
    assert legacy.data == original
    assert legacy.options == {}
    assert legacy.runtime_data is None
    assert _Runtime.instances == []

    supported = _Entry()
    supported.entry_id = "supported-meter"
    supported.data = {CONF_SOURCE_MODE: "signed_power", CONF_POWER_ENTITY: "sensor.grid_w"}
    assert _run(async_setup_entry(hass, supported)) is True
    assert _Runtime.instances[-1].entry is supported


def test_legacy_mode_d_unload_without_runtime_keeps_other_meter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_lifecycle_doubles(monkeypatch)
    hass = _Hass()
    other_runtime = SimpleNamespace()
    hass.data = {DOMAIN: {"runtimes": {"supported-meter": other_runtime}}}
    legacy = _Entry()
    legacy.entry_id = "legacy-mode-d"
    legacy.data = {CONF_SOURCE_MODE: SOURCE_CUMULATIVE_ENERGY}
    legacy.runtime_data = None

    assert _run(async_unload_entry(hass, legacy)) is True
    assert hass.config_entries.unloaded == 1
    assert hass.data[DOMAIN]["runtimes"] == {"supported-meter": other_runtime}
    assert legacy.runtime_data is None
    assert calls["unregister"] == 0


def test_legacy_mode_d_unload_without_any_runtime_is_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_lifecycle_doubles(monkeypatch)
    hass = _Hass()
    hass.data = {DOMAIN: {"runtimes": {}}}
    legacy = _Entry()
    legacy.data = {CONF_SOURCE_MODE: SOURCE_CUMULATIVE_ENERGY}

    assert _run(async_unload_entry(hass, legacy)) is True
    assert legacy.runtime_data is None
    assert calls["unregister"] == 1


def test_legacy_mode_d_failed_setup_unload_and_retry_are_repeatable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HA may unload and retry an intentionally unsupported entry repeatedly."""

    _install_lifecycle_doubles(monkeypatch)
    _Runtime.instances.clear()
    hass = _Hass()
    legacy = _Entry()
    legacy.entry_id = "legacy-retry"
    legacy.data = {
        CONF_SOURCE_MODE: SOURCE_CUMULATIVE_ENERGY,
        "import_energy_entity": "sensor.total_import",
    }
    original = dict(legacy.data)

    assert _run(async_setup_entry(hass, legacy)) is False
    assert _run(async_unload_entry(hass, legacy)) is True
    assert _run(async_setup_entry(hass, legacy)) is False
    assert legacy.runtime_data is None
    assert legacy.data == original
    assert _Runtime.instances == []
    assert hass.data.get(DOMAIN, {}).get("runtimes", {}) == {}


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
    assert hass.config_entries.unloaded == 1
    assert entry.runtime_data is None
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
        runtime = _Runtime.instances[-1]
        assert runtime.stopped == 1
        assert hass.data[DOMAIN]["runtimes"] == {entry.entry_id: runtime}
        assert entry.runtime_data is runtime
        assert calls["unregister"] == 0
    finally:
        _Runtime.fail_stop = False


@pytest.mark.parametrize(
    ("forward_order", "fail_platform", "loaded_first"),
    [
        (("sensor", "binary_sensor"), "binary_sensor", "sensor"),
        (("binary_sensor", "sensor"), "sensor", "binary_sensor"),
    ],
)
def test_partial_platform_forwarding_is_fully_rolled_back(
    monkeypatch: pytest.MonkeyPatch,
    forward_order: tuple[str, ...],
    fail_platform: str,
    loaded_first: str,
) -> None:
    calls = _install_lifecycle_doubles(monkeypatch)
    _Runtime.instances.clear()
    hass = _Hass(fail_platform=fail_platform, forward_order=forward_order)
    entry = _Entry()

    with pytest.raises(RuntimeError, match=fail_platform):
        _run(async_setup_entry(hass, entry))

    assert loaded_first not in hass.config_entries.loaded_platforms
    assert hass.config_entries.unloaded == 1
    assert _Runtime.instances[-1].stopped == 1
    assert not _Runtime.instances[-1].callbacks_registered
    assert hass.data[DOMAIN]["runtimes"] == {}
    assert entry.runtime_data is None
    assert entry.unload_callbacks == []
    assert calls["unregister"] == 1


def test_failed_setup_clears_runtime_data_and_retry_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_lifecycle_doubles(monkeypatch)
    _Runtime.instances.clear()
    hass = _Hass(fail_platform="binary_sensor")
    entry = _Entry()

    with pytest.raises(RuntimeError, match="binary_sensor"):
        _run(async_setup_entry(hass, entry))
    failed_runtime = _Runtime.instances[-1]
    assert entry.runtime_data is None

    hass.config_entries.fail_platform = None
    assert _run(async_setup_entry(hass, entry))
    retried_runtime = _Runtime.instances[-1]
    assert retried_runtime is not failed_runtime
    assert entry.runtime_data is retried_runtime
    assert hass.data[DOMAIN]["runtimes"] == {entry.entry_id: retried_runtime}
    assert hass.config_entries.loaded_platforms == ["sensor", "binary_sensor"]


def test_failed_setup_keeps_runtime_with_unfinished_durable_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rollback never unregisters a runtime whose SQLite cleanup is unfinished."""

    calls = _install_lifecycle_doubles(monkeypatch)

    class LingeringRuntime(_Runtime):
        def __init__(self, hass: Any, entry: Any) -> None:
            super().__init__(hass, entry)
            self.shutdown_complete = False

        async def async_stop(self) -> None:
            self.stopped += 1
            raise RuntimeError("archive shutdown still active")

    sys.modules["custom_components.si_grid_monitor.runtime"].GridMonitorRuntime = (  # type: ignore[attr-defined]
        LingeringRuntime
    )
    hass = _Hass(fail_platform="binary_sensor")
    entry = _Entry()

    with pytest.raises(RuntimeError, match="binary_sensor"):
        _run(async_setup_entry(hass, entry))

    runtime = entry.runtime_data
    assert isinstance(runtime, LingeringRuntime)
    assert hass.data[DOMAIN]["runtimes"] == {entry.entry_id: runtime}
    assert runtime.stopped == 1
    assert calls["unregister"] == 0
    config_entry_not_ready = sys.modules["homeassistant.exceptions"].ConfigEntryNotReady
    with pytest.raises(config_entry_not_ready):
        _run(async_setup_entry(hass, entry))
    assert entry.runtime_data is runtime
    assert hass.data[DOMAIN]["runtimes"] == {entry.entry_id: runtime}


def test_immediate_setup_cancellation_rolls_back_and_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deterministically exercise cancellation without an event-loop stub."""

    calls = _install_lifecycle_doubles(monkeypatch)
    _Runtime.instances.clear()
    hass = _Hass()
    entry = _Entry()

    async def cancel_forward(_entry: Any, _platforms: Any) -> None:
        hass.config_entries.loaded_platforms.append("sensor")
        raise asyncio.CancelledError

    hass.config_entries.async_forward_entry_setups = cancel_forward
    with pytest.raises(asyncio.CancelledError):
        _run(async_setup_entry(hass, entry))

    assert hass.config_entries.loaded_platforms == []
    assert hass.config_entries.unloaded == 1
    assert not _Runtime.instances[-1].callbacks_registered
    assert hass.data[DOMAIN]["runtimes"] == {}
    assert entry.runtime_data is None
    assert calls["unregister"] == 1


@pytest.mark.skipif(
    REAL_LOOP_UNAVAILABLE,
    reason="the managed Windows runtime cannot create asyncio's socketpair",
)
def test_setup_cancellation_preserves_prior_runtime_until_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancellation while joining old shutdown cannot transfer ownership."""

    _install_lifecycle_doubles(monkeypatch)
    hass = _Hass()
    entry = _Entry()

    async def scenario() -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        class PriorRuntime:
            shutdown_complete = False

            async def async_wait_for_shutdown(self, _timeout: float) -> bool:
                entered.set()
                await release.wait()
                self.shutdown_complete = True
                return True

        prior = PriorRuntime()
        entry.runtime_data = prior
        hass.data.setdefault(DOMAIN, {}).setdefault("runtimes", {})[entry.entry_id] = prior
        setup_task = asyncio.create_task(async_setup_entry(hass, entry))
        await entered.wait()
        setup_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await setup_task
        assert entry.runtime_data is prior
        assert hass.data[DOMAIN]["runtimes"] == {entry.entry_id: prior}
        assert _Runtime.instances == []

        release.set()
        assert await prior.async_wait_for_shutdown(1.0)
        assert await async_setup_entry(hass, entry)
        replacement = entry.runtime_data
        assert isinstance(replacement, _Runtime)
        assert hass.data[DOMAIN]["runtimes"] == {entry.entry_id: replacement}

    _Runtime.instances.clear()
    asyncio.run(scenario())


@pytest.mark.skipif(
    REAL_LOOP_UNAVAILABLE,
    reason="the managed Windows runtime cannot create asyncio's socketpair",
)
def test_setup_timeout_defers_then_reopens_archive_on_successful_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bounded wait preserves prior SQLite ownership until shutdown completes."""

    import custom_components.si_grid_monitor as integration

    _install_lifecycle_doubles(monkeypatch)
    monkeypatch.setattr(integration, "PREVIOUS_RUNTIME_SHUTDOWN_WAIT_SECONDS", 0.01)
    config_entry_not_ready = sys.modules["homeassistant.exceptions"].ConfigEntryNotReady
    hass = _Hass()
    entry = _Entry()
    archive_path = tmp_path / ".storage" / "si_grid_monitor_retry.db"
    archive = QuarterArchive(archive_path)
    archive.open()
    start = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
    archive.upsert_quarter(_archive_record(entry.entry_id, start))

    async def scenario() -> None:
        release = asyncio.Event()

        class PriorRuntime:
            def __init__(self) -> None:
                self.shutdown_complete = False
                self.shutdown_task = asyncio.create_task(self._shutdown())

            async def _shutdown(self) -> None:
                await release.wait()
                archive.close()
                self.shutdown_complete = True

            async def async_wait_for_shutdown(self, timeout: float) -> bool:
                if self.shutdown_complete:
                    return True
                try:
                    await asyncio.wait_for(asyncio.shield(self.shutdown_task), timeout)
                except TimeoutError:
                    return False
                return self.shutdown_complete

        prior = PriorRuntime()
        entry.runtime_data = prior
        hass.data.setdefault(DOMAIN, {}).setdefault("runtimes", {})[entry.entry_id] = prior

        with pytest.raises(config_entry_not_ready):
            await async_setup_entry(hass, entry)
        assert not prior.shutdown_task.done()
        assert entry.runtime_data is prior
        assert hass.data[DOMAIN]["runtimes"] == {entry.entry_id: prior}
        assert _Runtime.instances == []

        release.set()
        await prior.shutdown_task
        assert await async_setup_entry(hass, entry)
        replacement = entry.runtime_data
        assert isinstance(replacement, _Runtime)
        assert hass.data[DOMAIN]["runtimes"] == {entry.entry_id: replacement}

        reopened = QuarterArchive(archive_path)
        reopened.open()
        rows = reopened.list_quarters(entry.entry_id, start, start + timedelta(minutes=15))
        assert len(rows) == 1
        assert rows[0]["import_kwh"] == pytest.approx(0.25)
        assert reopened.schema_version == 7
        reopened.close()

    _Runtime.instances.clear()
    asyncio.run(scenario())


@pytest.mark.skipif(
    REAL_LOOP_UNAVAILABLE,
    reason="the managed Windows runtime cannot create asyncio's socketpair",
)
def test_cancelled_integration_setup_rolls_back_and_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise cancellation with a real SelectorEventLoop, not the sync driver."""

    calls = _install_lifecycle_doubles(monkeypatch)
    _Runtime.instances.clear()
    hass = _Hass()
    entry = _Entry()

    async def scenario() -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        async def delayed_forward(_entry: Any, _platforms: Any) -> None:
            hass.config_entries.loaded_platforms.append("sensor")
            entered.set()
            await release.wait()

        hass.config_entries.async_forward_entry_setups = delayed_forward
        setup_task = asyncio.create_task(async_setup_entry(hass, entry))
        await entered.wait()
        setup_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await setup_task

    loop = asyncio.SelectorEventLoop()
    try:
        loop.run_until_complete(scenario())
    finally:
        loop.close()

    assert hass.config_entries.loaded_platforms == []
    assert hass.config_entries.unloaded == 1
    assert _Runtime.instances[-1].stopped == 1
    assert not _Runtime.instances[-1].callbacks_registered
    assert hass.data[DOMAIN]["runtimes"] == {}
    assert entry.runtime_data is None
    assert calls["unregister"] == 1


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
    schedule = ContractedPowerSchedule(
        (
            ContractedPowerPeriod(
                effective_from=date(2026, 1, 1),
                effective_to=date(2026, 12, 31),
                block_targets_kw=(3.5, 3.9, 4.1, 4.2, 4.2),
                provenance="distributor_record",
                recorded_on=date(2025, 10, 17),
            ),
        )
    )
    epoch = archive.register_configuration_epoch(
        namespace="meter-a",
        source_id="sensor.meter-a",
        positive_means_import=True,
        contractual_target_kw=3.5,
        safety_margin_kw=0.2,
        block_targets_kw=(3.5, 3.9, 4.1, 4.2, 4.2),
        allow_provisional_tariff=False,
        contracted_power_schedule=schedule,
        effective_utc=datetime(2026, 1, 1, tzinfo=UTC),
    )
    archive.upsert_quarter(
        replace(
            _archive_record("meter-a", start),
            source_epoch=epoch.epoch,
            contractual_target_kw=3.5,
            safety_margin_kw=0.2,
            operational_target_kw=3.3,
            target_effective_from="2026-01-01",
            target_effective_to="2026-12-31",
            target_provenance="distributor_record",
            target_recorded_on="2025-10-17",
        )
    )
    archive.upsert_quarter(_archive_record("meter-b", start))
    archive.save_checkpoint("meter-a", {"schema": 1, "import_kwh": 0.25})
    archive.close()

    reopened = QuarterArchive(path)
    reopened.open()
    assert reopened.schema_version == 7
    meter_a = reopened.list_quarters("meter-a", start, start + timedelta(hours=1))
    assert len(meter_a) == 1
    assert len(reopened.list_quarters("meter-b", start, start + timedelta(hours=1))) == 1
    assert meter_a[0]["contractual_target_kw"] == pytest.approx(3.5)
    assert meter_a[0]["operational_target_kw"] == pytest.approx(3.3)
    assert meter_a[0]["target_provenance"] == "distributor_record"
    epochs = reopened.list_configuration_epochs("meter-a")
    assert len(epochs) == 1
    assert epochs[0].source_id == "sensor.meter-a"
    assert epochs[0].block_targets_kw == pytest.approx((3.5, 3.9, 4.1, 4.2, 4.2))
    assert epochs[0].contracted_power_periods == schedule.periods
    assert reopened.load_checkpoint("meter-a") == {"schema": 1, "import_kwh": 0.25}
    assert reopened.list_quarters("missing-meter", start, start + timedelta(hours=1)) == []
    reopened.close()


def test_v096_mode_d_schema6_archive_survives_disable_and_source_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real schema-6 counter archive remains immutable across the V1 transition."""

    namespace = "legacy-mode-d"
    path = tmp_path / ".storage" / f"si_grid_monitor_{namespace}.db"
    start = datetime(2026, 10, 22, 18, 0, tzinfo=UTC)
    legacy_source_id = (
        "mode=cumulative_energy|counter_type=import_only|import=sensor.total_import_energy|export="
    )
    legacy_checkpoint = {
        "schema": 3,
        "quarter_start_utc": start.isoformat(),
        "source_id": legacy_source_id,
        "import_kwh": 0.127,
        "export_kwh": None,
        "quality": "counter_derived",
    }

    archive = QuarterArchive(path)
    archive.open()
    epoch = archive.register_configuration_epoch(
        namespace=namespace,
        source_id=legacy_source_id,
        positive_means_import=True,
        contractual_target_kw=3.9,
        safety_margin_kw=0.2,
        block_targets_kw=(3.5, 3.9, 4.1, 4.2, 4.2),
        allow_provisional_tariff=False,
        effective_utc=datetime(2026, 1, 1, tzinfo=UTC),
    )
    archive.upsert_quarter(
        replace(
            _archive_record(namespace, start),
            import_kwh=0.127,
            export_kwh=0.0,
            signed_average_kw=0.508,
            import_demand_kw=0.508,
            coverage_seconds=780,
            gap_seconds=120,
            quality="counter_derived",
            provenance="counter_derived_live:export_unknown",
            source_id=legacy_source_id,
            source_epoch=epoch.epoch,
            configuration_status="known",
            contractual_target_kw=3.9,
            safety_margin_kw=0.2,
            operational_target_kw=3.7,
            utilization_pct=None,
            exceeded=None,
            excess_kw=None,
            contractual_status="unconfirmed",
            contractual_status_reason="counter interval did not prove quarter alignment",
            confirmed_exceeded=None,
        )
    )
    archive.save_checkpoint(namespace, legacy_checkpoint)
    original_row = dict(archive.list_quarters(namespace, start, start + timedelta(minutes=15))[0])
    original_epochs = archive.list_configuration_epochs(namespace)
    archive.close()

    _install_lifecycle_doubles(monkeypatch)
    _Runtime.instances.clear()
    hass = _Hass()
    entry = _Entry()
    entry.entry_id = namespace
    entry.unique_id = "cumulative_energy:sensor.total_import_energy"
    entry.data = {
        CONF_SOURCE_MODE: SOURCE_CUMULATIVE_ENERGY,
        "import_energy_entity": "sensor.total_import_energy",
    }
    assert _run(async_setup_entry(hass, entry)) is False
    assert _run(async_unload_entry(hass, entry)) is True
    assert _Runtime.instances == []

    migrated = QuarterArchive(path)
    migrated.open()
    assert migrated.schema_version == 7
    assert dict(migrated.list_quarters(namespace, start, start + timedelta(minutes=15))[0]) == (
        original_row
    )
    assert migrated.list_configuration_epochs(namespace) == original_epochs
    assert migrated.load_checkpoint(namespace) == legacy_checkpoint

    new_epoch = migrated.register_configuration_epoch(
        namespace=namespace,
        source_id="sensor.solaredge_grid",
        positive_means_import=True,
        contractual_target_kw=3.9,
        safety_margin_kw=0.2,
        block_targets_kw=(3.5, 3.9, 4.1, 4.2, 4.2),
        allow_provisional_tariff=False,
        effective_utc=datetime(2026, 10, 22, 18, 15, tzinfo=UTC),
    )
    assert new_epoch.epoch == epoch.epoch + 1

    def must_not_reclassify(_start: datetime) -> Any:
        raise AssertionError("legacy counter-derived quarter was passed to classification")

    assert migrated.classify_existing_quarters(namespace, must_not_reclassify) == 0
    preserved = dict(migrated.list_quarters(namespace, start, start + timedelta(minutes=15))[0])
    assert preserved == original_row
    assert preserved["quality"] == "counter_derived"
    assert preserved["provenance"] == "counter_derived_live:export_unknown"
    assert preserved["source_epoch"] == epoch.epoch
    assert preserved["tariff_rule_version"] is None
    assert migrated.load_checkpoint(namespace) == legacy_checkpoint
    migrated.close()


def test_beta_version_frontend_and_hacs_package_are_consistent() -> None:
    manifest = json.loads(
        (ROOT / "custom_components/si_grid_monitor/manifest.json").read_text(encoding="utf-8")
    )
    dashboard = (ROOT / "custom_components/si_grid_monitor/frontend/dashboard.js").read_text(
        encoding="utf-8"
    )
    hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
    assert manifest["version"] == VERSION == "1.0.2"
    assert "dashboard-model.mjs?v=1.0.2" in dashboard
    assert "dashboard-i18n.mjs?v=1.0.2" in dashboard
    assert hacs["name"] == "SI Grid Monitor"
    assert not any(ROOT.joinpath(name).exists() for name in ("release.zip", "dist.zip"))


def test_entity_unique_id_formulas_remain_entry_scoped_and_version_independent() -> None:
    """A code/HACS upgrade must not change existing entity registry identities."""

    for module in ("sensor.py", "binary_sensor.py"):
        source = (ROOT / "custom_components/si_grid_monitor" / module).read_text(encoding="utf-8")
        assert 'f"{entry.entry_id}_{description.key}"' in source


def test_only_three_source_modes_are_wired() -> None:
    config_flow = (ROOT / "custom_components/si_grid_monitor/config_flow.py").read_text(
        encoding="utf-8"
    )
    assert "SOURCE_MODES = SUPPORTED_SOURCE_MODES" in config_flow
    assert "SOURCE_CUMULATIVE_ENERGY" not in config_flow
    assert "SOURCE_ALIGNED_QUARTER" not in config_flow
    assert 'errors["base"] = "mode_not_available_v0_4"' not in config_flow


def test_mode_a_keeps_legacy_unique_id_and_duplicate_guard() -> None:
    from custom_components.si_grid_monitor.source_identity import source_unique_id

    config_flow = (ROOT / "custom_components/si_grid_monitor/config_flow.py").read_text(
        encoding="utf-8"
    )
    assert source_unique_id("signed_power", {CONF_POWER_ENTITY: "sensor.grid"}) == (
        "signed:sensor.grid"
    )
    assert "source_unique_id(mode, self._values)" in config_flow
    assert "await self.async_set_unique_id(unique_id)" in config_flow
    assert "self._abort_if_unique_id_configured()" in config_flow


@pytest.mark.parametrize(
    ("mode", "configured", "expected"),
    (
        ("signed_power", {CONF_POWER_ENTITY: "sensor.signed"}, "signed:sensor.signed"),
        (
            SOURCE_SEPARATE_POWER,
            {
                CONF_IMPORT_POWER_ENTITY: "sensor.import_power",
                CONF_EXPORT_POWER_ENTITY: "sensor.export_power",
            },
            "separate_power:sensor.import_power|sensor.export_power",
        ),
        (
            SOURCE_IMPORT_ONLY,
            {CONF_IMPORT_POWER_ENTITY: "sensor.import_only"},
            "import_only:sensor.import_only",
        ),
    ),
)
def test_all_supported_reconfiguration_sources_have_duplicate_safe_identities(
    mode: str, configured: dict[str, Any], expected: str
) -> None:
    from custom_components.si_grid_monitor.source_identity import (
        find_duplicate_source_entry,
        source_unique_id,
    )

    target = source_unique_id(mode, configured)
    assert target == expected
    current = SimpleNamespace(
        entry_id="legacy", unique_id="cumulative_energy:old", data={}, options={}
    )
    existing = SimpleNamespace(
        entry_id="existing",
        unique_id=None,
        data={CONF_SOURCE_MODE: mode, **configured},
        options={},
    )
    assert (
        find_duplicate_source_entry(
            [current, existing], current_entry_id=current.entry_id, target_unique_id=target
        )
        is existing
    )


def test_legacy_mode_d_reconfigure_rebinds_unique_id_and_reloads_same_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ensure_config_flow_stubs()
    sys.modules.pop("custom_components.si_grid_monitor.config_flow", None)
    from custom_components.si_grid_monitor.config_flow import SIGridMonitorConfigFlow

    entry = SimpleNamespace(
        entry_id="legacy-entry-id",
        title="Legacy counter",
        unique_id="cumulative_energy:sensor.total_import",
        data={
            CONF_SOURCE_MODE: SOURCE_CUMULATIVE_ENERGY,
            "import_energy_entity": "sensor.total_import",
            CONF_TARGET_KW: 4.8,
        },
        options={},
    )

    class Entries:
        def __init__(self) -> None:
            self.reload_calls = 0

        @staticmethod
        def async_entries(_domain: str) -> list[Any]:
            return [entry]

        @staticmethod
        def async_update_entry(target: Any, **changes: Any) -> None:
            for key, value in changes.items():
                setattr(target, key, value)

    entries = Entries()
    flow = SIGridMonitorConfigFlow()
    flow.hass = SimpleNamespace(
        config_entries=entries, states=SimpleNamespace(get=lambda _id: None)
    )
    flow._values = {
        "meter_name": "Main grid",
        CONF_SOURCE_MODE: "signed_power",
    }
    flow._get_reconfigure_entry = lambda: entry  # type: ignore[method-assign]
    flow._validate_source_input = lambda _input: {}  # type: ignore[method-assign]

    async def set_unique_id(value: str) -> None:
        flow.flow_unique_id = value

    def update_reload(target: Any, **changes: Any) -> dict[str, Any]:
        entries.reload_calls += 1
        if "data_updates" in changes:
            target.data = {**target.data, **changes["data_updates"]}
        if "options_updates" in changes:
            target.options = {**target.options, **changes["options_updates"]}
        return {"type": "abort", "reason": changes["reason"]}

    flow.async_set_unique_id = set_unique_id  # type: ignore[method-assign]
    flow.async_update_reload_and_abort = update_reload  # type: ignore[method-assign]
    flow.async_abort = lambda **kwargs: {"type": "abort", **kwargs}  # type: ignore[method-assign]

    result = _run(
        flow.async_step_reconfigure_meter(
            {CONF_POWER_ENTITY: "sensor.solaredge_grid", CONF_POSITIVE_MEANS_IMPORT: True}
        )
    )

    assert result == {"type": "abort", "reason": "reconfigure_successful"}
    assert entry.entry_id == "legacy-entry-id"
    assert entry.unique_id == "signed:sensor.solaredge_grid"
    assert entry.data[CONF_SOURCE_MODE] == "signed_power"
    assert entry.data[CONF_POWER_ENTITY] == "sensor.solaredge_grid"
    assert entry.data["import_energy_entity"] == "sensor.total_import"
    assert entries.reload_calls == 1


def test_legacy_mode_d_reconfigure_rejects_duplicate_target_source() -> None:
    _ensure_config_flow_stubs()
    sys.modules.pop("custom_components.si_grid_monitor.config_flow", None)
    from custom_components.si_grid_monitor.config_flow import SIGridMonitorConfigFlow

    legacy = SimpleNamespace(
        entry_id="legacy-entry-id",
        title="Legacy counter",
        unique_id="cumulative_energy:sensor.total_import",
        data={CONF_SOURCE_MODE: SOURCE_CUMULATIVE_ENERGY},
        options={},
    )
    existing = SimpleNamespace(
        entry_id="existing-live-entry",
        title="Existing live source",
        unique_id=None,
        data={CONF_SOURCE_MODE: "signed_power", CONF_POWER_ENTITY: "sensor.grid_power"},
        options={},
    )

    class Entries:
        updated = False

        @staticmethod
        def async_entries(_domain: str) -> list[Any]:
            return [legacy, existing]

        def async_update_entry(self, _target: Any, **_changes: Any) -> None:
            self.updated = True

    entries = Entries()
    flow = SIGridMonitorConfigFlow()
    flow.hass = SimpleNamespace(
        config_entries=entries, states=SimpleNamespace(get=lambda _id: None)
    )
    flow._values = {"meter_name": "Legacy", CONF_SOURCE_MODE: "signed_power"}
    flow._get_reconfigure_entry = lambda: legacy  # type: ignore[method-assign]
    flow._validate_source_input = lambda _input: {}  # type: ignore[method-assign]

    async def set_unique_id(value: str) -> None:
        flow.flow_unique_id = value

    flow.async_set_unique_id = set_unique_id  # type: ignore[method-assign]
    flow.async_abort = lambda **kwargs: {"type": "abort", **kwargs}  # type: ignore[method-assign]

    result = _run(
        flow.async_step_reconfigure_meter(
            {CONF_POWER_ENTITY: "sensor.grid_power", CONF_POSITIVE_MEANS_IMPORT: True}
        )
    )

    assert result == {"type": "abort", "reason": "already_configured"}
    assert not entries.updated
    assert legacy.unique_id == "cumulative_energy:sensor.total_import"
    assert legacy.data == {CONF_SOURCE_MODE: SOURCE_CUMULATIVE_ENERGY}


def test_runtime_modes_expose_stable_sources_and_truthful_capabilities(tmp_path: Path) -> None:
    _ensure_homeassistant_stubs()
    from custom_components.si_grid_monitor.runtime import (
        GridMonitorRuntime,
        UnsupportedSourceModeError,
    )

    class Config:
        def path(self, *parts: str) -> str:
            return str(tmp_path.joinpath(*parts))

    class States:
        @staticmethod
        def get(_entity_id: str) -> None:
            return None

    hass = SimpleNamespace(config=Config(), states=States())
    common = {
        CONF_TARGET_KW: 4.8,
        CONF_CONTRACTED_POWER_PERIODS: "[]",
        CONF_ALLOW_PROVISIONAL_TARIFF: False,
        CONF_SAFETY_MARGIN_KW: 0.0,
        CONF_SMOOTHING_SECONDS: 120,
        CONF_SUSTAINED_HORIZON_MINUTES: 60,
        CONF_SIMULATION_ENABLED: False,
        CONF_SIMULATION_TARGET_KW: 4.8,
    }

    separate = GridMonitorRuntime(
        hass,
        SimpleNamespace(
            entry_id="b",
            data={
                **common,
                CONF_SOURCE_MODE: SOURCE_SEPARATE_POWER,
                CONF_IMPORT_POWER_ENTITY: "sensor.import",
                CONF_EXPORT_POWER_ENTITY: "sensor.export",
            },
            options={},
        ),
    )
    assert separate.source_entities == ("sensor.import", "sensor.export")
    assert separate.export_known and separate.instantaneous_power_known

    import_only = GridMonitorRuntime(
        hass,
        SimpleNamespace(
            entry_id="c",
            data={
                **common,
                CONF_SOURCE_MODE: SOURCE_IMPORT_ONLY,
                CONF_IMPORT_POWER_ENTITY: "sensor.import_only",
            },
            options={},
        ),
    )
    assert import_only.source_entities == ("sensor.import_only",)
    assert not import_only.export_known
    assert import_only.instantaneous_power_known

    with pytest.raises(UnsupportedSourceModeError, match="not supported"):
        GridMonitorRuntime(
            hass,
            SimpleNamespace(
                entry_id="d",
                title="Legacy counter",
                data={
                    **common,
                    CONF_SOURCE_MODE: SOURCE_CUMULATIVE_ENERGY,
                    "import_energy_entity": "sensor.import_total",
                },
                options={},
            ),
        )


def test_options_flow_has_no_active_counter_policy() -> None:
    """V1.0 options expose only live-power source fields."""

    source = (ROOT / "custom_components/si_grid_monitor/config_flow.py").read_text(encoding="utf-8")
    assert "CONF_COUNTER_MIN_OBSERVATION_SECONDS" not in source
    assert "CONF_COUNTER_MAX_PLAUSIBLE_POWER_KW" not in source
    assert "async_step_counter_type" not in source


def _options_flow_entry(schedule: ContractedPowerSchedule) -> SimpleNamespace:
    return SimpleNamespace(
        entry_id="meter-options",
        title="Main grid",
        data={
            CONF_SOURCE_MODE: "signed_power",
            CONF_POWER_ENTITY: "sensor.grid_power",
        },
        options={CONF_CONTRACTED_POWER_PERIODS: schedule.to_json()},
    )


def _assignment_input(start: date, end: date, targets: tuple[float, ...]) -> dict[str, Any]:
    return {
        CONF_ASSIGNMENT_START_DATE: start,
        CONF_ASSIGNMENT_END_DATE: end,
        CONF_ASSIGNMENT_RECORDED_ON: date(2025, 10, 17),
        CONF_ASSIGNMENT_PROVENANCE: "distributor_record",
        **dict(
            zip(
                (
                    CONF_TARGET_B1_KW,
                    CONF_TARGET_B2_KW,
                    CONF_TARGET_B3_KW,
                    CONF_TARGET_B4_KW,
                    CONF_TARGET_B5_KW,
                ),
                targets,
                strict=True,
            )
        ),
    }


def test_native_options_menu_remains_available_with_dashboard_panel() -> None:
    """The integration gear must expose native options, not redirect to the panel."""

    _ensure_config_flow_stubs()
    from custom_components.si_grid_monitor.config_flow import SIGridMonitorOptionsFlow

    schedule = ContractedPowerSchedule(
        (
            ContractedPowerPeriod(
                date(2026, 1, 1),
                date(2026, 12, 31),
                (3.5, 3.9, 4.1, 4.2, 4.2),
                "distributor_record",
            ),
        )
    )
    flow = SIGridMonitorOptionsFlow()
    flow.config_entry = _options_flow_entry(schedule)
    flow.async_show_menu = lambda **kwargs: kwargs

    result = _run(flow.async_step_init())

    assert result["step_id"] == "init"
    assert result["menu_options"] == [
        "settings",
        "assignments",
        "add_assignment",
        "archive_removal",
    ]


def test_options_flow_can_shorten_and_extend_dated_assignments_midyear() -> None:
    """Editing one period and adding a non-overlapping successor stays native and auditable."""

    _ensure_config_flow_stubs()
    from custom_components.si_grid_monitor.config_flow import SIGridMonitorOptionsFlow

    original_targets = (3.5, 3.9, 4.1, 4.2, 4.2)
    later_targets = (3.6, 4.0, 4.2, 4.3, 4.3)
    original = ContractedPowerSchedule(
        (
            ContractedPowerPeriod(
                date(2026, 1, 1),
                date(2026, 12, 31),
                original_targets,
                "distributor_record",
                date(2025, 10, 17),
            ),
        )
    )
    entry = _options_flow_entry(original)

    def run_assignment(
        schedule: ContractedPowerSchedule,
        selected_index: int | None,
        step: str,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        flow = SIGridMonitorOptionsFlow()
        entry.options = {CONF_CONTRACTED_POWER_PERIODS: schedule.to_json()}
        flow.config_entry = entry
        flow._selected_index = selected_index
        flow.async_create_entry = lambda **kwargs: kwargs
        action = (
            flow.async_step_edit_assignment if step == "edit" else flow.async_step_add_assignment
        )
        return _run(action(values))

    edited_result = run_assignment(
        original,
        0,
        "edit",
        _assignment_input(date(2026, 1, 1), date(2026, 6, 30), original_targets),
    )
    shortened = contracted_power_schedule_from_json(
        edited_result["data"][CONF_CONTRACTED_POWER_PERIODS]
    )
    assert shortened.periods[0].effective_to == date(2026, 6, 30)

    added_result = run_assignment(
        shortened,
        None,
        "add",
        _assignment_input(date(2026, 7, 1), date(2026, 12, 31), later_targets),
    )
    final_schedule = contracted_power_schedule_from_json(
        added_result["data"][CONF_CONTRACTED_POWER_PERIODS]
    )
    assert len(final_schedule.periods) == 2
    assert final_schedule.periods[0].block_targets_kw == original_targets
    assert final_schedule.periods[1].effective_from == date(2026, 7, 1)
    assert final_schedule.periods[1].block_targets_kw == later_targets


def test_kw_kwh_entities_publish_full_precision_with_three_digit_display_hint() -> None:
    source = (ROOT / "custom_components/si_grid_monitor/sensor.py").read_text(encoding="utf-8")
    assert "UnitOfPower.KILO_WATT,\n            UnitOfEnergy.KILO_WATT_HOUR," in source
    assert "precision = 3" in source
    native_value = source[
        source.index("    def native_value(") : source.index(
            "    def extra_state_attributes", source.index("    def native_value(")
        )
    ]
    assert "round_for_display" not in native_value
    assert "return value" in native_value


def test_v09_entry_migrates_to_mode_a_without_changing_identity() -> None:
    entry = SimpleNamespace(
        version=4,
        minor_version=0,
        entry_id="existing-mode-a",
        data={CONF_POWER_ENTITY: "sensor.solaredge_m1_ac_power", CONF_TARGET_KW: 4.8},
        options={},
    )

    class Entries:
        @staticmethod
        def async_update_entry(target: Any, **changes: Any) -> None:
            for key, value in changes.items():
                setattr(target, key, value)

    hass = SimpleNamespace(config_entries=Entries())
    assert _run(async_migrate_entry(hass, entry))
    assert entry.version == 5
    assert entry.entry_id == "existing-mode-a"
    assert entry.data[CONF_SOURCE_MODE] == "signed_power"
    assert entry.data[CONF_POWER_ENTITY] == "sensor.solaredge_m1_ac_power"


def test_migrated_mode_a_keeps_the_v09_configuration_epoch_identity(tmp_path: Path) -> None:
    _ensure_homeassistant_stubs()
    from custom_components.si_grid_monitor.runtime import GridMonitorRuntime

    class Config:
        @staticmethod
        def path(*parts: str) -> str:
            return str(tmp_path.joinpath(*parts))

    entry = SimpleNamespace(
        entry_id="existing-mode-a",
        title="Main grid",
        data={
            CONF_SOURCE_MODE: "signed_power",
            CONF_POWER_ENTITY: "sensor.solaredge_m1_ac_power",
            CONF_TARGET_KW: 4.8,
            CONF_CONTRACTED_POWER_PERIODS: "[]",
        },
        options={},
    )
    runtime = GridMonitorRuntime(SimpleNamespace(config=Config()), entry)
    assert runtime.configuration_source_id == "sensor.solaredge_m1_ac_power"
    assert runtime.source_semantics_id == "sensor.solaredge_m1_ac_power|positive_means_import=True"
    archive = runtime.archive
    archive.open()
    original = archive.register_configuration_epoch(
        namespace=entry.entry_id,
        source_id="sensor.solaredge_m1_ac_power",
        positive_means_import=True,
        contractual_target_kw=None,
        safety_margin_kw=0.0,
        effective_utc=datetime(2026, 1, 1, tzinfo=UTC),
    )
    after_upgrade = archive.register_configuration_epoch(
        namespace=entry.entry_id,
        source_id=runtime.configuration_source_id,
        positive_means_import=True,
        contractual_target_kw=None,
        safety_margin_kw=0.0,
        effective_utc=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert after_upgrade.epoch == original.epoch
    assert len(archive.list_configuration_epochs(entry.entry_id)) == 1
    archive.close()


def test_meter_archive_removal_is_entry_scoped_and_backup_is_reopenable(tmp_path: Path) -> None:
    storage = tmp_path / ".storage"
    storage.mkdir()
    selected = storage / "si_grid_monitor_meter-a.db"
    other = storage / "si_grid_monitor_meter-b.db"
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for path, namespace in ((selected, "meter-a"), (other, "meter-b")):
        archive = QuarterArchive(path)
        archive.open()
        archive.upsert_quarter(_archive_record(namespace, start))
        archive.close()
    Path(f"{selected}-wal").write_bytes(b"owned sidecar")
    Path(f"{selected}-shm").write_bytes(b"owned sidecar")

    backup = _remove_meter_archive(selected, storage, "meter-a", True)

    assert backup is not None and backup.exists()
    assert not selected.exists()
    assert not Path(f"{selected}-wal").exists()
    assert not Path(f"{selected}-shm").exists()
    assert other.exists()
    restored = QuarterArchive(backup)
    restored.open()
    assert restored.schema_version == 7
    assert len(restored.list_quarters("meter-a", start, start + timedelta(minutes=15))) == 1
    restored.close()


def test_remove_entry_keeps_database_unless_deletion_was_explicitly_armed(
    tmp_path: Path,
) -> None:
    storage = tmp_path / ".storage"
    storage.mkdir()
    archive_path = storage / "si_grid_monitor_keep-meter.db"
    archive = QuarterArchive(archive_path)
    archive.open()
    archive.close()

    class Config:
        @staticmethod
        def path(*parts: str) -> str:
            return str(tmp_path.joinpath(*parts))

    class Hass:
        config = Config()

        @staticmethod
        async def async_add_executor_job(function: Any, *args: Any) -> Any:
            return function(*args)

    entry = SimpleNamespace(
        entry_id="keep-meter",
        title="Keep meter",
        options={},
        runtime_data=None,
    )
    _run(async_remove_entry(Hass(), entry))
    assert archive_path.exists()


def test_remove_entry_deletes_only_the_armed_meter_after_shutdown(tmp_path: Path) -> None:
    storage = tmp_path / ".storage"
    storage.mkdir()
    selected = storage / "si_grid_monitor_delete-meter.db"
    other = storage / "si_grid_monitor_other-meter.db"
    for path in (selected, other):
        archive = QuarterArchive(path)
        archive.open()
        archive.close()

    class Config:
        @staticmethod
        def path(*parts: str) -> str:
            return str(tmp_path.joinpath(*parts))

    class Hass:
        config = Config()

        @staticmethod
        async def async_add_executor_job(function: Any, *args: Any) -> Any:
            return function(*args)

    entry = SimpleNamespace(
        entry_id="delete-meter",
        title="Delete meter",
        options={
            "delete_archive_on_remove": True,
            "backup_archive_on_remove": False,
            CONF_ARCHIVE_REMOVAL_CONFIRMED_AT: datetime.now(UTC).isoformat(),
        },
        runtime_data=None,
    )
    _run(async_remove_entry(Hass(), entry))
    assert not selected.exists()
    assert other.exists()


def test_archive_deletion_confirmation_expires_and_cannot_remain_armed() -> None:
    confirmed = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
    options = {
        "delete_archive_on_remove": True,
        CONF_ARCHIVE_REMOVAL_CONFIRMED_AT: confirmed.isoformat(),
    }
    assert _archive_deletion_authorized(
        options,
        now_utc=confirmed + timedelta(minutes=9, seconds=59),
        ttl_seconds=ARCHIVE_REMOVAL_CONFIRMATION_TTL_SECONDS,
    )
    assert not _archive_deletion_authorized(
        options,
        now_utc=confirmed + timedelta(minutes=10, seconds=1),
        ttl_seconds=ARCHIVE_REMOVAL_CONFIRMATION_TTL_SECONDS,
    )
    assert not _archive_deletion_authorized(
        {"delete_archive_on_remove": True},
        now_utc=confirmed,
        ttl_seconds=ARCHIVE_REMOVAL_CONFIRMATION_TTL_SECONDS,
    )


def test_remove_entry_keeps_database_after_deletion_confirmation_expires(tmp_path: Path) -> None:
    storage = tmp_path / ".storage"
    storage.mkdir()
    archive_path = storage / "si_grid_monitor_expired-meter.db"
    archive = QuarterArchive(archive_path)
    archive.open()
    archive.close()

    class Config:
        @staticmethod
        def path(*parts: str) -> str:
            return str(tmp_path.joinpath(*parts))

    class Hass:
        config = Config()

        @staticmethod
        async def async_add_executor_job(function: Any, *args: Any) -> Any:
            return function(*args)

    entry = SimpleNamespace(
        entry_id="expired-meter",
        title="Expired meter",
        options={
            "delete_archive_on_remove": True,
            CONF_ARCHIVE_REMOVAL_CONFIRMED_AT: "2020-01-01T00:00:00+00:00",
        },
        runtime_data=None,
    )
    _run(async_remove_entry(Hass(), entry))
    assert archive_path.exists()


def test_setup_translations_cover_three_modes_and_legacy_notice() -> None:
    for language in ("en", "sl"):
        translations = json.loads(
            (ROOT / f"custom_components/si_grid_monitor/translations/{language}.json").read_text(
                encoding="utf-8"
            )
        )
        assert set(translations["selector"]["source_mode"]["options"]) == {
            "signed_power",
            "separate_power",
            "import_only",
        }
        assert "meter_name" in translations["config"]["step"]["user"]["data_description"]
        assert "reconfigure" in translations["config"]["step"]
        assert "legacy_mode_d_unsupported" in translations["issues"]
        assert "archive_removal" in translations["options"]["step"]
        assert "confirm_archive_deletion" in translations["options"]["step"]


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


def test_immediate_runtime_startup_cancellation_closes_archive(
    tmp_path: Path,
) -> None:
    """Deterministically inject cancellation after SQLite has opened."""

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
            if getattr(function, "func", None) is not None:
                raise asyncio.CancelledError
            return function(*args)

    entry = SimpleNamespace(
        entry_id="immediate-startup-cancel",
        title="Immediate startup cancel",
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

    with pytest.raises(asyncio.CancelledError):
        _run(runtime.async_start())
    assert runtime.archive._connection is None
    assert runtime._unsubscribers == []


def test_runtime_startup_cancellation_closes_archive_and_propagates(
    tmp_path: Path,
) -> None:
    """Cancel a real runtime startup at an executor boundary on a real loop."""

    if REAL_LOOP_UNAVAILABLE:
        pytest.skip("the managed Windows runtime cannot create asyncio's socketpair")
    _ensure_homeassistant_stubs()
    from custom_components.si_grid_monitor.runtime import GridMonitorRuntime

    class Config:
        def path(self, *parts: str) -> str:
            return str(tmp_path.joinpath(*parts))

    class States:
        @staticmethod
        def get(_entity_id: str) -> None:
            return None

    entry = SimpleNamespace(
        entry_id="startup-cancelled",
        title="Startup cancelled",
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

    async def scenario() -> GridMonitorRuntime:
        entered = asyncio.Event()
        release = asyncio.Event()

        class Hass:
            config = Config()
            states = States()

            @staticmethod
            async def async_add_executor_job(function: Any, *args: Any) -> Any:
                if getattr(function, "__name__", "") == "classify_existing_quarters":
                    entered.set()
                    await release.wait()
                return function(*args)

        runtime = GridMonitorRuntime(Hass(), entry)  # type: ignore[arg-type]
        startup_task = asyncio.create_task(runtime.async_start())
        await entered.wait()
        startup_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await startup_task
        return runtime

    loop = asyncio.SelectorEventLoop()
    try:
        runtime = loop.run_until_complete(scenario())
    finally:
        loop.close()

    assert runtime.archive._connection is None
    assert runtime._unsubscribers == []


def test_runtime_shutdown_finishes_durable_cleanup_after_listener_failure() -> None:
    """Individual cleanup errors are reported only after all durable work runs."""

    _ensure_homeassistant_stubs()
    from custom_components.si_grid_monitor.runtime import GridMonitorRuntime

    completed: list[str] = []

    def bad_listener() -> None:
        completed.append("bad_listener")
        raise RuntimeError("listener cleanup failed")

    def good_listener() -> None:
        completed.append("good_listener")

    class Queue:
        has_active_tasks = False

        async def cancel_and_wait(self, _task: Any) -> None:
            completed.append("backfill_cancelled")

        async def drain(self) -> tuple[BaseException, ...]:
            completed.append("tasks_drained")
            return (RuntimeError("prior archive task failed"),)

    async def store_pending() -> None:
        completed.append("pending_quarters_stored")

    async def save_checkpoint(_payload: Any) -> None:
        completed.append("checkpoint_saved")

    async def executor(function: Any, *args: Any) -> Any:
        return function(*args)

    runtime = SimpleNamespace(
        _unsubscribers=[bad_listener, good_listener],
        _listeners={lambda: None},
        _archive_tasks=Queue(),
        _backfill_task=None,
        _drain_completed=lambda: completed.append("completed_queued"),
        _async_store_pending_completed=store_pending,
        engine=SimpleNamespace(checkpoint=lambda: {"quarter": "durable"}),
        _async_save_checkpoint=save_checkpoint,
        hass=SimpleNamespace(async_add_executor_job=executor),
        archive=SimpleNamespace(close=lambda: completed.append("archive_closed")),
    )

    with pytest.raises(ExceptionGroup) as raised:
        _run(GridMonitorRuntime._async_stop_impl(runtime))

    messages = [str(error) for error in raised.value.exceptions]
    assert messages == ["listener cleanup failed", "prior archive task failed"]
    assert completed == [
        "bad_listener",
        "good_listener",
        "backfill_cancelled",
        "completed_queued",
        "tasks_drained",
        "pending_quarters_stored",
        "checkpoint_saved",
        "archive_closed",
    ]
    assert runtime._unsubscribers == []
    assert runtime._listeners == set()


@pytest.mark.skipif(
    REAL_LOOP_UNAVAILABLE,
    reason="the managed Windows runtime cannot create asyncio's socketpair",
)
@pytest.mark.parametrize("cancel_phase", ["drain", "checkpoint", "close"])
def test_real_loop_shutdown_cancellation_finishes_archive_and_reopens(
    tmp_path: Path,
    cancel_phase: str,
) -> None:
    """Cancellation at each durable await propagates only after safe cleanup."""

    _ensure_homeassistant_stubs()
    from custom_components.si_grid_monitor.runtime import GridMonitorRuntime

    class Config:
        def path(self, *parts: str) -> str:
            return str(tmp_path.joinpath(*parts))

    entry = SimpleNamespace(
        entry_id=f"shutdown-{cancel_phase}",
        title="Shutdown cancellation",
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

    async def scenario() -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        class Hass:
            config = Config()
            states = SimpleNamespace(get=lambda _entity_id: None)

            @staticmethod
            async def async_add_executor_job(function: Any, *args: Any) -> Any:
                if cancel_phase == "close" and getattr(function, "__name__", "") == "close":
                    entered.set()
                    await release.wait()
                return function(*args)

        class Queue:
            has_active_tasks = False

            async def cancel_and_wait(self, _task: Any) -> None:
                return None

            async def drain(self) -> tuple[BaseException, ...]:
                if cancel_phase == "drain":
                    self.has_active_tasks = True
                    entered.set()
                    await release.wait()
                    self.has_active_tasks = False
                return ()

        runtime = GridMonitorRuntime(Hass(), entry)  # type: ignore[arg-type]
        runtime.archive.open()
        start = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)
        runtime.archive.upsert_quarter(_archive_record(entry.entry_id, start))
        runtime._archive_tasks = Queue()  # type: ignore[assignment]
        runtime._backfill_task = None
        runtime._unsubscribers = []
        runtime._listeners = set()
        runtime._drain_completed = lambda: None  # type: ignore[method-assign]

        async def store_pending() -> None:
            return None

        async def save_checkpoint(_payload: Any) -> None:
            if cancel_phase == "checkpoint":
                entered.set()
                await release.wait()

        runtime._async_store_pending_completed = store_pending  # type: ignore[method-assign]
        runtime._async_save_checkpoint = save_checkpoint  # type: ignore[method-assign]
        runtime.engine = SimpleNamespace(completed=[], checkpoint=lambda: {"safe": True})

        stop_task = asyncio.create_task(runtime.async_stop())
        await entered.wait()
        stop_task.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await stop_task

        assert runtime.shutdown_complete
        assert runtime._shutdown_task is not None
        assert runtime._shutdown_task.done()
        # A retry/restart can safely join the idempotent shutdown and reopen the
        # same schema-6 archive without deleting or duplicating committed rows.
        await runtime.async_stop()
        runtime.archive.open()
        rows = runtime.archive.list_quarters(entry.entry_id, start, start + timedelta(minutes=15))
        assert len(rows) == 1
        assert rows[0]["import_kwh"] == pytest.approx(0.25)
        assert runtime.archive.schema_version == 7
        runtime.archive.close()

    asyncio.run(scenario())


@pytest.mark.skipif(
    REAL_LOOP_UNAVAILABLE,
    reason="the managed Windows runtime cannot create asyncio's socketpair",
)
def test_cancelled_unload_retains_registry_until_shutdown_is_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An interrupted unload cannot advertise removal while work is active."""

    calls = _install_lifecycle_doubles(monkeypatch)
    hass = _Hass()
    entry = _Entry()

    class Runtime:
        def __init__(self) -> None:
            self.shutdown_complete = False
            self.entered: asyncio.Event | None = None
            self.release: asyncio.Event | None = None

        async def async_stop(self) -> None:
            assert self.entered is not None
            assert self.release is not None
            self.entered.set()
            await self.release.wait()
            self.shutdown_complete = True

    runtime = Runtime()
    entry.runtime_data = runtime
    hass.data.setdefault(DOMAIN, {}).setdefault("runtimes", {})[entry.entry_id] = runtime

    async def scenario() -> None:
        runtime.entered = asyncio.Event()
        runtime.release = asyncio.Event()
        unload_task = asyncio.create_task(async_unload_entry(hass, entry))
        await runtime.entered.wait()
        unload_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await unload_task
        assert hass.data[DOMAIN]["runtimes"] == {entry.entry_id: runtime}
        assert entry.runtime_data is runtime
        assert calls["unregister"] == 0

        runtime.release.set()
        assert await async_unload_entry(hass, entry)
        assert hass.data[DOMAIN]["runtimes"] == {}
        assert entry.runtime_data is None
        assert calls["unregister"] == 1

    asyncio.run(scenario())
