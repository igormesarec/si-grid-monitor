"""Binary sensor entities for SI Grid Monitor V0.2."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .engine import EngineSnapshot
from .publishing import PublicationState, PublishingClass
from .runtime import GridMonitorRuntime


@dataclass(frozen=True, kw_only=True)
class SIGridBinarySensorDescription(BinarySensorEntityDescription):
    """Describe an SI Grid Monitor binary sensor."""

    value_fn: Callable[[EngineSnapshot], bool | None]
    requires_fresh_input: bool = False


BINARY_SENSORS = (
    SIGridBinarySensorDescription(
        key="projected_exceedance",
        translation_key="projected_exceedance",
        value_fn=lambda snapshot: snapshot.projection.projected_exceedance,
        requires_fresh_input=True,
    ),
    SIGridBinarySensorDescription(
        key="unrecoverable_interval",
        translation_key="unrecoverable_interval",
        value_fn=lambda snapshot: snapshot.projection.unrecoverable,
    ),
    SIGridBinarySensorDescription(
        key="input_stale",
        translation_key="input_stale",
        value_fn=lambda snapshot: snapshot.input_stale,
    ),
)

BINARY_SENSOR_PUBLISHING_POLICIES: dict[str, PublishingClass] = {
    "projected_exceedance": PublishingClass.CRITICAL,
    "unrecoverable_interval": PublishingClass.CRITICAL,
    "input_stale": PublishingClass.CRITICAL,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SI Grid Monitor binary sensors."""

    runtime: GridMonitorRuntime = entry.runtime_data
    async_add_entities(
        SIGridBinarySensor(runtime, entry, description) for description in BINARY_SENSORS
    )


class SIGridBinarySensor(BinarySensorEntity):
    """Representation of one boolean calculation output."""

    _attr_has_entity_name = True
    _unrecorded_attributes = frozenset({"source_status_reason"})

    def __init__(
        self,
        runtime: GridMonitorRuntime,
        entry: ConfigEntry,
        description: SIGridBinarySensorDescription,
    ) -> None:
        self.runtime = runtime
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="SI Grid Monitor",
            model="Software meter monitor",
        )

    @property
    def available(self) -> bool:
        snapshot = self.runtime.snapshot
        if snapshot is None:
            return False
        if (
            self.entity_description.key == "projected_exceedance"
            and not self.runtime.instantaneous_power_known
        ):
            return False
        if self.entity_description.key in {
            "projected_exceedance",
            "unrecoverable_interval",
        }:
            if self.entity_description.key == "projected_exceedance" and (
                not self.runtime.source_available or snapshot.input_stale
            ):
                return False
            return self.runtime.current_contractual_available
        return not (
            self.entity_description.requires_fresh_input
            and (not self.runtime.source_available or snapshot.input_stale)
        )

    @property
    def is_on(self) -> bool | None:
        snapshot = self.runtime.snapshot
        if snapshot is None:
            return None
        if self.entity_description.key == "input_stale" and not self.runtime.source_available:
            return True
        return self.entity_description.value_fn(snapshot)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.entity_description.key == "input_stale":
            return {
                "measurement_kind": "instantaneous",
                "source_status_reason": self.runtime.source_status_reason,
            }
        if self.entity_description.key not in {
            "projected_exceedance",
            "unrecoverable_interval",
        }:
            return {}
        tariff = self.runtime.current_tariff
        return {
            "contractual_available": self.runtime.current_contractual_available,
            "contractual_confirmed": self.runtime.current_contractual_confirmed,
            "contractual_status_reason": self.runtime.contractual_status_reason,
            "tariff_rule_status": (
                tariff.rule_status.value if tariff is not None else "unavailable"
            ),
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to runtime updates."""

        await super().async_added_to_hass()
        self.async_on_remove(
            self.runtime.add_publishing_listener(
                self.entity_description.key,
                BINARY_SENSOR_PUBLISHING_POLICIES[self.entity_description.key],
                self._publication_state,
                self._handle_update,
            )
        )

    @callback
    def _publication_state(self) -> PublicationState:
        return PublicationState(
            value=self.is_on,
            available=self.available,
            attributes=self.extra_state_attributes,
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
