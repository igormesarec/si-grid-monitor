"""Guided configuration and native contracted-power management."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .adapters import AdapterError, ImportOnlyPowerAdapter, SeparatePowerAdapter, SignedPowerAdapter
from .const import (
    CONF_ALLOW_PROVISIONAL_TARIFF,
    CONF_ARCHIVE_REMOVAL_ACTION,
    CONF_ARCHIVE_REMOVAL_BACKUP,
    CONF_ARCHIVE_REMOVAL_CONFIRMATION,
    CONF_ARCHIVE_REMOVAL_CONFIRMED_AT,
    CONF_ASSIGNMENT_ACTION,
    CONF_ASSIGNMENT_CHANGE_END_DATE,
    CONF_ASSIGNMENT_END_DATE,
    CONF_ASSIGNMENT_PROVENANCE,
    CONF_ASSIGNMENT_RECORDED_ON,
    CONF_ASSIGNMENT_START_DATE,
    CONF_BACKUP_ARCHIVE_ON_REMOVE,
    CONF_CONTRACTED_POWER_PERIODS,
    CONF_DELETE_ARCHIVE_ON_REMOVE,
    CONF_EXPORT_POWER_ENTITY,
    CONF_IMPORT_POWER_ENTITY,
    CONF_METER_NAME,
    CONF_PENDING_CONTRACT_AUDIT,
    CONF_POSITIVE_MEANS_IMPORT,
    CONF_POWER_ENTITY,
    CONF_PREFERRED_LANGUAGE,
    CONF_PUBLISHING_ACTIONABLE_INTERVAL_SECONDS,
    CONF_PUBLISHING_ENERGY_DEADBAND_KWH,
    CONF_PUBLISHING_FAST_ENTITIES,
    CONF_PUBLISHING_POWER_DEADBAND_KW,
    CONF_PUBLISHING_PROFILE,
    CONF_PUBLISHING_ROUTINE_INTERVAL_SECONDS,
    CONF_RETENTION,
    CONF_SAFETY_MARGIN_KW,
    CONF_SIMULATION_ENABLED,
    CONF_SIMULATION_TARGET_KW,
    CONF_SMOOTHING_SECONDS,
    CONF_SOURCE_MODE,
    CONF_SUSTAINED_HORIZON_MINUTES,
    CONF_TARGET_KW,
    CONF_TARGET_MODE,
    DEFAULT_PREFERRED_LANGUAGE,
    DEFAULT_PUBLISHING_ACTIONABLE_INTERVAL_SECONDS,
    DEFAULT_PUBLISHING_ENERGY_DEADBAND_KWH,
    DEFAULT_PUBLISHING_POWER_DEADBAND_KW,
    DEFAULT_PUBLISHING_PROFILE,
    DEFAULT_PUBLISHING_ROUTINE_INTERVAL_SECONDS,
    DEFAULT_RETENTION,
    DEFAULT_SAFETY_MARGIN_KW,
    DEFAULT_SMOOTHING_SECONDS,
    DEFAULT_SUSTAINED_HORIZON_MINUTES,
    DEFAULT_TARGET_KW,
    DOMAIN,
    PUBLISHING_FAST_ENTITY_OPTIONS,
    PUBLISHING_INTERVAL_PRESETS,
    PUBLISHING_PROFILES,
    SMOOTHING_PRESETS,
    SOURCE_IMPORT_ONLY,
    SOURCE_SEPARATE_POWER,
    SOURCE_SIGNED_POWER,
    SUPPORTED_LANGUAGES,
    SUPPORTED_SOURCE_MODES,
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
from .publishing import STORAGE_BUDGET_BYTES_PER_YEAR, projected_profile_bytes_per_year
from .source_identity import find_duplicate_source_entry, source_unique_id

SOURCE_MODES = SUPPORTED_SOURCE_MODES


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


def _local_today() -> date:
    """Return the Slovenian contract date, independent of server timezone."""

    from .engine import LJUBLJANA

    return dt_util.utcnow().astimezone(LJUBLJANA).date()


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
    recorded_key: Any = (
        vol.Optional(CONF_ASSIGNMENT_RECORDED_ON, default=period.recorded_on)
        if period is not None and period.recorded_on is not None
        else vol.Optional(CONF_ASSIGNMENT_RECORDED_ON)
    )
    values: dict[Any, Any] = {
        vol.Required(
            CONF_ASSIGNMENT_START_DATE, default=period.effective_from if period else _local_today()
        ): selector.DateSelector(),
        vol.Required(
            CONF_ASSIGNMENT_END_DATE, default=period.effective_to if period else _local_today()
        ): selector.DateSelector(),
        recorded_key: selector.DateSelector(),
        vol.Required(
            CONF_ASSIGNMENT_PROVENANCE, default=period.provenance if period else "user_configured"
        ): selector.TextSelector(),
    }
    for key, value in zip(TARGET_KEYS, targets, strict=True):
        field, field_selector = _number_field(key, value)
        values[field] = field_selector
    return vol.Schema(values)


def _schedule_summary(schedule: ContractedPowerSchedule) -> str:
    if not schedule.periods:
        return "No assignments"
    return "\n".join(
        f"{period.effective_from.isoformat()} - {period.effective_to.isoformat()}: "
        + "/".join(f"{target:.3f}" for target in period.block_targets_kw)
        + " kW"
        for period in schedule.periods
    )


def _schedule_revision(schedule: ContractedPowerSchedule) -> str:
    """Return a stable revision for optimistic contract-schedule concurrency."""

    return hashlib.sha256(schedule.to_json().encode()).hexdigest()


def _schedule_gap_summary(before: ContractedPowerSchedule, after: ContractedPowerSchedule) -> str:
    """Describe gaps across the original schedule span for confirmation."""

    if not before.periods:
        return "None"
    gaps = after.gaps(before.periods[0].effective_from, before.periods[-1].effective_to)
    if not gaps:
        return "None"
    return ", ".join(f"{start.isoformat()} - {end.isoformat()}" for start, end in gaps)


class SIGridMonitorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Guided installation wizard for SI Grid Monitor."""

    VERSION = 6
    MINOR_VERSION = 0

    def __init__(self) -> None:
        self._values: dict[str, Any] = {}
        self._polarity_preview = "live_reading=unavailable"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._values.update(user_input)
            return await self.async_step_source()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PREFERRED_LANGUAGE, default=DEFAULT_PREFERRED_LANGUAGE
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(SUPPORTED_LANGUAGES),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="preferred_language",
                        )
                    ),
                }
            ),
        )

    async def async_step_source(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Select a friendly meter name and one of the supported source modes."""

        if user_input is not None:
            self._values.update(user_input)
            return await self.async_step_meter()
        return self.async_show_form(
            step_id="source",
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

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Explicitly replace a source while preserving entry/archive identity."""

        entry = self._get_reconfigure_entry()
        if user_input is not None:
            self._values = {
                CONF_METER_NAME: str(
                    user_input.get(CONF_METER_NAME) or entry.title or "SI Grid Monitor"
                ),
                CONF_SOURCE_MODE: str(user_input[CONF_SOURCE_MODE]),
            }
            return await self.async_step_reconfigure_meter()
        current = {**entry.data, **entry.options}
        current_mode = str(current.get(CONF_SOURCE_MODE, SOURCE_SIGNED_POWER))
        default_mode = current_mode if current_mode in SOURCE_MODES else SOURCE_SIGNED_POWER
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_METER_NAME,
                        default=str(current.get(CONF_METER_NAME) or entry.title),
                    ): selector.TextSelector(),
                    vol.Required(CONF_SOURCE_MODE, default=default_mode): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(SOURCE_MODES),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="source_mode",
                        )
                    ),
                }
            ),
        )

    async def async_step_reconfigure_meter(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Validate a replacement live-power source and reload the same entry."""

        mode = str(self._values[CONF_SOURCE_MODE])

        def entity() -> selector.EntitySelector:
            return selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))

        if mode == SOURCE_SIGNED_POWER:
            fields: dict[Any, Any] = {
                vol.Required(CONF_POWER_ENTITY): entity(),
                vol.Required(CONF_POSITIVE_MEANS_IMPORT, default=True): selector.BooleanSelector(),
            }
        elif mode == SOURCE_SEPARATE_POWER:
            fields = {
                vol.Required(CONF_IMPORT_POWER_ENTITY): entity(),
                vol.Required(CONF_EXPORT_POWER_ENTITY): entity(),
            }
        else:
            fields = {vol.Required(CONF_IMPORT_POWER_ENTITY): entity()}
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._validate_source_input(user_input)
            if not errors:
                updates = {**self._values, **user_input}
                entry = self._get_reconfigure_entry()
                target_unique_id = source_unique_id(mode, updates)
                await self.async_set_unique_id(target_unique_id)
                duplicate = find_duplicate_source_entry(
                    self.hass.config_entries.async_entries(DOMAIN),
                    current_entry_id=entry.entry_id,
                    target_unique_id=target_unique_id,
                )
                if duplicate is not None:
                    return self.async_abort(reason="already_configured")
                # The source owns the config-entry unique ID. Rebinding updates
                # it only after collision checks; entry_id/archive namespace is
                # deliberately unchanged.
                self.hass.config_entries.async_update_entry(
                    entry,
                    title=str(updates[CONF_METER_NAME]),
                    unique_id=target_unique_id,
                )
                update_target = (
                    {"options_updates": updates}
                    if CONF_SOURCE_MODE in entry.options
                    else {"data_updates": updates}
                )
                return self.async_update_reload_and_abort(
                    entry, reason="reconfigure_successful", **update_target
                )
        return self.async_show_form(
            step_id="reconfigure_meter",
            data_schema=vol.Schema(fields),
            errors=errors,
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
            raise ValueError(f"unsupported source mode: {mode}")
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
            expected = {"W", "kW"}
            if unit not in expected:
                return {"base": "invalid_source_unit"}
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
        kind = "direct_power"
        export = "unknown" if mode == SOURCE_IMPORT_ONLY else "measured"
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
        return (
            f"mode={mode}; measurement={kind}; export={export}. "
            + ("; ".join(readings) or "live_reading=unavailable")
            + normalized
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
                )
                if self._values.get(key)
            ]
            entity_id = ", ".join(source_ids)
            unique_id = source_unique_id(mode, self._values)
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
                    )
                    if self._values.get(key)
                ),
                "dates": (
                    f"{self._values.get(CONF_ASSIGNMENT_START_DATE)} - "
                    f"{self._values.get(CONF_ASSIGNMENT_END_DATE)}"
                ),
                "targets": ", ".join(
                    f"B{i + 1} {float(self._values[key]):.3f} kW"
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
        self._pending_schedule: ContractedPowerSchedule | None = None
        self._pending_event: dict[str, Any] | None = None
        self._pending_original_schedule_json: str | None = None
        self._pending_original_revision: str | None = None
        self._pending_publishing: dict[str, Any] | None = None

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

    def _save_schedule(
        self,
        schedule: ContractedPowerSchedule,
        *,
        event_type: str,
        affected: ContractedPowerPeriod | None,
        old_schedule_json: str | None = None,
    ) -> FlowResult:
        """Save one complete schedule plus recoverable, idempotent audit intent."""

        old_json = old_schedule_json if old_schedule_json is not None else self._schedule.to_json()
        new_json = schedule.to_json()
        revision = hashlib.sha256(new_json.encode()).hexdigest()
        event = {
            "event_id": str(uuid.uuid4()),
            "event_utc": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "old_schedule_json": old_json,
            "new_schedule_json": new_json,
            "effective_from": affected.effective_from.isoformat() if affected else None,
            "effective_to": affected.effective_to.isoformat() if affected else None,
            "provenance": affected.provenance if affected else None,
            "recorded_on": (
                affected.recorded_on.isoformat()
                if affected is not None and affected.recorded_on is not None
                else None
            ),
            "origin": "user_action",
            "actor": None,
            "configuration_revision": revision,
        }
        raw_pending = self._current.get(CONF_PENDING_CONTRACT_AUDIT, [])
        try:
            pending = json.loads(raw_pending) if isinstance(raw_pending, str) else list(raw_pending)
        except (TypeError, ValueError, json.JSONDecodeError):
            pending = []
        pending = [*pending[-49:], event]
        active = schedule.period_for(_local_today()) or affected
        updates: dict[str, Any] = {
            CONF_CONTRACTED_POWER_PERIODS: new_json,
            CONF_PENDING_CONTRACT_AUDIT: pending,
            CONF_TARGET_MODE: TARGET_MODE_PER_BLOCK,
        }
        if active is not None:
            updates.update(
                {
                    CONF_TARGET_KW: active.block_targets_kw[0],
                    **dict(zip(TARGET_KEYS, active.block_targets_kw, strict=True)),
                }
            )
        return self._save(updates)

    def _preview(
        self,
        schedule: ContractedPowerSchedule,
        *,
        event_type: str,
        affected: ContractedPowerPeriod | None,
    ) -> FlowResult:
        original = self._schedule
        self._pending_schedule = schedule
        self._pending_event = {"event_type": event_type, "affected": affected}
        self._pending_original_schedule_json = original.to_json()
        self._pending_original_revision = _schedule_revision(original)
        if not hasattr(self, "async_show_form"):
            return self._save_schedule(schedule, event_type=event_type, affected=affected)
        return self.async_show_form(
            step_id="contract_preview",
            data_schema=vol.Schema(
                {vol.Required("confirm", default=False): selector.BooleanSelector()}
            ),
            description_placeholders={
                "before": _schedule_summary(original),
                "after": _schedule_summary(schedule),
                "gaps": _schedule_gap_summary(self._schedule, schedule),
            },
        )

    async def async_step_contract_preview(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if self._pending_schedule is None or self._pending_event is None:
            return await self.async_step_assignments()
        if user_input is not None and bool(user_input.get("confirm")):
            current_schedule = self._schedule
            if self._pending_original_revision != _schedule_revision(current_schedule):
                pending = self._pending_schedule
                self._pending_schedule = None
                self._pending_event = None
                self._pending_original_schedule_json = None
                self._pending_original_revision = None
                return self.async_show_form(
                    step_id="contract_preview",
                    data_schema=vol.Schema(
                        {vol.Required("confirm", default=False): selector.BooleanSelector()}
                    ),
                    errors={"base": "stale_contract_preview"},
                    description_placeholders={
                        "before": _schedule_summary(current_schedule),
                        "after": _schedule_summary(pending),
                        "gaps": _schedule_gap_summary(current_schedule, pending),
                    },
                )
            return self._save_schedule(
                self._pending_schedule,
                event_type=str(self._pending_event["event_type"]),
                affected=self._pending_event["affected"],
                old_schedule_json=self._pending_original_schedule_json,
            )
        return self.async_show_form(
            step_id="contract_preview",
            data_schema=vol.Schema(
                {vol.Required("confirm", default=False): selector.BooleanSelector()}
            ),
            description_placeholders={
                "before": _schedule_summary(self._schedule),
                "after": _schedule_summary(self._pending_schedule),
                "gaps": _schedule_gap_summary(self._schedule, self._pending_schedule),
            },
        )

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        mode = str(self._current.get(CONF_SOURCE_MODE, SOURCE_SIGNED_POWER))
        options = [
            "data_publishing",
            "restore_publishing_defaults",
            "assignments",
            "add_assignment",
            "archive_removal",
        ]
        if mode in SOURCE_MODES:
            options.insert(0, "settings")
        else:
            options.insert(0, "legacy_mode_d")
        return self.async_show_menu(step_id="init", menu_options=options)

    async def async_step_data_publishing(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure HA publication independently from one-second calculation."""

        current = self._current
        if user_input is not None:
            self._pending_publishing = {
                CONF_PUBLISHING_PROFILE: str(user_input[CONF_PUBLISHING_PROFILE]),
                CONF_PUBLISHING_ROUTINE_INTERVAL_SECONDS: int(
                    user_input[CONF_PUBLISHING_ROUTINE_INTERVAL_SECONDS]
                ),
                CONF_PUBLISHING_ACTIONABLE_INTERVAL_SECONDS: int(
                    user_input[CONF_PUBLISHING_ACTIONABLE_INTERVAL_SECONDS]
                ),
                CONF_PUBLISHING_POWER_DEADBAND_KW: float(
                    user_input[CONF_PUBLISHING_POWER_DEADBAND_KW]
                ),
                CONF_PUBLISHING_ENERGY_DEADBAND_KWH: float(
                    user_input[CONF_PUBLISHING_ENERGY_DEADBAND_KWH]
                ),
                CONF_PUBLISHING_FAST_ENTITIES: list(
                    user_input.get(CONF_PUBLISHING_FAST_ENTITIES, [])
                ),
            }
            return await self.async_step_publishing_preview()
        return self.async_show_form(
            step_id="data_publishing",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PUBLISHING_PROFILE,
                        default=str(
                            current.get(CONF_PUBLISHING_PROFILE, DEFAULT_PUBLISHING_PROFILE)
                        ),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(PUBLISHING_PROFILES),
                            translation_key="publishing_profile",
                        )
                    ),
                    vol.Required(
                        CONF_PUBLISHING_ROUTINE_INTERVAL_SECONDS,
                        default=str(
                            current.get(
                                CONF_PUBLISHING_ROUTINE_INTERVAL_SECONDS,
                                DEFAULT_PUBLISHING_ROUTINE_INTERVAL_SECONDS,
                            )
                        ),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[str(value) for value in PUBLISHING_INTERVAL_PRESETS]
                        )
                    ),
                    vol.Required(
                        CONF_PUBLISHING_ACTIONABLE_INTERVAL_SECONDS,
                        default=str(
                            current.get(
                                CONF_PUBLISHING_ACTIONABLE_INTERVAL_SECONDS,
                                DEFAULT_PUBLISHING_ACTIONABLE_INTERVAL_SECONDS,
                            )
                        ),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[str(value) for value in PUBLISHING_INTERVAL_PRESETS]
                        )
                    ),
                    vol.Required(
                        CONF_PUBLISHING_POWER_DEADBAND_KW,
                        default=float(
                            current.get(
                                CONF_PUBLISHING_POWER_DEADBAND_KW,
                                DEFAULT_PUBLISHING_POWER_DEADBAND_KW,
                            )
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.0, max=10.0, step=0.001, unit_of_measurement="kW"
                        )
                    ),
                    vol.Required(
                        CONF_PUBLISHING_ENERGY_DEADBAND_KWH,
                        default=float(
                            current.get(
                                CONF_PUBLISHING_ENERGY_DEADBAND_KWH,
                                DEFAULT_PUBLISHING_ENERGY_DEADBAND_KWH,
                            )
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.0, max=10.0, step=0.001, unit_of_measurement="kWh"
                        )
                    ),
                    vol.Optional(
                        CONF_PUBLISHING_FAST_ENTITIES,
                        default=list(current.get(CONF_PUBLISHING_FAST_ENTITIES, [])),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(PUBLISHING_FAST_ENTITY_OPTIONS), multiple=True
                        )
                    ),
                }
            ),
        )

    async def async_step_publishing_preview(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show an explicit planning estimate before saving publication settings."""

        if self._pending_publishing is None:
            return await self.async_step_data_publishing()
        estimate = projected_profile_bytes_per_year(
            profile=str(self._pending_publishing[CONF_PUBLISHING_PROFILE]), meter_count=2
        )
        if user_input is not None and bool(user_input.get("confirm")):
            pending = self._pending_publishing
            self._pending_publishing = None
            return self._save(pending)
        return self.async_show_form(
            step_id="publishing_preview",
            data_schema=vol.Schema(
                {vol.Required("confirm", default=False): selector.BooleanSelector()}
            ),
            description_placeholders={
                "profile": str(self._pending_publishing[CONF_PUBLISHING_PROFILE]),
                "annual_mb": f"{estimate / 1_000_000:.1f}",
                "budget_pct": f"{estimate / STORAGE_BUDGET_BYTES_PER_YEAR * 100:.1f}",
            },
        )

    async def async_step_restore_publishing_defaults(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Restore the storage-safe profile without touching calculations or archives."""

        return self._save(
            {
                CONF_PUBLISHING_PROFILE: DEFAULT_PUBLISHING_PROFILE,
                CONF_PUBLISHING_ROUTINE_INTERVAL_SECONDS: (
                    DEFAULT_PUBLISHING_ROUTINE_INTERVAL_SECONDS
                ),
                CONF_PUBLISHING_ACTIONABLE_INTERVAL_SECONDS: (
                    DEFAULT_PUBLISHING_ACTIONABLE_INTERVAL_SECONDS
                ),
                CONF_PUBLISHING_POWER_DEADBAND_KW: DEFAULT_PUBLISHING_POWER_DEADBAND_KW,
                CONF_PUBLISHING_ENERGY_DEADBAND_KWH: DEFAULT_PUBLISHING_ENERGY_DEADBAND_KWH,
                CONF_PUBLISHING_FAST_ENTITIES: [],
            }
        )

    async def async_step_legacy_mode_d(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Explain the safe V1.0 path without changing legacy counter settings."""

        return self.async_show_form(
            step_id="legacy_mode_d",
            data_schema=vol.Schema({}),
            description_placeholders={"meter": self.config_entry.title},
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
            raise ValueError("legacy cumulative-energy entries must be explicitly reconfigured")
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_METER_NAME,
                        default=str(current.get(CONF_METER_NAME) or self.config_entry.title),
                    ): selector.TextSelector(),
                    vol.Required(
                        CONF_PREFERRED_LANGUAGE,
                        default=str(
                            current.get(CONF_PREFERRED_LANGUAGE, DEFAULT_PREFERRED_LANGUAGE)
                        ),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(SUPPORTED_LANGUAGES),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="preferred_language",
                        )
                    ),
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
            if operation == "schedule":
                return await self.async_step_schedule_change()
            if operation == "correct":
                return await self.async_step_correct_assignment()
            return await self.async_step_edit_assignment()
        options = []
        for index, period in enumerate(self._schedule.periods):
            today = _local_today()
            status = (
                "active"
                if period.effective_from <= today <= period.effective_to
                else "expired"
                if period.effective_to < today
                else "future"
            )
            label = (
                f"{status.upper()} · {period.effective_from} - {period.effective_to} · "
                + "/".join(f"{target:.3f}" for target in period.block_targets_kw)
                + " kW"
            )
            options.extend(
                (
                    {"value": f"edit:{index}", "label": f"Edit details · {label}"},
                    {"value": f"schedule:{index}", "label": f"Schedule change · {label}"},
                    {"value": f"correct:{index}", "label": f"Correct assignment · {label}"},
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
        if self._selected_index is None:
            return await self.async_step_assignments()
        existing = self._schedule.periods[self._selected_index]
        if user_input is not None:
            if CONF_ASSIGNMENT_START_DATE in user_input:
                # Compatibility for an in-progress V1.0.1 flow restored across
                # upgrade. New menus route full corrections to the explicit step.
                return await self._assignment_form(
                    "correct_assignment", user_input, event_type="CORRECTED"
                )
            recorded = user_input.get(CONF_ASSIGNMENT_RECORDED_ON)
            replacement = ContractedPowerPeriod(
                existing.effective_from,
                existing.effective_to,
                existing.block_targets_kw,
                str(user_input.get(CONF_ASSIGNMENT_PROVENANCE) or "user_configured"),
                _as_date(recorded) if recorded else None,
            )
            periods = list(self._schedule.periods)
            periods[self._selected_index] = replacement
            return self._preview(
                ContractedPowerSchedule(tuple(periods)),
                event_type="CORRECTED",
                affected=replacement,
            )
        recorded_key: Any = (
            vol.Optional(CONF_ASSIGNMENT_RECORDED_ON, default=existing.recorded_on)
            if existing.recorded_on is not None
            else vol.Optional(CONF_ASSIGNMENT_RECORDED_ON)
        )
        return self.async_show_form(
            step_id="edit_assignment",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ASSIGNMENT_PROVENANCE, default=existing.provenance
                    ): selector.TextSelector(),
                    recorded_key: selector.DateSelector(),
                }
            ),
        )

    async def async_step_correct_assignment(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return await self._assignment_form("correct_assignment", user_input, event_type="CORRECTED")

    async def async_step_schedule_change(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if self._selected_index is None:
            return await self.async_step_assignments()
        existing = self._schedule.periods[self._selected_index]
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                start = _as_date(user_input[CONF_ASSIGNMENT_START_DATE])
                raw_end = user_input.get(CONF_ASSIGNMENT_CHANGE_END_DATE)
                end = _as_date(raw_end) if raw_end else existing.effective_to
                replacement = ContractedPowerPeriod(
                    start,
                    end,
                    tuple(float(user_input[key]) for key in TARGET_KEYS),  # type: ignore[arg-type]
                    str(user_input.get(CONF_ASSIGNMENT_PROVENANCE) or "user_configured"),
                    (
                        _as_date(user_input[CONF_ASSIGNMENT_RECORDED_ON])
                        if user_input.get(CONF_ASSIGNMENT_RECORDED_ON)
                        else None
                    ),
                )
                schedule = self._schedule.schedule_change(self._selected_index, replacement)
            except (KeyError, TypeError, ValueError):
                errors["base"] = "invalid_scheduled_contract_change"
            else:
                return self._preview(schedule, event_type="SCHEDULED_CHANGE", affected=replacement)
        values: dict[Any, Any] = {
            vol.Required(
                CONF_ASSIGNMENT_START_DATE, default=existing.effective_from
            ): selector.DateSelector(),
            vol.Optional(CONF_ASSIGNMENT_CHANGE_END_DATE): selector.DateSelector(),
            vol.Optional(CONF_ASSIGNMENT_RECORDED_ON): selector.DateSelector(),
            vol.Required(
                CONF_ASSIGNMENT_PROVENANCE, default="user_configured"
            ): selector.TextSelector(),
        }
        for key, target in zip(TARGET_KEYS, existing.block_targets_kw, strict=True):
            field, field_selector = _number_field(key, target)
            values[field] = field_selector
        return self.async_show_form(
            step_id="schedule_change", data_schema=vol.Schema(values), errors=errors
        )

    async def _assignment_form(
        self,
        step_id: str,
        user_input: dict[str, Any] | None,
        *,
        event_type: str = "CREATED",
    ) -> FlowResult:
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        periods = list(self._schedule.periods)
        existing = periods[self._selected_index] if self._selected_index is not None else None
        if user_input is not None:
            try:
                replacement = _period_from_input(user_input)
                conflict = self._schedule.conflict_for(
                    replacement, exclude_index=self._selected_index
                )
                if conflict is not None:
                    placeholders["conflict"] = (
                        f"{conflict.effective_from.strftime('%d.%m.%Y')} to "
                        f"{conflict.effective_to.strftime('%d.%m.%Y')}"
                    )
                    raise ValueError("overlap")
                if self._selected_index is None:
                    periods.append(replacement)
                else:
                    periods[self._selected_index] = replacement
                schedule = ContractedPowerSchedule(tuple(periods))
            except ValueError as err:
                errors["base"] = (
                    "overlapping_contracted_power_period"
                    if str(err) == "overlap"
                    else "invalid_contracted_power_periods"
                )
            else:
                return self._preview(schedule, event_type=event_type, affected=replacement)
        return self.async_show_form(
            step_id=step_id,
            data_schema=_period_schema(existing),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_remove_assignment(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if self._selected_index is None:
            return await self.async_step_assignments()
        if user_input is not None and user_input["confirm"]:
            periods = list(self._schedule.periods)
            removed = periods.pop(self._selected_index)
            return self._preview(
                ContractedPowerSchedule(tuple(periods)),
                event_type="REMOVED_FROM_ACTIVE_SCHEDULE",
                affected=removed,
            )
        return self.async_show_form(
            step_id="remove_assignment",
            data_schema=vol.Schema(
                {vol.Required("confirm", default=False): selector.BooleanSelector()}
            ),
        )
