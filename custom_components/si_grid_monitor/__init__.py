"""SI Grid Monitor Home Assistant integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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
        # V0.4 keeps the schema-5 archive and authoritative serialized schedule
        # unchanged; only the UI used to manage that schedule changes.
        hass.config_entries.async_update_entry(entry, version=4, minor_version=0)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SI Grid Monitor from a config entry."""

    from homeassistant.const import Platform

    from .const import DOMAIN
    from .dashboard import DATA_RUNTIMES, async_register_panel, async_setup_dashboard
    from .runtime import GridMonitorRuntime

    await async_setup_dashboard(hass)

    runtime = GridMonitorRuntime(hass, entry)
    entry.runtime_data = runtime
    await runtime.async_start()
    hass.data[DOMAIN][DATA_RUNTIMES][entry.entry_id] = runtime
    await async_register_panel(hass)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(
        entry, (Platform.SENSOR, Platform.BINARY_SENSOR)
    )
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
        await runtime.async_stop()
        runtimes = hass.data.get(DOMAIN, {}).get(DATA_RUNTIMES, {})
        runtimes.pop(entry.entry_id, None)
        if not runtimes:
            async_unregister_panel(hass)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload source, polarity and settings without deleting the entry."""

    await hass.config_entries.async_reload(entry.entry_id)
