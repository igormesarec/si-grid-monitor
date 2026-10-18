"""Sensor entities for SI Grid Monitor V0.1."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_BUDGET_HEADROOM_WARNING, CONF_TARGET_KW, DOMAIN
from .engine import EngineSnapshot
from .runtime import GridMonitorRuntime


@dataclass(frozen=True, kw_only=True)
class SIGridSensorDescription(SensorEntityDescription):
    """Describe an SI Grid Monitor sensor."""

    value_fn: Callable[[EngineSnapshot, GridMonitorRuntime], float | str | None]
    requires_fresh_input: bool = False
    budget_warning: bool = False


SENSORS: tuple[SIGridSensorDescription, ...] = (
    SIGridSensorDescription(
        key="current_power",
        translation_key="current_power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snapshot, runtime: snapshot.current_signed_power_kw,
        requires_fresh_input=True,
    ),
    SIGridSensorDescription(
        key="import_power",
        translation_key="import_power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snapshot, runtime: (
            max(0.0, snapshot.current_signed_power_kw)
            if snapshot.current_signed_power_kw is not None
            else None
        ),
        requires_fresh_input=True,
    ),
    SIGridSensorDescription(
        key="export_power",
        translation_key="export_power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snapshot, runtime: (
            max(0.0, -snapshot.current_signed_power_kw)
            if snapshot.current_signed_power_kw is not None
            else None
        ),
        requires_fresh_input=True,
    ),
    SIGridSensorDescription(
        key="net_power_15m_rolling",
        translation_key="net_power_15m_rolling",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snapshot, runtime: snapshot.rolling_15m_signed.value_kw,
    ),
    SIGridSensorDescription(
        key="import_power_15m_rolling",
        translation_key="import_power_15m_rolling",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snapshot, runtime: snapshot.rolling_15m_import.value_kw,
    ),
    SIGridSensorDescription(
        key="current_interval_import_average",
        translation_key="current_interval_import_average",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snapshot, runtime: snapshot.current_import_average_kw,
    ),
    SIGridSensorDescription(
        key="current_interval_signed_average",
        translation_key="current_interval_signed_average",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snapshot, runtime: snapshot.current_signed_average_kw,
    ),
    SIGridSensorDescription(
        key="last_completed_15m_import_demand",
        translation_key="last_completed_15m_import_demand",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snapshot, runtime: (
            runtime.engine.completed[-1].import_demand_kw
            if runtime.engine.completed
            else None
        ),
    ),
    SIGridSensorDescription(
        key="last_completed_15m_signed_average",
        translation_key="last_completed_15m_signed_average",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snapshot, runtime: (
            runtime.engine.completed[-1].signed_average_kw
            if runtime.engine.completed
            else None
        ),
    ),
    SIGridSensorDescription(
        key="quarter_import_kwh_so_far",
        translation_key="quarter_import_kwh_so_far",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda snapshot, runtime: snapshot.quarter_import_kwh,
    ),
    SIGridSensorDescription(
        key="quarter_export_kwh_so_far",
        translation_key="quarter_export_kwh_so_far",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda snapshot, runtime: snapshot.quarter_export_kwh,
    ),
    SIGridSensorDescription(
        key="target_kw",
        translation_key="target_kw",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda snapshot, runtime: float(runtime.settings[CONF_TARGET_KW]),
    ),
    SIGridSensorDescription(
        key="operational_target_kw",
        translation_key="operational_target_kw",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda snapshot, runtime: snapshot.projection.operational_target_kw,
    ),
    SIGridSensorDescription(
        key="quarter_budget_remaining_kwh",
        translation_key="quarter_budget_remaining_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        value_fn=lambda snapshot, runtime: snapshot.projection.budget_remaining_kwh,
    ),
    SIGridSensorDescription(
        key="allowed_import_until_end_kw",
        translation_key="allowed_import_until_end_kw",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda snapshot, runtime: snapshot.projection.allowed_remaining_import_kw,
    ),
    SIGridSensorDescription(
        key="forecast_instant_kw",
        translation_key="forecast_instant_kw",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda snapshot, runtime: snapshot.projection.forecast_instant_kw,
        requires_fresh_input=True,
    ),
    SIGridSensorDescription(
        key="forecast_smoothed_kw",
        translation_key="forecast_smoothed_kw",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda snapshot, runtime: snapshot.projection.forecast_smoothed_kw,
    ),
    SIGridSensorDescription(
        key="forecast_utilization_pct",
        translation_key="forecast_utilization_pct",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snapshot, runtime: snapshot.projection.forecast_utilization_pct,
    ),
    SIGridSensorDescription(
        key="current_utilization_pct",
        translation_key="current_utilization_pct",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snapshot, runtime: snapshot.projection.current_utilization_pct,
    ),
    SIGridSensorDescription(
        key="can_add_power",
        translation_key="can_add_power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda snapshot, runtime: snapshot.projection.can_add_kw,
        requires_fresh_input=True,
        budget_warning=True,
    ),
    SIGridSensorDescription(
        key="must_reduce_power",
        translation_key="must_reduce_power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda snapshot, runtime: snapshot.projection.must_reduce_kw,
        requires_fresh_input=True,
        budget_warning=True,
    ),
    SIGridSensorDescription(
        key="interval_elapsed_seconds",
        translation_key="interval_elapsed_seconds",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        value_fn=lambda snapshot, runtime: snapshot.elapsed_seconds,
    ),
    SIGridSensorDescription(
        key="interval_remaining_seconds",
        translation_key="interval_remaining_seconds",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        value_fn=lambda snapshot, runtime: snapshot.remaining_seconds,
    ),
    SIGridSensorDescription(
        key="data_quality",
        translation_key="data_quality",
        value_fn=lambda snapshot, runtime: snapshot.quality.value,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SI Grid Monitor sensors."""

    runtime: GridMonitorRuntime = entry.runtime_data
    async_add_entities(
        SIGridSensor(runtime, entry, description) for description in SENSORS
    )


