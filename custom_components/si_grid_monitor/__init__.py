"""SI Grid Monitor Home Assistant integration."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
PREVIOUS_RUNTIME_SHUTDOWN_WAIT_SECONDS = 10.0

try:
    from homeassistant.helpers import config_validation as cv
except ModuleNotFoundError:  # Pure calculation tests intentionally do not install HA.
    CONFIG_SCHEMA = None
else:
    CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_setup(hass: HomeAssistant, _config: dict[str, Any]) -> bool:
    """Register the authenticated dashboard transport and bundled assets."""

    from .dashboard import async_setup_dashboard

    await async_setup_dashboard(hass)
    return True


def migrated_v3_settings(
    data: dict[str, Any], options: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Copy a V0.2 effective target into all five V0.3 block targets."""

    from .const import (
        CONF_ALLOW_PROVISIONAL_TARIFF,
        CONF_CONTRACTED_POWER_PERIODS,
        CONF_TARGET_B1_KW,
        CONF_TARGET_B2_KW,
        CONF_TARGET_B3_KW,
        CONF_TARGET_B4_KW,
        CONF_TARGET_B5_KW,
        CONF_TARGET_KW,
        CONF_TARGET_MODE,
        TARGET_MODE_SHARED,
    )

    migrated_data = dict(data)
    migrated_options = dict(options)
    effective = {**migrated_data, **migrated_options}
    target = float(effective[CONF_TARGET_KW])
    additions = {
        CONF_TARGET_MODE: TARGET_MODE_SHARED,
        CONF_TARGET_B1_KW: target,
        CONF_TARGET_B2_KW: target,
        CONF_TARGET_B3_KW: target,
        CONF_TARGET_B4_KW: target,
        CONF_TARGET_B5_KW: target,
        CONF_ALLOW_PROVISIONAL_TARIFF: False,
        # Historical settings have no auditable validity dates. Preserve their
        # values, but require an explicit period before contractual advice.
        CONF_CONTRACTED_POWER_PERIODS: "[]",
    }
    destination = migrated_options if CONF_TARGET_KW in migrated_options else migrated_data
    for key, value in additions.items():
        destination.setdefault(key, value)
    return migrated_data, migrated_options


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old entries while preserving effective V0.2 preferences."""

    if entry.version < 2:
        hass.config_entries.async_update_entry(entry, version=2, minor_version=0)
    if entry.version < 3:
        data, options = migrated_v3_settings(dict(entry.data), dict(entry.options))
        hass.config_entries.async_update_entry(
            entry, data=data, options=options, version=3, minor_version=1
        )
    if entry.version == 3 and entry.minor_version < 1:
        from .const import CONF_CONTRACTED_POWER_PERIODS

        options = dict(entry.options)
        if (
            CONF_CONTRACTED_POWER_PERIODS not in entry.data
            and CONF_CONTRACTED_POWER_PERIODS not in options
        ):
            options[CONF_CONTRACTED_POWER_PERIODS] = "[]"
        hass.config_entries.async_update_entry(entry, options=options, version=3, minor_version=1)
    if entry.version < 4:
        # Entry identity and the authoritative serialized schedule stay unchanged.
        # Archive migration is independently additive in QuarterArchive.
        hass.config_entries.async_update_entry(entry, version=4, minor_version=0)
    if entry.version < 5:
        from .const import CONF_SOURCE_MODE, SOURCE_SIGNED_POWER

        data = dict(entry.data)
        options = dict(entry.options)
        destination = options if "power_entity" in options else data
        destination.setdefault(CONF_SOURCE_MODE, SOURCE_SIGNED_POWER)
        hass.config_entries.async_update_entry(
            entry, data=data, options=options, version=5, minor_version=0
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SI Grid Monitor from a config entry."""

    from homeassistant.const import Platform
    from homeassistant.exceptions import ConfigEntryNotReady

    from .const import DOMAIN
    from .dashboard import (
        DATA_RUNTIMES,
        async_register_panel,
        async_setup_dashboard,
        async_unregister_panel,
    )
    from .runtime import GridMonitorRuntime

    await async_setup_dashboard(hass)

    runtimes = hass.data[DOMAIN][DATA_RUNTIMES]
    existing_runtime = runtimes.get(entry.entry_id)
    entry_runtime = getattr(entry, "runtime_data", None)
    if (
        existing_runtime is not None
        and entry_runtime is not None
        and existing_runtime is not entry_runtime
    ):
        _LOGGER.error(
            "Deferring SI Grid Monitor setup for %s because runtime ownership conflicts",
            entry.entry_id,
        )
        raise ConfigEntryNotReady("Existing SI Grid Monitor runtime ownership is inconsistent")
    if existing_runtime is None and entry_runtime is not None:
        existing_runtime = entry_runtime
    if existing_runtime is not None:
        shutdown_complete = bool(getattr(existing_runtime, "shutdown_complete", False))
        waiter = getattr(existing_runtime, "async_wait_for_shutdown", None)
        if not shutdown_complete and callable(waiter):
            _LOGGER.info(
                "Waiting up to %.1f seconds for prior SI Grid Monitor runtime %s shutdown",
                PREVIOUS_RUNTIME_SHUTDOWN_WAIT_SECONDS,
                entry.entry_id,
            )
            shutdown_complete = await waiter(PREVIOUS_RUNTIME_SHUTDOWN_WAIT_SECONDS)
        if not shutdown_complete:
            _LOGGER.warning(
                "Deferring SI Grid Monitor setup for %s because prior durable shutdown "
                "is still active",
                entry.entry_id,
            )
            raise ConfigEntryNotReady(
                "Previous SI Grid Monitor runtime is still closing its archive"
            )
        if runtimes.get(entry.entry_id) is existing_runtime:
            runtimes.pop(entry.entry_id, None)
        if getattr(entry, "runtime_data", None) is existing_runtime:
            entry.runtime_data = None

    runtime = GridMonitorRuntime(hass, entry)
    entry.runtime_data = runtime
    started = False
    panel_created = False
    forwarding_started = False

    async def cleanup_failed_setup() -> None:
        """Undo every setup phase without replacing the original failure."""

        if forwarding_started:
            try:
                await hass.config_entries.async_unload_platforms(
                    entry, (Platform.SENSOR, Platform.BINARY_SENSOR)
                )
            except Exception:
                _LOGGER.exception("Failed to unload platforms after setup failure")
        cleanup_complete = not started
        if started:
            try:
                await runtime.async_stop()
                cleanup_complete = True
            except Exception:
                _LOGGER.exception("Failed to stop SI Grid Monitor after setup failure")
                cleanup_complete = bool(getattr(runtime, "shutdown_complete", False))
        if cleanup_complete and runtimes.get(entry.entry_id) is runtime:
            runtimes.pop(entry.entry_id, None)
        if cleanup_complete and panel_created and not runtimes:
            try:
                async_unregister_panel(hass)
            except Exception:
                _LOGGER.exception("Failed to remove SI Grid Monitor panel after setup failure")
        if cleanup_complete and getattr(entry, "runtime_data", None) is runtime:
            entry.runtime_data = None
        if not cleanup_complete:
            _LOGGER.warning(
                "Keeping failed SI Grid Monitor runtime %s registered until durable "
                "shutdown completes",
                entry.entry_id,
            )

    try:
        await runtime.async_start()
        started = True
        runtimes[entry.entry_id] = runtime
        panel_created = await async_register_panel(hass)
        forwarding_started = True
        await hass.config_entries.async_forward_entry_setups(
            entry, (Platform.SENSOR, Platform.BINARY_SENSOR)
        )
    except asyncio.CancelledError:
        # Once the cancellation has been caught, cleanup awaits can complete
        # before the original cancellation is propagated to Home Assistant.
        await cleanup_failed_setup()
        raise
    except Exception:
        await cleanup_failed_setup()
        raise
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    from homeassistant.const import Platform

    from .const import DOMAIN
    from .dashboard import DATA_RUNTIMES, async_unregister_panel

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, (Platform.SENSOR, Platform.BINARY_SENSOR)
    )
    if unload_ok:
        runtime: Any = entry.runtime_data
        stopped = False
        try:
            await runtime.async_stop()
            stopped = True
        finally:
            cleanup_complete = stopped or bool(getattr(runtime, "shutdown_complete", False))
            if cleanup_complete:
                runtimes = hass.data.get(DOMAIN, {}).get(DATA_RUNTIMES, {})
                if runtimes.get(entry.entry_id) is runtime:
                    runtimes.pop(entry.entry_id, None)
                if getattr(entry, "runtime_data", None) is runtime:
                    entry.runtime_data = None
                if not runtimes:
                    async_unregister_panel(hass)
            else:
                _LOGGER.warning(
                    "Keeping SI Grid Monitor runtime registered because durable shutdown "
                    "is still active"
                )
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload source, polarity and settings without deleting the entry."""

    await hass.config_entries.async_reload(entry.entry_id)
