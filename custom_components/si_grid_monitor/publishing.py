"""Centralized Home Assistant entity publishing control.

The calculation engine remains one-second and authoritative.  This module only
decides when an HA entity should expose a new state, which protects Recorder and
external state consumers such as InfluxDB from calculation-rate event streams.
"""

from __future__ import annotations

import json
from collections import Counter, deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from .const import (
    CONF_PUBLISHING_ACTIONABLE_INTERVAL_SECONDS,
    CONF_PUBLISHING_ENERGY_DEADBAND_KWH,
    CONF_PUBLISHING_FAST_ENTITIES,
    CONF_PUBLISHING_POWER_DEADBAND_KW,
    CONF_PUBLISHING_PROFILE,
    CONF_PUBLISHING_ROUTINE_INTERVAL_SECONDS,
    DEFAULT_PUBLISHING_ACTIONABLE_INTERVAL_SECONDS,
    DEFAULT_PUBLISHING_ENERGY_DEADBAND_KWH,
    DEFAULT_PUBLISHING_POWER_DEADBAND_KW,
    DEFAULT_PUBLISHING_PROFILE,
    DEFAULT_PUBLISHING_ROUTINE_INTERVAL_SECONDS,
    PUBLISHING_PROFILE_AUTOMATION,
    PUBLISHING_PROFILE_CUSTOM,
)

STORAGE_BUDGET_BYTES_PER_YEAR = 1_000_000_000
SECONDS_PER_YEAR = 365 * 24 * 60 * 60


class PublishingClass(StrEnum):
    """Entity publication category."""

    CRITICAL = "critical"
    ACTIONABLE = "actionable"
    MONITORING = "monitoring"
    CONFIGURATION = "configuration"
    DIAGNOSTIC = "diagnostic"


@dataclass(frozen=True, slots=True)
class PublicationState:
    """Minimal entity state used for publication decisions."""

    value: Any
    available: bool
    attributes: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class PublishingSettings:
    """Effective per-meter publishing settings."""

    profile: str
    routine_interval_seconds: int
    actionable_interval_seconds: int
    power_deadband_kw: float
    energy_deadband_kwh: float
    fast_entities: frozenset[str]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> PublishingSettings:
        profile = str(data.get(CONF_PUBLISHING_PROFILE, DEFAULT_PUBLISHING_PROFILE))
        if profile == PUBLISHING_PROFILE_AUTOMATION:
            routine = 60
            actionable = 15
            power_deadband = 0.025
            energy_deadband = 0.002
        else:
            routine = int(
                data.get(
                    CONF_PUBLISHING_ROUTINE_INTERVAL_SECONDS,
                    DEFAULT_PUBLISHING_ROUTINE_INTERVAL_SECONDS,
                )
            )
            actionable = int(
                data.get(
                    CONF_PUBLISHING_ACTIONABLE_INTERVAL_SECONDS,
                    DEFAULT_PUBLISHING_ACTIONABLE_INTERVAL_SECONDS,
                )
            )
            power_deadband = float(
                data.get(
                    CONF_PUBLISHING_POWER_DEADBAND_KW,
                    DEFAULT_PUBLISHING_POWER_DEADBAND_KW,
                )
            )
            energy_deadband = float(
                data.get(
                    CONF_PUBLISHING_ENERGY_DEADBAND_KWH,
                    DEFAULT_PUBLISHING_ENERGY_DEADBAND_KWH,
                )
            )
        fast_raw = data.get(CONF_PUBLISHING_FAST_ENTITIES, ())
        if isinstance(fast_raw, str):
            fast = frozenset(item.strip() for item in fast_raw.split(",") if item.strip())
        else:
            fast = frozenset(str(item) for item in (fast_raw or ()))
        if profile != PUBLISHING_PROFILE_CUSTOM:
            # Automation Priority may still explicitly name threshold-critical
            # values. Storage Optimized intentionally has no default fast list.
            fast = fast if profile == PUBLISHING_PROFILE_AUTOMATION else frozenset()
        return cls(
            profile=profile,
            routine_interval_seconds=max(15, routine),
            actionable_interval_seconds=max(1, actionable),
            power_deadband_kw=max(0.0, power_deadband),
            energy_deadband_kwh=max(0.0, energy_deadband),
            fast_entities=fast,
        )


@dataclass(slots=True)
class _Registration:
    key: str
    publishing_class: PublishingClass
    reader: Callable[[], PublicationState]
    callback: Callable[[], None]
    last_state: PublicationState | None = None
    last_fingerprint: str | None = None
    last_attributes_fingerprint: str | None = None
    last_published_utc: datetime | None = None


