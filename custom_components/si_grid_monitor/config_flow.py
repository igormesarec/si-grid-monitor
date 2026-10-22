"""Guided configuration and native contracted-power management."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .adapters import AdapterError, ImportOnlyPowerAdapter, SeparatePowerAdapter, SignedPowerAdapter
from .const import (
    CONF_ALLOW_PROVISIONAL_TARIFF,
    CONF_ARCHIVE_REMOVAL_ACTION,
    CONF_ARCHIVE_REMOVAL_BACKUP,
    CONF_ARCHIVE_REMOVAL_CONFIRMATION,
    CONF_ARCHIVE_REMOVAL_CONFIRMED_AT,
    CONF_ASSIGNMENT_ACTION,
    CONF_ASSIGNMENT_END_DATE,
    CONF_ASSIGNMENT_PROVENANCE,
    CONF_ASSIGNMENT_RECORDED_ON,
    CONF_ASSIGNMENT_START_DATE,
    CONF_BACKUP_ARCHIVE_ON_REMOVE,
    CONF_CONTRACTED_POWER_PERIODS,
    CONF_COUNTER_BEHAVIOR,
    CONF_DELETE_ARCHIVE_ON_REMOVE,
    CONF_EXPORT_ENERGY_ENTITY,
    CONF_EXPORT_POWER_ENTITY,
    CONF_IMPORT_ENERGY_ENTITY,
    CONF_IMPORT_POWER_ENTITY,
    CONF_METER_NAME,
    CONF_POSITIVE_MEANS_IMPORT,
    CONF_POWER_ENTITY,
    CONF_RETENTION,
    CONF_SAFETY_MARGIN_KW,
    CONF_SIMULATION_ENABLED,
    CONF_SIMULATION_TARGET_KW,
    CONF_SMOOTHING_SECONDS,
    CONF_SOURCE_MODE,
    CONF_SUSTAINED_HORIZON_MINUTES,
    CONF_TARGET_KW,
    CONF_TARGET_MODE,
    COUNTER_BEHAVIORS,
    COUNTER_IMPORT_ONLY,
    COUNTER_NET,
    COUNTER_SEPARATE,
    DEFAULT_RETENTION,
    DEFAULT_SAFETY_MARGIN_KW,
    DEFAULT_SMOOTHING_SECONDS,
    DEFAULT_SUSTAINED_HORIZON_MINUTES,
    DEFAULT_TARGET_KW,
    DOMAIN,
    SMOOTHING_PRESETS,
    SOURCE_CUMULATIVE_ENERGY,
    SOURCE_IMPORT_ONLY,
    SOURCE_SEPARATE_POWER,
    SOURCE_SIGNED_POWER,
    SUSTAINED_HORIZON_PRESETS,
    TARGET_KEYS,
    TARGET_MODE_PER_BLOCK,
    TARGET_MODE_SHARED,
)
from .contracted_power import (
    ContractedPowerPeriod,
    ContractedPowerSchedule,
    contracted_power_schedule_from_json,
)

SOURCE_MODES = (
    SOURCE_SIGNED_POWER,
    SOURCE_SEPARATE_POWER,
    SOURCE_IMPORT_ONLY,
    SOURCE_CUMULATIVE_ENERGY,
)


def _number_field(name: str, default: float) -> tuple[Any, Any]:
    return vol.Required(name, default=default), selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0.0,
            max=1000.0,
            step=0.01,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="kW",
        )
    )


def _select(name: str, values: tuple[int, ...], default: int) -> tuple[Any, Any]:
    """Select values and their defaults are strings, fixing untouched defaults."""
    return vol.Required(name, default=str(default)), selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[str(value) for value in values], mode=selector.SelectSelectorMode.DROPDOWN
        )
    )


def _as_date(value: date | str) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def _period_from_input(data: dict[str, Any]) -> ContractedPowerPeriod:
    recorded = data.get(CONF_ASSIGNMENT_RECORDED_ON)
    return ContractedPowerPeriod(
        effective_from=_as_date(data[CONF_ASSIGNMENT_START_DATE]),
        effective_to=_as_date(data[CONF_ASSIGNMENT_END_DATE]),
        block_targets_kw=tuple(float(data[key]) for key in TARGET_KEYS),  # type: ignore[arg-type]
        provenance=str(data.get(CONF_ASSIGNMENT_PROVENANCE) or "user_configured"),
        recorded_on=_as_date(recorded) if recorded else None,
    )


def _period_schema(period: ContractedPowerPeriod | None = None) -> vol.Schema:
    targets = period.block_targets_kw if period else (DEFAULT_TARGET_KW,) * 5
    values: dict[Any, Any] = {
        vol.Required(
            CONF_ASSIGNMENT_START_DATE, default=period.effective_from if period else date.today()
        ): selector.DateSelector(),
        vol.Required(
            CONF_ASSIGNMENT_END_DATE, default=period.effective_to if period else date.today()
        ): selector.DateSelector(),
        vol.Optional(
            CONF_ASSIGNMENT_RECORDED_ON,
            default=period.recorded_on if period and period.recorded_on else None,
        ): selector.DateSelector(),
        vol.Required(
            CONF_ASSIGNMENT_PROVENANCE, default=period.provenance if period else "user_configured"
        ): selector.TextSelector(),
    }
    for key, value in zip(TARGET_KEYS, targets, strict=True):
        field, field_selector = _number_field(key, value)
        values[field] = field_selector
    return vol.Schema(values)


class SIGridMonitorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Six-step V0.4 installation wizard."""

    VERSION = 5
    MINOR_VERSION = 0

    def __init__(self) -> None:
        self._values: dict[str, Any] = {}
        self._polarity_preview = "live_reading=unavailable"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._values.update(user_input)
            if user_input[CONF_SOURCE_MODE] == SOURCE_CUMULATIVE_ENERGY:
                return await self.async_step_counter_type()
            return await self.async_step_meter()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_METER_NAME, default="Main Grid"): selector.TextSelector(),
                    vol.Required(
                        CONF_SOURCE_MODE, default=SOURCE_SIGNED_POWER
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(SOURCE_MODES),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="source_mode",
                        )
                    ),
                }
            ),
        )

    async def async_step_counter_type(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Choose one truthful cumulative-counter behavior before entity selection."""

        if user_input is not None:
            self._values.update(user_input)
            return await self.async_step_meter()
        return self.async_show_form(
            step_id="counter_type",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_COUNTER_BEHAVIOR, default=COUNTER_IMPORT_ONLY
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(COUNTER_BEHAVIORS),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="counter_behavior",
                        )
                    )
                }
            ),
        )

    async def async_step_meter(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            errors = self._validate_source_input(user_input)
            if not errors:
                self._values.update(user_input)
                self._polarity_preview = self._source_preview()
                return await self.async_step_polarity_preview()
        else:
            errors = {}
        mode = self._values.get(CONF_SOURCE_MODE, SOURCE_SIGNED_POWER)

        def entity() -> selector.EntitySelector:
            return selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))

        fields: dict[Any, Any]
        if mode == SOURCE_SIGNED_POWER:
            fields = {
                vol.Required(CONF_POWER_ENTITY): entity(),
                vol.Required(CONF_POSITIVE_MEANS_IMPORT, default=True): selector.BooleanSelector(),
            }
        elif mode == SOURCE_SEPARATE_POWER:
            fields = {
                vol.Required(CONF_IMPORT_POWER_ENTITY): entity(),
                vol.Required(CONF_EXPORT_POWER_ENTITY): entity(),
            }
        elif mode == SOURCE_IMPORT_ONLY:
            fields = {vol.Required(CONF_IMPORT_POWER_ENTITY): entity()}
        else:
            counter_behavior = self._values.get(CONF_COUNTER_BEHAVIOR, COUNTER_IMPORT_ONLY)
            fields = {vol.Required(CONF_IMPORT_ENERGY_ENTITY): entity()}
            if counter_behavior == COUNTER_NET:
                fields[vol.Required(CONF_POSITIVE_MEANS_IMPORT, default=True)] = (
                    selector.BooleanSelector()
                )
            elif counter_behavior == COUNTER_SEPARATE:
                fields[vol.Optional(CONF_EXPORT_ENERGY_ENTITY)] = entity()
        return self.async_show_form(
            step_id="meter",
            data_schema=vol.Schema(fields),
            errors=errors,
        )

    def _validate_source_input(self, user_input: dict[str, Any]) -> dict[str, str]:
        """Validate selected entity units and live values with actionable errors."""

        mode = str(self._values.get(CONF_SOURCE_MODE, SOURCE_SIGNED_POWER))
        combined = {**self._values, **user_input}
        keys = {
            SOURCE_SIGNED_POWER: (CONF_POWER_ENTITY,),
            SOURCE_SEPARATE_POWER: (CONF_IMPORT_POWER_ENTITY, CONF_EXPORT_POWER_ENTITY),
            SOURCE_IMPORT_ONLY: (CONF_IMPORT_POWER_ENTITY,),
            SOURCE_CUMULATIVE_ENERGY: (
                CONF_IMPORT_ENERGY_ENTITY,
                CONF_EXPORT_ENERGY_ENTITY,
            ),
        }[mode]
        states = []
        for key in keys:
            entity_id = combined.get(key)
            if not entity_id:
                continue
            state = self.hass.states.get(entity_id)
            if state is None:
                return {"base": "source_not_found"}
            states.append(state)
            unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
            expected = {"Wh", "kWh"} if mode == SOURCE_CUMULATIVE_ENERGY else {"W", "kW"}
            if unit not in expected:
                return {"base": "invalid_source_unit"}
            if mode == SOURCE_CUMULATIVE_ENERGY and state.attributes.get("state_class") not in {
                "total",
                "total_increasing",
            }:
                return {"base": "invalid_counter_state_class"}
            if state.state in {STATE_UNKNOWN, STATE_UNAVAILABLE, "none", ""}:
                continue
            try:
                numeric = float(state.state)
            except (TypeError, ValueError):
                return {"base": "invalid_source_value"}
            if mode in {SOURCE_SEPARATE_POWER, SOURCE_IMPORT_ONLY} and numeric < 0:
                return {"base": "negative_nonnegative_source"}
        if (
            mode == SOURCE_SEPARATE_POWER
            and len(states) == 2
            and all(
                state.state not in {STATE_UNKNOWN, STATE_UNAVAILABLE, "none", ""}
                for state in states
            )
        ):
            try:
                SeparatePowerAdapter().normalize(
                    states[0].state,
                    str(states[0].attributes[ATTR_UNIT_OF_MEASUREMENT]),
                    states[1].state,
                    str(states[1].attributes[ATTR_UNIT_OF_MEASUREMENT]),
                )
            except AdapterError:
                return {"base": "conflicting_power_sources"}
        return {}

    def _source_preview(self) -> str:
        mode = str(self._values.get(CONF_SOURCE_MODE, SOURCE_SIGNED_POWER))
        keys = {
            SOURCE_SIGNED_POWER: (CONF_POWER_ENTITY,),
            SOURCE_SEPARATE_POWER: (CONF_IMPORT_POWER_ENTITY, CONF_EXPORT_POWER_ENTITY),
            SOURCE_IMPORT_ONLY: (CONF_IMPORT_POWER_ENTITY,),
            SOURCE_CUMULATIVE_ENERGY: (CONF_IMPORT_ENERGY_ENTITY, CONF_EXPORT_ENERGY_ENTITY),
        }[mode]
        readings: list[str] = []
        states: list[Any] = []
        for key in keys:
            entity_id = self._values.get(key)
            if not entity_id:
                continue
            state = self.hass.states.get(entity_id)
            if state is not None:
                states.append(state)
                readings.append(
                    f"{entity_id}: {state.state} "
                    f"{state.attributes.get('unit_of_measurement', '')}".strip()
                )
        kind = "counter_interval_average" if mode == SOURCE_CUMULATIVE_ENERGY else "direct_power"
        counter_behavior = self._values.get(CONF_COUNTER_BEHAVIOR, COUNTER_IMPORT_ONLY)
        export_unknown = mode == SOURCE_IMPORT_ONLY or (
            mode == SOURCE_CUMULATIVE_ENERGY
            and counter_behavior != COUNTER_NET
            and not self._values.get(CONF_EXPORT_ENERGY_ENTITY)
        )
        export = (
            "unknown"
            if export_unknown
            else "inferred_from_net_delta"
            if mode == SOURCE_CUMULATIVE_ENERGY and counter_behavior == COUNTER_NET
            else "measured"
        )
        normalized = ""
        try:
            if mode == SOURCE_SIGNED_POWER and states:
                sample = SignedPowerAdapter(
                    positive_means_import=bool(self._values[CONF_POSITIVE_MEANS_IMPORT])
                ).normalize(
                    states[0].state,
                    str(states[0].attributes.get("unit_of_measurement", "")),
                )
            elif mode == SOURCE_SEPARATE_POWER and len(states) == 2:
                sample = SeparatePowerAdapter().normalize(
                    states[0].state,
                    str(states[0].attributes.get("unit_of_measurement", "")),
                    states[1].state,
                    str(states[1].attributes.get("unit_of_measurement", "")),
                )
            elif mode == SOURCE_IMPORT_ONLY and states:
                sample = ImportOnlyPowerAdapter().normalize(
                    states[0].state,
                    str(states[0].attributes.get("unit_of_measurement", "")),
                )
            else:
                sample = None
            if sample is not None:
                normalized = f" normalized_signed={sample.signed_kw:+.3f} kW."
        except (AdapterError, TypeError, ValueError):
            normalized = " normalized_signed=unavailable."
        counter_note = (
            f" counter_behavior={counter_behavior}; second_reading_required=true."
            if mode == SOURCE_CUMULATIVE_ENERGY
            else ""
        )
        return (
            f"mode={mode}; measurement={kind}; export={export}. "
            + ("; ".join(readings) or "live_reading=unavailable")
            + normalized
            + counter_note
        )

    async def async_step_polarity_preview(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return await self.async_step_contract()
        return self.async_show_form(
            step_id="polarity_preview",
            data_schema=vol.Schema(
                {vol.Required("confirm", default=True): selector.BooleanSelector()}
            ),
            description_placeholders={"preview": self._polarity_preview},
        )

    async def async_step_contract(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if _as_date(user_input[CONF_ASSIGNMENT_END_DATE]) < _as_date(
                user_input[CONF_ASSIGNMENT_START_DATE]
            ):
                errors["base"] = "invalid_contracted_power_periods"
            else:
                self._values.update(user_input)
                return await self.async_step_target_mode()
        return self.async_show_form(
            step_id="contract",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ASSIGNMENT_START_DATE): selector.DateSelector(),
                    vol.Required(CONF_ASSIGNMENT_END_DATE): selector.DateSelector(),
                    vol.Optional(CONF_ASSIGNMENT_RECORDED_ON): selector.DateSelector(),
                    vol.Required(
                        CONF_ASSIGNMENT_PROVENANCE, default="user_configured"
                    ): selector.TextSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_target_mode(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._values.update(user_input)
            if user_input[CONF_TARGET_MODE] == TARGET_MODE_SHARED:
                return await self.async_step_shared_target()
            return await self.async_step_individual_targets()
        return self.async_show_form(
            step_id="target_mode",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TARGET_MODE, default=TARGET_MODE_SHARED
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[TARGET_MODE_SHARED, TARGET_MODE_PER_BLOCK],
                            translation_key="target_mode",
                        )
                    )
                }
            ),
        )

    async def async_step_shared_target(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            target = float(user_input[CONF_TARGET_KW])
            self._values[CONF_TARGET_KW] = target
            self._values.update({key: target for key in TARGET_KEYS})
            return await self.async_step_calculation()
        field, field_selector = _number_field(CONF_TARGET_KW, DEFAULT_TARGET_KW)
        return self.async_show_form(
            step_id="shared_target", data_schema=vol.Schema({field: field_selector})
        )

    async def async_step_individual_targets(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._values.update(user_input)
            self._values[CONF_TARGET_KW] = float(user_input[TARGET_KEYS[0]])
            return await self.async_step_calculation()
        values: dict[Any, Any] = {}
        for key in TARGET_KEYS:
            field, field_selector = _number_field(key, DEFAULT_TARGET_KW)
            values[field] = field_selector
        return self.async_show_form(step_id="individual_targets", data_schema=vol.Schema(values))

    async def async_step_calculation(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._values.update(user_input)
            self._values[CONF_SMOOTHING_SECONDS] = int(user_input[CONF_SMOOTHING_SECONDS])
            self._values[CONF_SUSTAINED_HORIZON_MINUTES] = int(
                user_input[CONF_SUSTAINED_HORIZON_MINUTES]
            )
            return await self.async_step_review()
        smoothing, smoothing_selector = _select(
            CONF_SMOOTHING_SECONDS, SMOOTHING_PRESETS, DEFAULT_SMOOTHING_SECONDS
        )
        horizon, horizon_selector = _select(
            CONF_SUSTAINED_HORIZON_MINUTES,
            SUSTAINED_HORIZON_PRESETS,
            DEFAULT_SUSTAINED_HORIZON_MINUTES,
        )
        margin, margin_selector = _number_field(CONF_SAFETY_MARGIN_KW, DEFAULT_SAFETY_MARGIN_KW)
        simulation_target, simulation_target_selector = _number_field(
            CONF_SIMULATION_TARGET_KW,
            float(self._values.get(CONF_TARGET_KW, DEFAULT_TARGET_KW)),
        )
        return self.async_show_form(
            step_id="calculation",
            data_schema=vol.Schema(
                {
                    margin: margin_selector,
                    smoothing: smoothing_selector,
                    horizon: horizon_selector,
                    vol.Required(
                        CONF_RETENTION, default=DEFAULT_RETENTION
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=[DEFAULT_RETENTION])
                    ),
                    vol.Required(
                        CONF_ALLOW_PROVISIONAL_TARIFF, default=False
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_SIMULATION_ENABLED, default=False
                    ): selector.BooleanSelector(),
                    simulation_target: simulation_target_selector,
                }
            ),
        )

    async def async_step_review(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            period = _period_from_input(self._values)
            self._values[CONF_CONTRACTED_POWER_PERIODS] = ContractedPowerSchedule(
                (period,)
            ).to_json()
            self._values.setdefault(CONF_SIMULATION_ENABLED, False)
            self._values.setdefault(CONF_SIMULATION_TARGET_KW, self._values[CONF_TARGET_KW])
            mode = str(self._values[CONF_SOURCE_MODE])
            source_ids = [
                str(self._values[key])
                for key in (
                    CONF_POWER_ENTITY,
                    CONF_IMPORT_POWER_ENTITY,
                    CONF_EXPORT_POWER_ENTITY,
                    CONF_IMPORT_ENERGY_ENTITY,
                    CONF_EXPORT_ENERGY_ENTITY,
                )
                if self._values.get(key)
            ]
            entity_id = ", ".join(source_ids)
            unique_id = (
                f"signed:{source_ids[0]}"
                if mode == SOURCE_SIGNED_POWER
                else f"{mode}:{'|'.join(source_ids)}"
            )
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            meter_name = str(self._values.get(CONF_METER_NAME) or entity_id)
            return self.async_create_entry(title=meter_name, data=self._values)
        return self.async_show_form(
            step_id="review",
            data_schema=vol.Schema(
                {vol.Required("confirm", default=True): selector.BooleanSelector()}
            ),
            description_placeholders={
                "entity": ", ".join(
                    str(self._values[key])
                    for key in (
                        CONF_POWER_ENTITY,
                        CONF_IMPORT_POWER_ENTITY,
                        CONF_EXPORT_POWER_ENTITY,
                        CONF_IMPORT_ENERGY_ENTITY,
                        CONF_EXPORT_ENERGY_ENTITY,
                    )
                    if self._values.get(key)
                ),
                "dates": (
                    f"{self._values.get(CONF_ASSIGNMENT_START_DATE)} - "
                    f"{self._values.get(CONF_ASSIGNMENT_END_DATE)}"
                ),
                "targets": ", ".join(
                    f"B{i + 1} {float(self._values[key]):.2f} kW"
                    for i, key in enumerate(TARGET_KEYS)
                ),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return SIGridMonitorOptionsFlow()


class SIGridMonitorOptionsFlow(config_entries.OptionsFlow):
    """Native settings and assignment editor; JSON remains internal."""

    def __init__(self) -> None:
        self._selected_index: int | None = None
        self._pending_archive_backup = True

    @property
    def _current(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    @property
    def _schedule(self) -> ContractedPowerSchedule:
        return contracted_power_schedule_from_json(
            self._current.get(CONF_CONTRACTED_POWER_PERIODS, "[]")
        )

    def _save(self, updates: dict[str, Any]) -> FlowResult:
        values = dict(self.config_entry.options)
        values.update(updates)
        return self.async_create_entry(title="", data=values)

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["settings", "assignments", "add_assignment", "archive_removal"],
        )

    async def async_step_archive_removal(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure the explicit archive policy used only on entry removal."""

        if user_input is not None:
            action = str(user_input[CONF_ARCHIVE_REMOVAL_ACTION])
            if action == "keep":
                return self._save(
                    {
                        CONF_DELETE_ARCHIVE_ON_REMOVE: False,
                        CONF_BACKUP_ARCHIVE_ON_REMOVE: False,
                        CONF_ARCHIVE_REMOVAL_CONFIRMED_AT: "",
                    }
                )
            self._pending_archive_backup = bool(user_input.get(CONF_ARCHIVE_REMOVAL_BACKUP, True))
            return await self.async_step_confirm_archive_deletion()
        return self.async_show_form(
            step_id="archive_removal",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ARCHIVE_REMOVAL_ACTION, default="keep"
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=["keep", "delete"],
                            translation_key="archive_removal_action",
                        )
                    ),
                    vol.Required(
                        CONF_ARCHIVE_REMOVAL_BACKUP, default=True
                    ): selector.BooleanSelector(),
                }
            ),
            description_placeholders={"meter": self.config_entry.title},
        )

    async def async_step_confirm_archive_deletion(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Require the exact friendly meter name before arming deletion."""

        errors: dict[str, str] = {}
        expected = f"DELETE {self.config_entry.title}"
        if user_input is not None:
            if str(user_input[CONF_ARCHIVE_REMOVAL_CONFIRMATION]).strip() != expected:
                errors["base"] = "archive_delete_confirmation_mismatch"
            else:
                return self._save(
                    {
                        CONF_DELETE_ARCHIVE_ON_REMOVE: True,
                        CONF_BACKUP_ARCHIVE_ON_REMOVE: self._pending_archive_backup,
                        CONF_ARCHIVE_REMOVAL_CONFIRMED_AT: datetime.now(UTC).isoformat(),
                    }
                )
        return self.async_show_form(
            step_id="confirm_archive_deletion",
            data_schema=vol.Schema(
                {vol.Required(CONF_ARCHIVE_REMOVAL_CONFIRMATION): selector.TextSelector()}
            ),
            errors=errors,
            description_placeholders={"confirmation": expected, "meter": self.config_entry.title},
        )

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        current = self._current
        if user_input is not None:
            user_input[CONF_SMOOTHING_SECONDS] = int(user_input[CONF_SMOOTHING_SECONDS])
            user_input[CONF_SUSTAINED_HORIZON_MINUTES] = int(
                user_input[CONF_SUSTAINED_HORIZON_MINUTES]
            )
            if (
                current.get(CONF_SOURCE_MODE) == SOURCE_CUMULATIVE_ENERGY
                and user_input.get(CONF_COUNTER_BEHAVIOR) != COUNTER_SEPARATE
            ):
                # Override any prior separate-export source stored in entry data;
                # the runtime must not subscribe to or identify an unused channel.
                user_input[CONF_EXPORT_ENERGY_ENTITY] = None
            meter_name = str(user_input.get(CONF_METER_NAME) or self.config_entry.title)
            self.hass.config_entries.async_update_entry(self.config_entry, title=meter_name)
            return self._save(user_input)
        smoothing, smoothing_selector = _select(
            CONF_SMOOTHING_SECONDS,
            SMOOTHING_PRESETS,
            int(current.get(CONF_SMOOTHING_SECONDS, DEFAULT_SMOOTHING_SECONDS)),
        )
        horizon, horizon_selector = _select(
            CONF_SUSTAINED_HORIZON_MINUTES,
            SUSTAINED_HORIZON_PRESETS,
            int(current.get(CONF_SUSTAINED_HORIZON_MINUTES, DEFAULT_SUSTAINED_HORIZON_MINUTES)),
        )
        margin, margin_selector = _number_field(
            CONF_SAFETY_MARGIN_KW,
            float(current.get(CONF_SAFETY_MARGIN_KW, DEFAULT_SAFETY_MARGIN_KW)),
        )
        simulation_target, simulation_target_selector = _number_field(
            CONF_SIMULATION_TARGET_KW,
            float(
                current.get(
                    CONF_SIMULATION_TARGET_KW,
                    current.get(CONF_TARGET_KW, DEFAULT_TARGET_KW),
                )
            ),
        )
        mode = str(current.get(CONF_SOURCE_MODE, SOURCE_SIGNED_POWER))

        def entity() -> selector.EntitySelector:
            return selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))

        source_fields: dict[Any, Any]
        if mode == SOURCE_SIGNED_POWER:
            source_fields = {
                vol.Required(CONF_POWER_ENTITY, default=current[CONF_POWER_ENTITY]): entity(),
                vol.Required(
                    CONF_POSITIVE_MEANS_IMPORT,
                    default=bool(current.get(CONF_POSITIVE_MEANS_IMPORT, True)),
                ): selector.BooleanSelector(),
            }
        elif mode == SOURCE_SEPARATE_POWER:
            source_fields = {
                vol.Required(
                    CONF_IMPORT_POWER_ENTITY, default=current[CONF_IMPORT_POWER_ENTITY]
                ): entity(),
                vol.Required(
                    CONF_EXPORT_POWER_ENTITY, default=current[CONF_EXPORT_POWER_ENTITY]
                ): entity(),
            }
        elif mode == SOURCE_IMPORT_ONLY:
            source_fields = {
                vol.Required(
                    CONF_IMPORT_POWER_ENTITY, default=current[CONF_IMPORT_POWER_ENTITY]
                ): entity()
            }
        else:
            export_energy_key = (
                vol.Optional(
                    CONF_EXPORT_ENERGY_ENTITY,
                    default=current[CONF_EXPORT_ENERGY_ENTITY],
                )
                if current.get(CONF_EXPORT_ENERGY_ENTITY)
                else vol.Optional(CONF_EXPORT_ENERGY_ENTITY)
            )
            source_fields = {
                vol.Required(
                    CONF_COUNTER_BEHAVIOR,
                    default=current.get(CONF_COUNTER_BEHAVIOR, COUNTER_IMPORT_ONLY),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=list(COUNTER_BEHAVIORS),
                        translation_key="counter_behavior",
                    )
                ),
                vol.Required(
                    CONF_IMPORT_ENERGY_ENTITY, default=current[CONF_IMPORT_ENERGY_ENTITY]
                ): entity(),
                export_energy_key: entity(),
                vol.Required(
                    CONF_POSITIVE_MEANS_IMPORT,
                    default=bool(current.get(CONF_POSITIVE_MEANS_IMPORT, True)),
                ): selector.BooleanSelector(),
            }
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_METER_NAME,
                        default=str(current.get(CONF_METER_NAME) or self.config_entry.title),
                    ): selector.TextSelector(),
                    **source_fields,
                    margin: margin_selector,
                    smoothing: smoothing_selector,
                    horizon: horizon_selector,
                    vol.Required(
                        CONF_RETENTION, default=current.get(CONF_RETENTION, DEFAULT_RETENTION)
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=[DEFAULT_RETENTION])
                    ),
                    vol.Required(
                        CONF_ALLOW_PROVISIONAL_TARIFF,
                        default=bool(current.get(CONF_ALLOW_PROVISIONAL_TARIFF, False)),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_SIMULATION_ENABLED,
                        default=bool(current.get(CONF_SIMULATION_ENABLED, False)),
                    ): selector.BooleanSelector(),
                    simulation_target: simulation_target_selector,
                }
            ),
        )

    async def async_step_assignments(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            action = str(user_input[CONF_ASSIGNMENT_ACTION])
            operation, index = action.split(":", 1)
            self._selected_index = int(index)
            if operation == "remove":
                return await self.async_step_remove_assignment()
            return await self.async_step_edit_assignment()
        options = []
        for index, period in enumerate(self._schedule.periods):
            today = date.today()
            status = (
                "active"
                if period.effective_from <= today <= period.effective_to
                else "expired"
                if period.effective_to < today
                else "future"
            )
            label = (
                f"{status.upper()} · {period.effective_from} - {period.effective_to} · "
                + "/".join(f"{target:.2f}" for target in period.block_targets_kw)
                + " kW"
            )
            options.extend(
                (
                    {"value": f"edit:{index}", "label": f"Edit · {label}"},
                    {"value": f"remove:{index}", "label": f"Remove · {label}"},
                )
            )
        if not options:
            return await self.async_step_add_assignment()
        return self.async_show_form(
            step_id="assignments",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ASSIGNMENT_ACTION): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=options)
                    )
                }
            ),
        )

    async def async_step_add_assignment(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        self._selected_index = None
        return await self._assignment_form("add_assignment", user_input)

    async def async_step_edit_assignment(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return await self._assignment_form("edit_assignment", user_input)

    async def _assignment_form(self, step_id: str, user_input: dict[str, Any] | None) -> FlowResult:
        errors: dict[str, str] = {}
        periods = list(self._schedule.periods)
        existing = periods[self._selected_index] if self._selected_index is not None else None
        if user_input is not None:
            try:
                replacement = _period_from_input(user_input)
                if self._selected_index is None:
                    periods.append(replacement)
                else:
                    periods[self._selected_index] = replacement
                schedule = ContractedPowerSchedule(tuple(periods))
            except ValueError:
                errors["base"] = "invalid_contracted_power_periods"
            else:
                active = schedule.period_for(date.today()) or replacement
                return self._save(
                    {
                        CONF_CONTRACTED_POWER_PERIODS: schedule.to_json(),
                        CONF_TARGET_MODE: TARGET_MODE_PER_BLOCK,
                        CONF_TARGET_KW: active.block_targets_kw[0],
                        **dict(zip(TARGET_KEYS, active.block_targets_kw, strict=True)),
                    }
                )
        return self.async_show_form(
            step_id=step_id, data_schema=_period_schema(existing), errors=errors
        )

    async def async_step_remove_assignment(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if self._selected_index is None:
            return await self.async_step_assignments()
        if user_input is not None and user_input["confirm"]:
            periods = list(self._schedule.periods)
            periods.pop(self._selected_index)
            return self._save(
                {CONF_CONTRACTED_POWER_PERIODS: ContractedPowerSchedule(tuple(periods)).to_json()}
            )
        return self.async_show_form(
            step_id="remove_assignment",
            data_schema=vol.Schema(
                {vol.Required("confirm", default=False): selector.BooleanSelector()}
            ),
        )