class SIGridSensor(SensorEntity):
    """Representation of one calculation output."""

    _attr_has_entity_name = True

    def __init__(
        self,
        runtime: GridMonitorRuntime,
        entry: ConfigEntry,
        description: SIGridSensorDescription,
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
        return not (
            self.entity_description.requires_fresh_input and snapshot.input_stale
        )

    @property
    def native_value(self) -> float | str | None:
        snapshot = self.runtime.snapshot
        if snapshot is None:
            return None
        return self.entity_description.value_fn(snapshot, self.runtime)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        snapshot = self.runtime.snapshot
        if snapshot is None:
            return {}
        attributes: dict[str, Any] = {
            "quality": snapshot.quality.value,
            "coverage_seconds": round(snapshot.coverage_seconds, 3),
            "gap_seconds": round(snapshot.gap_seconds, 3),
            "input_stale": snapshot.input_stale,
        }
        if self.entity_description.key.endswith("15m_rolling"):
            window = (
                snapshot.rolling_15m_import
                if self.entity_description.key.startswith("import")
                else snapshot.rolling_15m_signed
            )
            attributes.update(
                {
                    "rolling_window_complete": window.complete,
                    "rolling_coverage_seconds": round(window.coverage_seconds, 3),
                    "rolling_gap_seconds": round(window.gap_seconds, 3),
                }
            )
        if self.entity_description.budget_warning:
            attributes["safety_warning"] = ATTR_BUDGET_HEADROOM_WARNING
            if snapshot.projection.unrecoverable:
                attributes["advice_status"] = "cannot_restore_target"
        return attributes

    async def async_added_to_hass(self) -> None:
        """Subscribe to runtime updates."""

        await super().async_added_to_hass()
        self.async_on_remove(self.runtime.add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
