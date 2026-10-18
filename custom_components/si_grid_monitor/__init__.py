"""SI Grid Monitor Home Assistant integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SI Grid Monitor from a config entry."""

    from homeassistant.const import Platform

    from .runtime import GridMonitorRuntime

    runtime = GridMonitorRuntime(hass, entry)
    entry.runtime_data = runtime
    await runtime.async_start()
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
        runtime.async_stop()
    return unload_ok