@dataclass(frozen=True, slots=True)
class _PublicationEvent:
    timestamp_utc: datetime
    key: str
    payload_bytes: int
    critical: bool


class PublishingController:
    """Coalesce calculation-rate updates into meaningful HA publications."""

    def __init__(self, settings: PublishingSettings) -> None:
        self.settings = settings
        self._registrations: dict[str, _Registration] = {}
        self._events: deque[_PublicationEvent] = deque(maxlen=50_000)
        self.started_utc = datetime.now(UTC)
        self.calculation_cycles = 0
        self.publications = 0
        self.suppressed_unchanged = 0
        self.suppressed_policy = 0
        self.suppressed_attribute_only = 0
        self.critical_publications = 0

    def register(
        self,
        key: str,
        publishing_class: PublishingClass,
        reader: Callable[[], PublicationState],
        callback: Callable[[], None],
    ) -> Callable[[], None]:
        """Register exactly one entity callback and return its remover."""

        self._registrations[key] = _Registration(key, publishing_class, reader, callback)

        def remove() -> None:
            registration = self._registrations.get(key)
            if registration is not None and registration.callback is callback:
                self._registrations.pop(key, None)

        return remove

    def clear(self) -> None:
        """Release entity references during runtime shutdown."""

        self._registrations.clear()

    def process(self, now_utc: datetime) -> None:
        """Evaluate all policies after one internal calculation cycle."""

        now_utc = now_utc.astimezone(UTC)
        self.calculation_cycles += 1
        for registration in tuple(self._registrations.values()):
            state = registration.reader()
            fingerprint, attributes_fingerprint, payload_bytes = _fingerprint(state)
            should_publish, critical = self._should_publish(
                registration, state, fingerprint, now_utc
            )
            if not should_publish:
                continue
            registration.callback()
            registration.last_state = state
            registration.last_fingerprint = fingerprint
            registration.last_attributes_fingerprint = attributes_fingerprint
            registration.last_published_utc = now_utc
            self.publications += 1
            self.critical_publications += int(critical)
            self._events.append(
                _PublicationEvent(now_utc, registration.key, payload_bytes, critical)
            )
        self._discard_old_events(now_utc)

    def _should_publish(
        self,
        registration: _Registration,
        state: PublicationState,
        fingerprint: str,
        now_utc: datetime,
    ) -> tuple[bool, bool]:
        previous = registration.last_state
        if previous is None or registration.last_published_utc is None:
            return True, registration.publishing_class == PublishingClass.CRITICAL
        if fingerprint == registration.last_fingerprint:
            self.suppressed_unchanged += 1
            return False, False
        if state.available != previous.available:
            return True, True
        changed_value = state.value != previous.value
        attributes_changed = (
            _attributes_fingerprint(state.attributes) != registration.last_attributes_fingerprint
        )
        if registration.publishing_class == PublishingClass.CRITICAL and changed_value:
            # A critical value/availability transition is never delayed.  An
            # attribute-only diagnostic change is coalesced below so it cannot
            # accidentally recreate a one-second event stream.
            return True, True
        if registration.publishing_class == PublishingClass.CONFIGURATION:
            return True, False
        if registration.key in self.settings.fast_entities and changed_value:
            return True, False
        if _zero_transition(previous.value, state.value):
            return True, registration.publishing_class == PublishingClass.ACTIONABLE
        elapsed = (now_utc - registration.last_published_utc).total_seconds()
        interval = self._interval_for(registration.publishing_class)
        if elapsed < interval:
            self.suppressed_policy += 1
            if attributes_changed and not changed_value:
                self.suppressed_attribute_only += 1
            return False, False
        if changed_value and _meaningful_delta(
            previous.value,
            state.value,
            registration.key,
            self.settings.power_deadband_kw,
            self.settings.energy_deadband_kwh,
        ):
            return True, False
        # Attribute changes are allowed only at the class interval. Stable
        # attributes therefore never create a heartbeat, while changed quality
        # or forecast metadata eventually remains visible.
        attributes_fingerprint = _attributes_fingerprint(state.attributes)
        if registration.last_attributes_fingerprint != attributes_fingerprint:
            return True, False
        self.suppressed_unchanged += 1
        return False, False

    def _interval_for(self, publishing_class: PublishingClass) -> int:
        if publishing_class == PublishingClass.ACTIONABLE:
            return self.settings.actionable_interval_seconds
        if publishing_class == PublishingClass.DIAGNOSTIC:
            return max(300, self.settings.routine_interval_seconds)
        return self.settings.routine_interval_seconds

    def diagnostics(self, now_utc: datetime, window_seconds: int = 3600) -> dict[str, Any]:
        """Return bounded publication counters without querying Recorder."""

        now_utc = now_utc.astimezone(UTC)
        self._discard_old_events(now_utc)
        cutoff = now_utc - timedelta(seconds=max(60, window_seconds))
        events = [event for event in self._events if event.timestamp_utc >= cutoff]
        observed_seconds = max(
            1.0,
            min(
                float(window_seconds),
                (now_utc - self.started_utc).total_seconds(),
            ),
        )
        payload = sum(event.payload_bytes for event in events)
        event_count = len(events)
        annual_factor = SECONDS_PER_YEAR / observed_seconds
        # Recorder estimate includes a conservative row/index allowance; the
        # Influx estimate represents state/field/series protocol overhead. The
        # dashboard labels both as estimates rather than physical allocation.
        annual_payload = payload * annual_factor
        recorder_bytes = annual_payload + event_count * 240 * annual_factor
        influx_bytes = event_count * 140 * annual_factor
        archive_bytes = 40_000_000  # dense schema-7 quarter/audit allowance per meter/year
        annual_total = int(recorder_bytes + influx_bytes + archive_bytes)
        top = Counter(event.key for event in events).most_common(10)
        return {
            "profile": self.settings.profile,
            "window_seconds": window_seconds,
            "calculation_cycles": self.calculation_cycles,
            "calculation_cycles_per_minute": self.calculation_cycles
            / max(1.0, (now_utc - self.started_utc).total_seconds())
            * 60,
            "publications": self.publications,
            "publications_in_window": event_count,
            "publications_per_minute": event_count / observed_seconds * 60,
            "suppressed_unchanged": self.suppressed_unchanged,
            "suppressed_policy": self.suppressed_policy,
            "suppressed_attribute_only": self.suppressed_attribute_only,
            "critical_publications": self.critical_publications,
            "payload_bytes_in_window": payload,
            "top_entities": [{"entity_key": key, "count": count} for key, count in top],
            "estimated_recorder_bytes_per_year": int(recorder_bytes),
            "estimated_influxdb_bytes_per_year": int(influx_bytes),
            "estimated_archive_bytes_per_year": archive_bytes,
            "estimated_total_bytes_per_year": annual_total,
            "budget_bytes_per_year": STORAGE_BUDGET_BYTES_PER_YEAR,
            "budget_utilization_pct": annual_total / STORAGE_BUDGET_BYTES_PER_YEAR * 100,
            "estimate_method": (
                "observed entity payload plus conservative Recorder/InfluxDB overhead"
            ),
            "policy_active_since_utc": self.started_utc.isoformat(),
        }

    def _discard_old_events(self, now_utc: datetime) -> None:
        cutoff = now_utc - timedelta(days=7)
        while self._events and self._events[0].timestamp_utc < cutoff:
            self._events.popleft()


