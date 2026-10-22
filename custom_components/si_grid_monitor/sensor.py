"""Sensor entities for SI Grid Monitor."""

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

from .const import (
    ATTR_BUDGET_HEADROOM_WARNING,
    DOMAIN,
)
from .engine import EngineSnapshot, round_for_display
from .runtime import GridMonitorRuntime


@dataclass(frozen=True, kw_only=True)
class SIGridSensorDescription(SensorEntityDescription):
    """Describe an SI Grid Monitor sensor."""

    value_fn: Callable[[EngineSnapshot | None, GridMonitorRuntime], float | int | str | None]
    requires_fresh_input: bool = False
    budget_warning: bool = False
    display_precision: int | None = None


SENSORS: tuple[SIGridSensorDescription, ...] = (
    SIGridSensorDescription(
        key="source_mode",
        translation_key="source_mode",
        value_fn=lambda snapshot, runtime: runtime.source_mode,
    ),
    SIGridSensorDescription(
        key="derived_import_power",
        translation_key="derived_import_power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snapshot, runtime: runtime.derived_import_power_kw,
    ),
    SIGridSensorDescription(
        key="derived_export_power",
        translation_key="derived_export_power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snapshot, runtime: runtime.derived_export_power_kw,
    ),
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
        key="smoothed_signed_power",
        translation_key="smoothed_signed_power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snapshot, runtime: (
            snapshot.smoothed_signed.value_kw if snapshot.smoothed_signed.complete else None
        ),
    ),
    SIGridSensorDescription(
        key="smoothed_import_power",
        translation_key="smoothed_import_power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snapshot, runtime: (
            snapshot.smoothed_import.value_kw if snapshot.smoothed_import.complete else None
        ),
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
        value_fn=lambda snapshot, runtime: runtime.last_completed_import_demand_kw,
    ),
    SIGridSensorDescription(
        key="last_completed_15m_signed_average",
        translation_key="last_completed_15m_signed_average",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snapshot, runtime: runtime.last_completed_signed_average_kw,
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
        value_fn=lambda snapshot, runtime: runtime.effective_target_kw,
    ),
    SIGridSensorDescription(
        key="current_tariff_block",
        translation_key="current_tariff_block",
        value_fn=lambda snapshot, runtime: (
            f"B{runtime.current_tariff.block}"
            if runtime.current_tariff is not None and runtime.current_tariff.block is not None
            else None
        ),
    ),
    SIGridSensorDescription(
        key="current_tariff_season",
        translation_key="current_tariff_season",
        value_fn=lambda snapshot, runtime: (
            runtime.current_tariff.season.value if runtime.current_tariff is not None else None
        ),
    ),
    SIGridSensorDescription(
        key="current_tariff_day_type",
        translation_key="current_tariff_day_type",
        value_fn=lambda snapshot, runtime: (
            runtime.current_tariff.day_type.value if runtime.current_tariff is not None else None
        ),
    ),
    SIGridSensorDescription(
        key="current_block_contracted_power",
        translation_key="current_block_contracted_power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda snapshot, runtime: (
            runtime.target_for_tariff(runtime.current_tariff)
            if runtime.current_tariff is not None
            else None
        ),
    ),
    SIGridSensorDescription(
        key="next_tariff_block",
        translation_key="next_tariff_block",
        value_fn=lambda snapshot, runtime: (
            f"B{runtime.next_tariff.block}"
            if runtime.next_tariff is not None and runtime.next_tariff.block is not None
            else None
        ),
    ),
    SIGridSensorDescription(
        key="time_to_next_tariff_block",
        translation_key="time_to_next_tariff_block",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        value_fn=lambda snapshot, runtime: runtime.time_to_next_tariff_seconds,
    ),
    SIGridSensorDescription(
        key="next_block_contracted_power",
        translation_key="next_block_contracted_power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda snapshot, runtime: (
            runtime.target_for_tariff(runtime.next_tariff)
            if runtime.next_tariff is not None
            else None
        ),
    ),
    SIGridSensorDescription(
        key="tariff_calendar_year",
        translation_key="tariff_calendar_year",
        value_fn=lambda snapshot, runtime: (
            runtime.current_tariff.calendar_year if runtime.current_tariff is not None else None
        ),
    ),
    SIGridSensorDescription(
        key="tariff_rule_status",
        translation_key="tariff_rule_status",
        value_fn=lambda snapshot, runtime: (
            runtime.current_tariff.rule_status.value
            if runtime.current_tariff is not None
            else "unavailable"
        ),
    ),
    SIGridSensorDescription(
        key="contracted_power_b1",
        translation_key="contracted_power_b1",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda snapshot, runtime: (
            runtime.current_block_targets_kw[0]
            if runtime.current_block_targets_kw is not None
            else None
        ),
    ),
    SIGridSensorDescription(
        key="contracted_power_b2",
        translation_key="contracted_power_b2",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda snapshot, runtime: (
            runtime.current_block_targets_kw[1]
            if runtime.current_block_targets_kw is not None
            else None
        ),
    ),
    SIGridSensorDescription(
        key="contracted_power_b3",
        translation_key="contracted_power_b3",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda snapshot, runtime: (
            runtime.current_block_targets_kw[2]
            if runtime.current_block_targets_kw is not None
            else None
        ),
    ),
    SIGridSensorDescription(
        key="contracted_power_b4",
        translation_key="contracted_power_b4",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda snapshot, runtime: (
            runtime.current_block_targets_kw[3]
            if runtime.current_block_targets_kw is not None
            else None
        ),
    ),
    SIGridSensorDescription(
        key="contracted_power_b5",
        translation_key="contracted_power_b5",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda snapshot, runtime: (
            runtime.current_block_targets_kw[4]
            if runtime.current_block_targets_kw is not None
            else None
        ),
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
        display_precision=2,
    ),
    SIGridSensorDescription(
        key="forecast_instant_utilization_pct",
        translation_key="forecast_instant_utilization_pct",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snapshot, runtime: snapshot.projection.forecast_instant_utilization_pct,
        requires_fresh_input=True,
        display_precision=2,
    ),
    SIGridSensorDescription(
        key="current_utilization_pct",
        translation_key="current_utilization_pct",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snapshot, runtime: snapshot.projection.current_utilization_pct,
        display_precision=2,
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
        key="sustained_can_add_power",
        translation_key="sustained_can_add_power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda snapshot, runtime: (
            runtime.sustained_forecast.can_add_kw
            if runtime.sustained_forecast is not None
            else None
        ),
        budget_warning=True,
        display_precision=2,
    ),
    SIGridSensorDescription(
        key="sustained_must_reduce_power",
        translation_key="sustained_must_reduce_power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda snapshot, runtime: (
            runtime.sustained_forecast.must_reduce_kw
            if runtime.sustained_forecast is not None
            else None
        ),
        budget_warning=True,
        display_precision=2,
    ),
    SIGridSensorDescription(
        key="sustained_forecast_quality",
        translation_key="sustained_forecast_quality",
        value_fn=lambda snapshot, runtime: (
            runtime.sustained_forecast.quality.value
            if runtime.sustained_forecast is not None
            else "unavailable"
        ),
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

TARIFF_ONLY_SENSOR_KEYS = {
    "current_tariff_block",
    "current_tariff_season",
    "current_tariff_day_type",
    "current_block_contracted_power",
    "next_tariff_block",
    "time_to_next_tariff_block",
    "next_block_contracted_power",
    "tariff_calendar_year",
    "tariff_rule_status",
    "contracted_power_b1",
    "contracted_power_b2",
    "contracted_power_b3",
    "contracted_power_b4",
    "contracted_power_b5",
}

CONTRACTUAL_SENSOR_KEYS = {
    "target_kw",
    "operational_target_kw",
    "quarter_budget_remaining_kwh",
    "allowed_import_until_end_kw",
    "forecast_instant_kw",
    "forecast_smoothed_kw",
    "forecast_utilization_pct",
    "forecast_instant_utilization_pct",
    "current_utilization_pct",
    "can_add_power",
    "must_reduce_power",
}

LIVE_FORECAST_SENSOR_KEYS = {
    "forecast_instant_kw",
    "forecast_smoothed_kw",
    "forecast_utilization_pct",
    "forecast_instant_utilization_pct",
    "can_add_power",
    "must_reduce_power",
}

ARCHIVED_SENSOR_KEYS = {
    "last_completed_15m_import_demand",
    "last_completed_15m_signed_average",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SI Grid Monitor sensors."""

    runtime: GridMonitorRuntime = entry.runtime_data
    derived_keys = {"derived_import_power", "derived_export_power"}
    descriptions = (
        description
        for description in SENSORS
        if description.key not in derived_keys or runtime.source_mode == "cumulative_energy"
    )
    async_add_entities(SIGridSensor(runtime, entry, description) for description in descriptions)


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
        precision = description.display_precision
        if precision is None and description.native_unit_of_measurement == UnitOfPower.KILO_WATT:
            precision = 2
        if precision is not None:
            self._attr_suggested_display_precision = precision

    @property
    def available(self) -> bool:
        snapshot = self.runtime.snapshot
        if self.entity_description.key == "source_mode":
            return True
        if self.entity_description.key == "derived_import_power":
            return (
                self.runtime.source_available and self.runtime.derived_import_power_kw is not None
            )
        if self.entity_description.key == "derived_export_power":
            return (
                self.runtime.source_available and self.runtime.derived_export_power_kw is not None
            )
        if (
            self.entity_description.key in {"export_power", "quarter_export_kwh_so_far"}
            and not self.runtime.export_known
        ):
            return False
        if self.entity_description.key in TARIFF_ONLY_SENSOR_KEYS:
            return self.entity_description.value_fn(snapshot, self.runtime) is not None
        if self.entity_description.key in ARCHIVED_SENSOR_KEYS:
            return self.entity_description.value_fn(snapshot, self.runtime) is not None
        if snapshot is None:
            return False
        if (
            self.entity_description.key in LIVE_FORECAST_SENSOR_KEYS
            and not self.runtime.instantaneous_power_known
        ):
            return False
        if self.entity_description.key in CONTRACTUAL_SENSOR_KEYS:
            return self.runtime.current_contractual_available
        if self.entity_description.key in {
            "sustained_can_add_power",
            "sustained_must_reduce_power",
        }:
            forecast = self.runtime.sustained_forecast
            if forecast is None:
                return False
            return (
                forecast.can_add_kw is not None
                if self.entity_description.key == "sustained_can_add_power"
                else forecast.must_reduce_kw is not None
            )
        return not (self.entity_description.requires_fresh_input and snapshot.input_stale)

    @property
    def native_value(self) -> float | int | str | None:
        snapshot = self.runtime.snapshot
        if snapshot is None and self.entity_description.key not in (
            TARIFF_ONLY_SENSOR_KEYS
            | ARCHIVED_SENSOR_KEYS
            | {"source_mode", "derived_import_power", "derived_export_power"}
        ):
            return None
        value = self.entity_description.value_fn(snapshot, self.runtime)
        precision = self.entity_description.display_precision
        if (
            precision is None
            and self.entity_description.native_unit_of_measurement == UnitOfPower.KILO_WATT
        ):
            precision = 2
        if isinstance(value, float) and precision is not None:
            return round_for_display(value, precision)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        snapshot = self.runtime.snapshot
        attributes: dict[str, Any] = {}
        attributes.update(
            {
                "source_mode": self.runtime.source_mode,
                "source_entities": self.runtime.source_entities,
                "source_available": self.runtime.source_available,
                "source_status_reason": self.runtime.source_status_reason,
                "source_measurement_timestamp_utc": (self.runtime.source_measurement_timestamp_utc),
                "instantaneous_power_known": self.runtime.instantaneous_power_known,
                "export_known": self.runtime.export_known,
            }
        )
        if snapshot is not None:
            attributes.update(
                {
                    "quality": snapshot.quality.value,
                    "coverage_seconds": round(snapshot.coverage_seconds, 3),
                    "gap_seconds": round(snapshot.gap_seconds, 3),
                    "input_stale": snapshot.input_stale,
                    "simulation_enabled": bool(
                        self.runtime.settings.get("simulation_enabled", False)
                    ),
                }
            )
        if snapshot is not None and self.entity_description.key.endswith("15m_rolling"):
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
        if snapshot is not None and self.entity_description.budget_warning:
            attributes["safety_warning"] = ATTR_BUDGET_HEADROOM_WARNING
            if snapshot.projection.unrecoverable:
                attributes["advice_status"] = "cannot_restore_target"
        if snapshot is not None and self.entity_description.key.startswith("sustained_"):
            forecast = self.runtime.sustained_forecast
            if forecast is not None:
                attributes.update(
                    {
                        "forecast_horizon_minutes": forecast.horizon_minutes,
                        "smoothing_window_seconds": forecast.smoothing_seconds,
                        "source_measurement_age_seconds": forecast.measurement_age_seconds,
                        "valid_measurement_coverage_seconds": forecast.coverage_seconds,
                        "limiting_quarter_start": forecast.limiting_quarter_start_utc,
                        "limiting_quarter_end": forecast.limiting_quarter_end_utc,
                        "limiting_target_kw": forecast.limiting_target_kw,
                        "current_quarter_unrecoverable": (forecast.current_quarter_unrecoverable),
                        "forecast_assumption": forecast.assumption,
                        "reason": forecast.reason,
                    }
                )
            else:
                attributes["reason"] = self.runtime.sustained_status_reason
        if (
            "tariff" in self.entity_description.key
            or "block_contracted" in self.entity_description.key
        ):
            tariff = (
                self.runtime.next_tariff
                if self.entity_description.key.startswith("next")
                else self.runtime.current_tariff
            )
            if tariff is not None:
                attributes.update(
                    {
                        "rule_version": tariff.rule_version,
                        "rule_status": tariff.rule_status.value,
                        "source_reference": tariff.source_url,
                        "holiday_name": tariff.holiday_name,
                        "local_datetime": tariff.local_datetime,
                        "utc_offset_seconds": tariff.utc_offset_seconds,
                        "fold": tariff.fold,
                    }
                )
        if snapshot is not None and self.entity_description.key in {
            "forecast_smoothed_kw",
            "forecast_utilization_pct",
        }:
            attributes.update(
                {
                    "smoothing_window_complete": snapshot.smoothed_import.complete,
                    "smoothing_coverage_seconds": round(
                        snapshot.smoothed_import.coverage_seconds, 3
                    ),
                    "smoothing_gap_seconds": round(snapshot.smoothed_import.gap_seconds, 3),
                    "forecast_basis": "time_weighted_import_only_power",
                }
            )
        if (
            self.entity_description.key in CONTRACTUAL_SENSOR_KEYS
            or "tariff" in self.entity_description.key
            or "block_contracted" in self.entity_description.key
        ):
            attributes.update(
                {
                    "contractual_available": self.runtime.current_contractual_available,
                    "contractual_confirmed": self.runtime.current_contractual_confirmed,
                    "contractual_status_reason": self.runtime.contractual_status_reason,
                }
            )
            assignment = self.runtime.current_assignment
            if assignment is not None:
                attributes.update(
                    {
                        "target_effective_from": assignment.effective_from,
                        "target_effective_to": assignment.effective_to,
                        "target_provenance": assignment.provenance,
                        "target_recorded_on": assignment.recorded_on,
                    }
                )
        if self.entity_description.key in {
            "last_completed_15m_import_demand",
            "last_completed_15m_signed_average",
        }:
            archived = self.runtime.archived_last_completed
            if not self.runtime.engine.completed and archived is not None:
                attributes.update(
                    {
                        "quality": archived.quality,
                        "provenance": archived.provenance,
                        "quarter_start_utc": archived.start_utc,
                        "quarter_end_utc": archived.end_utc,
                        "restored_from_archive": True,
                    }
                )
        return attributes

    async def async_added_to_hass(self) -> None:
        """Subscribe to runtime updates."""

        await super().async_added_to_hass()
        self.async_on_remove(self.runtime.add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
