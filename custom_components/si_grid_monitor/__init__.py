"""SI Grid Monitor Home Assistant integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate V0.1 entries without changing saved user preferences."""

    if entry.version < 2:
        hass.config_entries.async_update_entry(entry, version=2, minor_version=0)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SI Grid Monitor from a config entry."""

    from homeassistant.const import Platform

    from .runtime import GridMonitorRuntime

    runtime = GridMonitorRuntime(hass, entry)
    entry.runtime_data = runtime
    await runtime.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(
        entry, (Platform.SENSOR, Platform.BINARY_SENSOR)
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    from homeassistant.const import Platform

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, (Platform.SENSOR, Platform.BINARY_SENSOR)
    )
    if unload_ok:
        runtime: Any = entry.runtime_data
        await runtime.async_stop()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload source, polarity and settings without deleting the entry."""

    await hass.config_entries.async_reload(entry.entry_id)