def _attributes_fingerprint(attributes: Mapping[str, Any]) -> str:
    return json.dumps(attributes, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(state: PublicationState) -> tuple[str, str, int]:
    payload = json.dumps(
        {"available": state.available, "state": state.value, "attributes": state.attributes},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return payload, _attributes_fingerprint(state.attributes), len(payload.encode("utf-8"))


def _zero_transition(previous: Any, current: Any) -> bool:
    if not isinstance(previous, (int, float)) or not isinstance(current, (int, float)):
        return False
    return (previous <= 0 < current) or (previous > 0 >= current)


def _meaningful_delta(
    previous: Any,
    current: Any,
    key: str,
    power_deadband_kw: float,
    energy_deadband_kwh: float,
) -> bool:
    if not isinstance(previous, (int, float)) or not isinstance(current, (int, float)):
        return previous != current
    deadband = energy_deadband_kwh if "kwh" in key else power_deadband_kw
    return abs(float(current) - float(previous)) >= deadband


def projected_profile_bytes_per_year(
    *, profile: str, meter_count: int = 2, entity_count_per_meter: int = 48
) -> int:
    """Return a documented pre-save planning estimate for OptionsFlow."""

    if profile == PUBLISHING_PROFILE_AUTOMATION:
        publications_per_day_per_meter = entity_count_per_meter * 24 * 12
    elif profile == PUBLISHING_PROFILE_CUSTOM:
        publications_per_day_per_meter = entity_count_per_meter * 24 * 6
    else:
        # Stable/configuration entities publish only on change; the planning
        # allowance models 16 dynamic entities at 15-minute resolution plus
        # critical transitions.
        publications_per_day_per_meter = 16 * 96 + 50
    bytes_per_publication = 520
    archive_allowance = 40_000_000 * meter_count
    return int(
        publications_per_day_per_meter * meter_count * 365 * bytes_per_publication
        + archive_allowance
    )
