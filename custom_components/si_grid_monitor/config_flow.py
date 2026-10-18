"""Configuration flow for SI Grid Monitor."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_ALLOW_PROVISIONAL_TARIFF,
    CONF_POSITIVE_MEANS_IMPORT,
    CONF_POWER_ENTITY,
    CONF_RETENTION,
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
    CONF_TARGET_MODE,
    DEFAULT_RETENTION,
    DEFAULT_SAFETY_MARGIN_KW,
    DEFAULT_SMOOTHING_SECONDS,
    DEFAULT_SUSTAINED_HORIZON_MINUTES,
    DOMAIN,
    SMOOTHING_PRESETS,
    SOURCE_ALIGNED_QUARTER,
    SOURCE_CUMULATIVE_ENERGY,
    SOURCE_IMPORT_ONLY,
    SOURCE_SEPARATE_POWER,
    SOURCE_SIGNED_POWER,
    SUSTAINED_HORIZON_PRESETS,
    TARGET_MODE_PER_BLOCK,
    TARGET_MODE_SHARED,
)

SOURCE_MODES = (
    SOURCE_SIGNED_POWER,
    SOURCE_SEPARATE_POWER,
    SOURCE_IMPORT_ONLY,
    SOURCE_CUMULATIVE_ENERGY,
    SOURCE_ALIGNED_QUARTER,
)


def _number_selector(
    *, minimum: float, maximum: float, step: float, unit: str
) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement=unit,
        )
    )


class SIGridMonitorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the SI Grid Monitor setup flow."""

    VERSION = 3
    MINOR_VERSION = 0

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Select a source design; V0.3 activates signed live power only."""

        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_SOURCE_MODE] == SOURCE_SIGNED_POWER:
                return await self.async_step_signed_power()
            errors["base"] = "mode_not_available_v0_1"

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SOURCE_MODE, default=SOURCE_SIGNED_POWER
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=list(SOURCE_MODES),
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="source_mode",
                    )
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_signed_power(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Configure one signed live grid-power entity."""

        if user_input is not None:
            user_input[CONF_SMOOTHING_SECONDS] = int(user_input[CONF_SMOOTHING_SECONDS])
            user_input[CONF_SUSTAINED_HORIZON_MINUTES] = int(
                user_input[CONF_SUSTAINED_HORIZON_MINUTES]
            )
            entity_id = user_input[CONF_POWER_ENTITY]
            target = float(user_input[CONF_TARGET_KW])
            user_input.update(
                {
                    CONF_TARGET_MODE: TARGET_MODE_SHARED,
                    CONF_TARGET_B1_KW: target,
                    CONF_TARGET_B2_KW: target,
                    CONF_TARGET_B3_KW: target,
                    CONF_TARGET_B4_KW: target,
                    CONF_TARGET_B5_KW: target,
                    CONF_ALLOW_PROVISIONAL_TARIFF: False,
                }
            )
            await self.async_set_unique_id(f"signed:{entity_id}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"SI Grid Monitor ({entity_id})",
                data={CONF_SOURCE_MODE: SOURCE_SIGNED_POWER, **user_input},
            )

        return self.async_show_form(
            step_id="signed_power",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_POWER_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor")
                    ),
                    vol.Required(
                        CONF_POSITIVE_MEANS_IMPORT, default=True
                    ): selector.BooleanSelector(),
                    vol.Required(CONF_TARGET_KW): _number_selector(
                        minimum=0.0, maximum=1000.0, step=0.01, unit="kW"
                    ),
                    vol.Required(
                        CONF_SAFETY_MARGIN_KW,
                        default=DEFAULT_SAFETY_MARGIN_KW,
                    ): _number_selector(minimum=0.0, maximum=1000.0, step=0.01, unit="kW"),
                    vol.Required(
                        CONF_SMOOTHING_SECONDS,
                        default=DEFAULT_SMOOTHING_SECONDS,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[str(value) for value in SMOOTHING_PRESETS],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(
                        CONF_RETENTION, default=DEFAULT_RETENTION
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=[DEFAULT_RETENTION])
                    ),
                    vol.Required(
                        CONF_SUSTAINED_HORIZON_MINUTES,
                        default=DEFAULT_SUSTAINED_HORIZON_MINUTES,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[str(value) for value in SUSTAINED_HORIZON_PRESETS],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow."""

        return SIGridMonitorOptionsFlow()


class SIGridMonitorOptionsFlow(config_entries.OptionsFlow):
    """Edit calculation and tariff settings."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage calculation options."""

        if user_input is not None:
            user_input[CONF_SMOOTHING_SECONDS] = int(user_input[CONF_SMOOTHING_SECONDS])
            user_input[CONF_SUSTAINED_HORIZON_MINUTES] = int(
                user_input[CONF_SUSTAINED_HORIZON_MINUTES]
            )
            if user_input[CONF_TARGET_MODE] == TARGET_MODE_SHARED:
                shared = float(user_input[CONF_TARGET_KW])
                for key in (
                    CONF_TARGET_B1_KW,
                    CONF_TARGET_B2_KW,
                    CONF_TARGET_B3_KW,
                    CONF_TARGET_B4_KW,
                    CONF_TARGET_B5_KW,
                ):
                    user_input[key] = shared
            return self.async_create_entry(title="", data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        current_smoothing = int(current.get(CONF_SMOOTHING_SECONDS, DEFAULT_SMOOTHING_SECONDS))
        legacy_target = float(current[CONF_TARGET_KW])
        smoothing_options = list(SMOOTHING_PRESETS)
        if current_smoothing not in smoothing_options:
            smoothing_options.append(current_smoothing)
            smoothing_options.sort()
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POWER_ENTITY, default=current[CONF_POWER_ENTITY]
                    ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                    vol.Required(
                        CONF_POSITIVE_MEANS_IMPORT,
                        default=current[CONF_POSITIVE_MEANS_IMPORT],
                    ): selector.BooleanSelector(),
                    vol.Required(CONF_TARGET_KW, default=current[CONF_TARGET_KW]): _number_selector(
                        minimum=0.0, maximum=1000.0, step=0.01, unit="kW"
                    ),
                    vol.Required(
                        CONF_TARGET_MODE,
                        default=current.get(CONF_TARGET_MODE, TARGET_MODE_SHARED),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[TARGET_MODE_SHARED, TARGET_MODE_PER_BLOCK],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="target_mode",
                        )
                    ),
                    vol.Required(
                        CONF_TARGET_B1_KW,
                        default=current.get(CONF_TARGET_B1_KW, legacy_target),
                    ): _number_selector(minimum=0.0, maximum=1000.0, step=0.01, unit="kW"),
                    vol.Required(
                        CONF_TARGET_B2_KW,
                        default=current.get(CONF_TARGET_B2_KW, legacy_target),
                    ): _number_selector(minimum=0.0, maximum=1000.0, step=0.01, unit="kW"),
                    vol.Required(
                        CONF_TARGET_B3_KW,
                        default=current.get(CONF_TARGET_B3_KW, legacy_target),
                    ): _number_selector(minimum=0.0, maximum=1000.0, step=0.01, unit="kW"),
                    vol.Required(
                        CONF_TARGET_B4_KW,
                        default=current.get(CONF_TARGET_B4_KW, legacy_target),
                    ): _number_selector(minimum=0.0, maximum=1000.0, step=0.01, unit="kW"),
                    vol.Required(
                        CONF_TARGET_B5_KW,
                        default=current.get(CONF_TARGET_B5_KW, legacy_target),
                    ): _number_selector(minimum=0.0, maximum=1000.0, step=0.01, unit="kW"),
                    vol.Required(
                        CONF_ALLOW_PROVISIONAL_TARIFF,
                        default=current.get(CONF_ALLOW_PROVISIONAL_TARIFF, False),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_SAFETY_MARGIN_KW,
                        default=current.get(CONF_SAFETY_MARGIN_KW, DEFAULT_SAFETY_MARGIN_KW),
                    ): _number_selector(minimum=0.0, maximum=1000.0, step=0.01, unit="kW"),
                    vol.Required(
                        CONF_SMOOTHING_SECONDS,
                        default=str(current_smoothing),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[str(value) for value in smoothing_options],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(
                        CONF_RETENTION,
                        default=current.get(CONF_RETENTION, DEFAULT_RETENTION),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=[DEFAULT_RETENTION])
                    ),
                    vol.Required(
                        CONF_SUSTAINED_HORIZON_MINUTES,
                        default=current.get(
                            CONF_SUSTAINED_HORIZON_MINUTES,
                            DEFAULT_SUSTAINED_HORIZON_MINUTES,
                        ),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[str(value) for value in SUSTAINED_HORIZON_PRESETS],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(
                        CONF_SIMULATION_ENABLED,
                        default=current.get(CONF_SIMULATION_ENABLED, False),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_SIMULATION_TARGET_KW,
                        default=current.get(CONF_SIMULATION_TARGET_KW, current[CONF_TARGET_KW]),
                    ): _number_selector(minimum=0.0, maximum=1000.0, step=0.01, unit="kW"),
                }
            ),
        )
