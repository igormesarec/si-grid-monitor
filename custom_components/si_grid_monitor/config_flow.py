"""Configuration flow for SI Grid Monitor."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_POSITIVE_MEANS_IMPORT,
    CONF_POWER_ENTITY,
    CONF_SAFETY_MARGIN_KW,
    CONF_SMOOTHING_SECONDS,
    CONF_SOURCE_MODE,
    CONF_TARGET_KW,
    DEFAULT_SAFETY_MARGIN_KW,
    DEFAULT_SMOOTHING_SECONDS,
    DOMAIN,
    MAX_SMOOTHING_SECONDS,
    MIN_SMOOTHING_SECONDS,
    SOURCE_ALIGNED_QUARTER,
    SOURCE_CUMULATIVE_ENERGY,
    SOURCE_IMPORT_ONLY,
    SOURCE_SEPARATE_POWER,
    SOURCE_SIGNED_POWER,
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

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select a source design; V0.1 activates signed live power only."""

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

    async def async_step_signed_power(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure one signed live grid-power entity."""

        if user_input is not None:
            entity_id = user_input[CONF_POWER_ENTITY]
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
                    ): _number_selector(
                        minimum=0.0, maximum=1000.0, step=0.01, unit="kW"
                    ),
                    vol.Required(
                        CONF_SMOOTHING_SECONDS,
                        default=DEFAULT_SMOOTHING_SECONDS,
                    ): _number_selector(
                        minimum=MIN_SMOOTHING_SECONDS,
                        maximum=MAX_SMOOTHING_SECONDS,
                        step=1.0,
                        unit="s",
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
    """Edit V0.1 calculation settings."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage calculation options."""

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TARGET_KW, default=current[CONF_TARGET_KW]
                    ): _number_selector(
                        minimum=0.0, maximum=1000.0, step=0.01, unit="kW"
                    ),
                    vol.Required(
                        CONF_SAFETY_MARGIN_KW,
                        default=current.get(
                            CONF_SAFETY_MARGIN_KW, DEFAULT_SAFETY_MARGIN_KW
                        ),
                    ): _number_selector(
                        minimum=0.0, maximum=1000.0, step=0.01, unit="kW"
                    ),
                    vol.Required(
                        CONF_SMOOTHING_SECONDS,
                        default=current.get(
                            CONF_SMOOTHING_SECONDS, DEFAULT_SMOOTHING_SECONDS
                        ),
                    ): _number_selector(
                        minimum=MIN_SMOOTHING_SECONDS,
                        maximum=MAX_SMOOTHING_SECONDS,
                        step=1.0,
                        unit="s",
                    ),
                }
            ),
        )
