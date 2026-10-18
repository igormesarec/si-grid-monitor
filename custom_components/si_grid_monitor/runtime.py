"""Home Assistant runtime bridge for the pure calculation engine."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util import dt as dt_util

from .adapters import AdapterError, SignedPowerAdapter
from .const import (
    CONF_POSITIVE_MEANS_IMPORT,
    CONF_POWER_ENTITY,
    CONF_SAFETY_MARGIN_KW,
    CONF_SMOOTHING_SECONDS,
    CONF_TARGET_KW,
    DEFAULT_SAFETY_MARGIN_KW,
    DEFAULT_SMOOTHING_SECONDS,
    DEFAULT_STALE_AFTER_SECONDS,
)
from .engine import CalculationError, EngineSnapshot, FixedQuarterEngine, PowerSample

_LOGGER = logging.getLogger(__name__)


class GridMonitorRuntime:
    """Translate HA state changes into normalized engine samples."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.power_entity = str(entry.data[CONF_POWER_ENTITY])
        self.adapter = SignedPowerAdapter(
            positive_means_import=bool(entry.data[CONF_POSITIVE_MEANS_IMPORT])
        )
        self.engine = FixedQuarterEngine(
            stale_after_seconds=DEFAULT_STALE_AFTER_SECONDS,
            source_id=self.power_entity,
        )
        self.snapshot: EngineSnapshot | None = None
        self._listeners: set[Callable[[], None]] = set()
        self._unsubscribers: list[Callable[[], None]] = []

    @property
    def settings(self) -> dict[str, float | int]:
        """Return effective editable settings."""

        data = {**self.entry.data, **self.entry.options}
        return {
            CONF_TARGET_KW: float(data[CONF_TARGET_KW]),
            CONF_SAFETY_MARGIN_KW: float(
                data.get(CONF_SAFETY_MARGIN_KW, DEFAULT_SAFETY_MARGIN_KW)
            ),
            CONF_SMOOTHING_SECONDS: int(
                data.get(CONF_SMOOTHING_SECONDS, DEFAULT_SMOOTHING_SECONDS)
            ),
        }

    async def async_start(self) -> None:
        """Read the current state and register state/timer listeners."""

        current = self.hass.states.get(self.power_entity)
        if current is not None:
            self._ingest_state(current)

        self._unsubscribers.append(
            async_track_state_change_event(
                self.hass, [self.power_entity], self._async_state_changed
            )
        )
        self._unsubscribers.append(
            async_track_time_interval(
                self.hass, self._async_tick, timedelta(seconds=1)
            )
        )

    @callback
    def async_stop(self) -> None:
        """Remove runtime listeners."""

        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        self._listeners.clear()

    @callback
    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register an entity state listener."""

        self._listeners.add(listener)

        @callback
        def remove() -> None:
            self._listeners.discard(listener)

        return remove

    @callback
    def _async_state_changed(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        if isinstance(new_state, State):
            self._ingest_state(new_state)

    @callback
    def _async_tick(self, now) -> None:
        self._refresh(now)

    @callback
    def _ingest_state(self, state: State) -> None:
        if state.state in {"unknown", "unavailable", "none", ""}:
            return
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        if not isinstance(unit, str):
            _LOGGER.warning("Power source %s has no W/kW unit", self.power_entity)
            return
        try:
            normalized = self.adapter.normalize(state.state, unit)
            timestamp = state.last_reported or state.last_updated
            self.engine.ingest(PowerSample(timestamp, normalized.signed_kw))
        except (AdapterError, CalculationError) as err:
            _LOGGER.warning("Rejected power sample from %s: %s", self.power_entity, err)
            return
        self._refresh(dt_util.utcnow())

    @callback
    def _refresh(self, now) -> None:
        if self.engine.last_sample is None:
            return
        settings = self.settings
        try:
            self.snapshot = self.engine.snapshot(
                now=now,
                target_kw=float(settings[CONF_TARGET_KW]),
                safety_margin_kw=float(settings[CONF_SAFETY_MARGIN_KW]),
                smoothing_seconds=int(settings[CONF_SMOOTHING_SECONDS]),
            )
        except CalculationError as err:
            _LOGGER.warning("Could not refresh SI Grid Monitor: %s", err)
            return
        for listener in tuple(self._listeners):
            listener()
