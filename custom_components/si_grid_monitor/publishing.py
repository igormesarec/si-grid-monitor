"""Centralized Home Assistant entity publishing control.

The calculation engine remains one-second and authoritative.  This module only
decides when an HA entity should expose a new state, which protects Recorder and
external state consumers such as InfluxDB from calculation-rate event streams.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from .const import (
    CONF_PUBLISHING_ACTIONABLE_DELTA_KW,
    CONF_PUBLISHING_ACTIONABLE_HYSTERESIS_KW,
    CONF_PUBLISHING_ACTIONABLE_INTERVAL_SECONDS,
    CONF_PUBLISHING_ENERGY_DEADBAND_KWH,
    CONF_PUBLISHING_FAST_ENTITIES,
    CONF_PUBLISHING_POWER_DEADBAND_KW,
    CONF_PUBLISHING_PROFILE,
    CONF_PUBLISHING_ROUTINE_INTERVAL_SECONDS,
    DEFAULT_PUBLISHING_ACTIONABLE_DELTA_KW,
    DEFAULT_PUBLISHING_ACTIONABLE_HYSTERESIS_KW,
    DEFAULT_PUBLISHING_ACTIONABLE_INTERVAL_SECONDS,
    DEFAULT_PUBLISHING_ENERGY_DEADBAND_KWH,
    DEFAULT_PUBLISHING_POWER_DEADBAND_KW,
    DEFAULT_PUBLISHING_PROFILE,
    DEFAULT_PUBLISHING_ROUTINE_INTERVAL_SECONDS,
    PUBLISHING_PROFILE_AUTOMATION,
    PUBLISHING_PROFILE_CUSTOM,
    PUBLISHING_PROFILE_STORAGE_OPTIMIZED,
)

STORAGE_BUDGET_BYTES_PER_YEAR = 1_000_000_000
SECONDS_PER_YEAR = 365 * 24 * 60 * 60
SECONDS_PER_DAY = 24 * 60 * 60
MIN_ESTIMATE_OBSERVATION_SECONDS = 3600
CRITICAL_SAFE_CLEAR_DEBOUNCE_SECONDS = 30
ACTIONABLE_SAFE_DEBOUNCE_SECONDS = 30
AVAILABILITY_RECOVERY_DEBOUNCE_SECONDS = 30
CURRENT_MEASUREMENT_MAX_AGE_SECONDS = 180
PROCESSING_ERROR_LOG_INTERVAL_SECONDS = 300
FAULT_PUBLICATION_RETRY_SECONDS = 30
ACTIONABLE_ZERO_TRANSITION_KEYS = frozenset(
    {
        "can_add_power",
        "must_reduce_power",
        "sustained_can_add_power",
        "sustained_must_reduce_power",
    }
)
ACTIONABLE_INCREASE_IS_ADVERSE = frozenset({"must_reduce_power", "sustained_must_reduce_power"})
ACTIONABLE_DECREASE_IS_ADVERSE = frozenset({"can_add_power", "sustained_can_add_power"})
FAIL_CLOSED_RECOVERY_KEYS = frozenset(
    {
        "current_power",
        "import_power",
        "export_power",
        "quarter_budget_remaining_kwh",
        "allowed_import_until_end_kw",
        "forecast_instant_kw",
        "forecast_smoothed_kw",
        "forecast_utilization_pct",
        "forecast_instant_utilization_pct",
        "current_utilization_pct",
        "can_add_power",
        "must_reduce_power",
        "sustained_can_add_power",
        "sustained_must_reduce_power",
        "projected_exceedance",
        "unrecoverable_interval",
    }
)

_LOGGER = logging.getLogger(__name__)


class PublishingClass(StrEnum):
    """Entity publication category."""

    CRITICAL = "critical"
    ACTIONABLE = "actionable"
    CURRENT_MEASUREMENT = "current_measurement"
    QUARTER_ACCUMULATION = "quarter_accumulation"
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
    actionable_delta_kw: float
    actionable_hysteresis_kw: float
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
            actionable_delta_kw=max(
                0.0,
                float(
                    data.get(
                        CONF_PUBLISHING_ACTIONABLE_DELTA_KW,
                        DEFAULT_PUBLISHING_ACTIONABLE_DELTA_KW,
                    )
                ),
            ),
            actionable_hysteresis_kw=max(
                0.0,
                float(
                    data.get(
                        CONF_PUBLISHING_ACTIONABLE_HYSTERESIS_KW,
                        DEFAULT_PUBLISHING_ACTIONABLE_HYSTERESIS_KW,
                    )
                ),
            ),
            fast_entities=fast,
        )


@dataclass(slots=True)
class _Registration:
    key: str
    publishing_class: PublishingClass
    reader: Callable[[], PublicationState]
    callback: Callable[[], None]
    failure_callback: Callable[[], None] | None = None
    last_state: PublicationState | None = None
    last_fingerprint: str | None = None
    last_attributes_fingerprint: str | None = None
    last_published_utc: datetime | None = None
    last_observed_state: PublicationState | None = None
    pending_safe_clear_utc: datetime | None = None
    pending_available_recovery_utc: datetime | None = None
    last_error_logged_utc: datetime | None = None
    last_fault_publish_attempt_utc: datetime | None = None
    faulted: bool = False
    fault_publication_succeeded: bool = False


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
        self._last_discarded_event_utc: datetime | None = None
        self.started_utc = datetime.now(UTC)
        self.publishing_evaluations = 0
        self.internal_timer_ticks = 0
        self.publications = 0
        self.suppressed_unchanged = 0
        self.suppressed_policy = 0
        self.suppressed_attribute_only = 0
        self.critical_publications = 0
        self.processing_failures = 0
        self.last_successful_publication_utc: datetime | None = None

    def register(
        self,
        key: str,
        publishing_class: PublishingClass,
        reader: Callable[[], PublicationState],
        callback: Callable[[], None],
        failure_callback: Callable[[], None] | None = None,
    ) -> Callable[[], None]:
        """Register exactly one entity callback and return its remover."""

        self._registrations[key] = _Registration(
            key, publishing_class, reader, callback, failure_callback
        )

        def remove() -> None:
            registration = self._registrations.get(key)
            if registration is not None and registration.callback is callback:
                self._registrations.pop(key, None)

        return remove

    def clear(self) -> None:
        """Release entity references during runtime shutdown."""

        self._registrations.clear()

    def process(self, now_utc: datetime) -> None:
        """Evaluate policies after a timer tick or source-triggered refresh."""

        now_utc = now_utc.astimezone(UTC)
        self.publishing_evaluations += 1
        for registration in tuple(self._registrations.values()):
            ha_callback_succeeded = False
            try:
                state = registration.reader()
                fingerprint, attributes_fingerprint, payload_bytes = _fingerprint(state)
                registration.faulted = False
                should_publish, critical = self._should_publish(
                    registration, state, fingerprint, now_utc
                )
                if not should_publish:
                    registration.last_observed_state = state
                    continue
                registration.callback()
                ha_callback_succeeded = True
                # The HA callback succeeded, so advance its durable publication
                # cursor before optional diagnostic event bookkeeping. If that
                # bookkeeping fails, the entity must not duplicate the already
                # emitted HA state on the next one-second evaluation.
                registration.last_state = state
                registration.last_observed_state = state
                registration.last_fingerprint = fingerprint
                registration.last_attributes_fingerprint = attributes_fingerprint
                registration.last_published_utc = now_utc
                registration.faulted = False
                registration.fault_publication_succeeded = False
                registration.last_fault_publish_attempt_utc = None
                self.publications += 1
                self.last_successful_publication_utc = now_utc
                self.critical_publications += int(critical)
                event = _PublicationEvent(now_utc, registration.key, payload_bytes, critical)
                self._append_event(event)
            except Exception:
                # Reader, serialization, policy, callback and bookkeeping
                # failures are all isolated. Reader/callback failures retain the
                # previous cursor for retry; a post-callback diagnostic failure
                # retains the advanced cursor to avoid a duplicate HA state.
                self.processing_failures += 1
                if not ha_callback_succeeded:
                    registration.faulted = True
                    self._publish_fault_state(registration, now_utc)
                if (
                    registration.last_error_logged_utc is None
                    or (now_utc - registration.last_error_logged_utc).total_seconds()
                    >= PROCESSING_ERROR_LOG_INTERVAL_SECONDS
                ):
                    registration.last_error_logged_utc = now_utc
                    _LOGGER.exception(
                        "Failed to evaluate or publish SI Grid Monitor entity %s",
                        registration.key,
                    )
                continue
        self._discard_old_events(now_utc)

    def _publish_fault_state(self, registration: _Registration, now_utc: datetime) -> None:
        """Publish one bounded unavailable state when an entity pipeline fails."""

        if registration.failure_callback is None or registration.fault_publication_succeeded:
            return
        if (
            registration.last_fault_publish_attempt_utc is not None
            and (now_utc - registration.last_fault_publish_attempt_utc).total_seconds()
            < FAULT_PUBLICATION_RETRY_SECONDS
        ):
            return
        registration.last_fault_publish_attempt_utc = now_utc
        fault_state = PublicationState(None, False, {"publication_fault": True})
        try:
            registration.failure_callback()
        except Exception:
            # The normal HA write path itself may be unavailable. Keep the
            # registration fault visible in diagnostics and retry at a bounded
            # interval; software cannot guarantee a fallback state when HA's
            # state-write callback also fails.
            return
        fingerprint, attributes_fingerprint, payload_bytes = _fingerprint(fault_state)
        registration.last_state = fault_state
        registration.last_observed_state = fault_state
        registration.last_fingerprint = fingerprint
        registration.last_attributes_fingerprint = attributes_fingerprint
        registration.last_published_utc = now_utc
        registration.fault_publication_succeeded = True
        self.publications += 1
        self.critical_publications += 1
        self.last_successful_publication_utc = now_utc
        try:
            self._append_event(_PublicationEvent(now_utc, registration.key, payload_bytes, True))
        except Exception:
            # The HA unavailable state is already durable; diagnostics must not
            # turn that success into a retry storm or block another entity.
            return

    def record_internal_timer_tick(self) -> None:
        """Record the actual one-second runtime timer independently of evaluations."""

        self.internal_timer_ticks += 1

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
        if not state.available and registration.pending_available_recovery_utc is not None:
            registration.pending_available_recovery_utc = None
        if state.available != previous.available:
            if not state.available:
                registration.pending_safe_clear_utc = None
                registration.pending_available_recovery_utc = None
                return True, True
            if registration.key in FAIL_CLOSED_RECOVERY_KEYS:
                if registration.pending_available_recovery_utc is None:
                    registration.pending_available_recovery_utc = now_utc
                elapsed = (now_utc - registration.pending_available_recovery_utc).total_seconds()
                if elapsed < 0:
                    registration.pending_available_recovery_utc = now_utc
                    elapsed = 0
                if elapsed < AVAILABILITY_RECOVERY_DEBOUNCE_SECONDS:
                    self.suppressed_policy += 1
                    return False, False
                registration.pending_available_recovery_utc = None
                return True, True
            registration.pending_safe_clear_utc = None
            return True, True
        if (
            registration.publishing_class == PublishingClass.QUARTER_ACCUMULATION
            and state.attributes.get("quarter_start_utc")
            != previous.attributes.get("quarter_start_utc")
        ):
            # A current-quarter entity must reset to the new canonical quarter
            # immediately; the completed result remains in the archive and the
            # dedicated last-completed entities.
            return True, False
        if registration.publishing_class == PublishingClass.QUARTER_ACCUMULATION:
            previous_elapsed = previous.attributes.get("quarter_elapsed_seconds")
            current_elapsed = state.attributes.get("quarter_elapsed_seconds")
            if (
                isinstance(previous_elapsed, (int, float))
                and isinstance(current_elapsed, (int, float))
                and previous_elapsed < 60 <= current_elapsed
            ):
                # Avoid leaving the initial near-zero state visible through the
                # first general freshness interval of a newly started quarter.
                return True, False
        if registration.key == "projected_exceedance":
            if bool(state.value):
                # Hazard assertion (and reassertion after a false observation)
                # is immediate.  Any pending safe clear is cancelled.
                registration.pending_safe_clear_utc = None
            elif bool(previous.value):
                # Safe clear must be continuously observed to prevent a noisy
                # threshold from producing a critical event every second.
                if registration.pending_safe_clear_utc is None:
                    registration.pending_safe_clear_utc = now_utc
                elapsed = (now_utc - registration.pending_safe_clear_utc).total_seconds()
                if elapsed < 0:
                    registration.pending_safe_clear_utc = now_utc
                    elapsed = 0
                if elapsed < CRITICAL_SAFE_CLEAR_DEBOUNCE_SECONDS:
                    self.suppressed_policy += 1
                    return False, False
                registration.pending_safe_clear_utc = None
                return True, True
        if registration.key == "input_stale":
            if bool(state.value):
                registration.pending_safe_clear_utc = None
            elif bool(previous.value):
                if registration.pending_safe_clear_utc is None:
                    registration.pending_safe_clear_utc = now_utc
                elapsed = (now_utc - registration.pending_safe_clear_utc).total_seconds()
                if elapsed < 0:
                    registration.pending_safe_clear_utc = now_utc
                    elapsed = 0
                if elapsed < CRITICAL_SAFE_CLEAR_DEBOUNCE_SECONDS:
                    self.suppressed_policy += 1
                    return False, False
                registration.pending_safe_clear_utc = None
                return True, True
        if registration.key in ACTIONABLE_ZERO_TRANSITION_KEYS:
            transition = _actionable_zero_transition(
                registration.key,
                previous.value,
                state.value,
                self.settings.actionable_hysteresis_kw,
            )
            if transition == "adverse":
                registration.pending_safe_clear_utc = None
                return True, True
            direction = _actionable_value_direction(
                registration.key,
                previous.value,
                state.value,
                self.settings.actionable_hysteresis_kw,
            )
            observed_previous = registration.last_observed_state or previous
            observed_direction = _actionable_value_direction(
                registration.key,
                observed_previous.value,
                state.value,
                self.settings.actionable_hysteresis_kw,
            )
            if direction == "improvement":
                if observed_direction == "adverse":
                    registration.pending_safe_clear_utc = None
                if registration.pending_safe_clear_utc is None:
                    registration.pending_safe_clear_utc = now_utc
                elapsed = (now_utc - registration.pending_safe_clear_utc).total_seconds()
                if elapsed < 0:
                    registration.pending_safe_clear_utc = now_utc
                    elapsed = 0
                if elapsed < ACTIONABLE_SAFE_DEBOUNCE_SECONDS:
                    self.suppressed_policy += 1
                    return False, False
                if transition == "improvement":
                    # Crossing the zero/hysteresis boundary changes the
                    # semantic advice state and is published once after the
                    # required continuously-safe evidence window.
                    registration.pending_safe_clear_utc = None
                    return True, False
                # The candidate is now safe enough to be eligible, but it is
                # still an optimistic permission/restriction reduction. Keep
                # the configured ACTIONABLE cadence and deadband below instead
                # of creating a new publication every 30 seconds during a
                # slowly improving trace. Retain the evidence timestamp until
                # this eligible value is published or the direction worsens.
            if direction != "improvement" and registration.pending_safe_clear_utc is not None:
                # The observed value left the continuously safe side before
                # debounce completion. Retain the conservative public value.
                registration.pending_safe_clear_utc = None
        if fingerprint == registration.last_fingerprint:
            self.suppressed_unchanged += 1
            return False, False
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
        elapsed = (now_utc - registration.last_published_utc).total_seconds()
        observed_previous = registration.last_observed_state or previous
        if changed_value and (
            _actionable_change_is_adverse(
                registration.key,
                observed_previous.value,
                state.value,
                self.settings.actionable_delta_kw,
            )
            or _actionable_change_is_adverse(
                registration.key,
                previous.value,
                state.value,
                self.settings.actionable_delta_kw,
            )
        ):
            return True, True
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
        if publishing_class == PublishingClass.QUARTER_ACCUMULATION:
            if self.settings.profile == PUBLISHING_PROFILE_STORAGE_OPTIMIZED:
                return min(
                    CURRENT_MEASUREMENT_MAX_AGE_SECONDS,
                    self.settings.routine_interval_seconds,
                )
            return self.settings.routine_interval_seconds
        if publishing_class == PublishingClass.DIAGNOSTIC:
            return max(300, self.settings.routine_interval_seconds)
        return self.settings.routine_interval_seconds

    def diagnostics(self, now_utc: datetime, window_seconds: int = 3600) -> dict[str, Any]:
        """Return bounded publication counters without querying Recorder."""

        now_utc = now_utc.astimezone(UTC)
        self._discard_old_events(now_utc)
        requested_window_seconds = max(60, window_seconds)
        cutoff = now_utc - timedelta(seconds=requested_window_seconds)
        events = [event for event in self._events if event.timestamp_utc >= cutoff]
        observed_seconds = max(
            1.0,
            min(
                float(requested_window_seconds),
                (now_utc - self.started_utc).total_seconds(),
            ),
        )
        payload = sum(event.payload_bytes for event in events)
        event_count = len(events)
        discarded_in_window = (
            self._last_discarded_event_utc is not None and self._last_discarded_event_utc >= cutoff
        )
        full_observation_window = self.started_utc <= cutoff
        estimate_ready = (
            observed_seconds >= MIN_ESTIMATE_OBSERVATION_SECONDS
            and full_observation_window
            and not discarded_in_window
        )
        annual_factor = SECONDS_PER_YEAR / observed_seconds if estimate_ready else 0.0
        # Recorder estimate includes a conservative row/index allowance; the
        # Influx estimate represents state/field/series protocol overhead. The
        # dashboard labels both as estimates rather than physical allocation.
        annual_payload = payload * annual_factor
        recorder_bytes = annual_payload + event_count * 240 * annual_factor
        influx_bytes = event_count * 140 * annual_factor
        archive_bytes = 40_000_000  # dense schema-7 quarter/audit allowance per meter/year
        annual_total = (
            int(recorder_bytes + influx_bytes + archive_bytes) if estimate_ready else None
        )
        top = Counter(event.key for event in events).most_common(10)
        return {
            "profile": self.settings.profile,
            "window_seconds": requested_window_seconds,
            "publishing_evaluations": self.publishing_evaluations,
            "publishing_evaluations_per_minute": self.publishing_evaluations
            / max(1.0, (now_utc - self.started_utc).total_seconds())
            * 60,
            "internal_timer_ticks": self.internal_timer_ticks,
            "internal_timer_ticks_per_minute": self.internal_timer_ticks
            / max(1.0, (now_utc - self.started_utc).total_seconds())
            * 60,
            "publications": self.publications,
            "publications_in_window": event_count,
            "publications_per_minute": event_count / observed_seconds * 60,
            "suppressed_unchanged": self.suppressed_unchanged,
            "suppressed_policy": self.suppressed_policy,
            "suppressed_attribute_only": self.suppressed_attribute_only,
            "critical_publications": self.critical_publications,
            "processing_failures": self.processing_failures,
            "faulted_entities": sorted(
                registration.key
                for registration in self._registrations.values()
                if registration.faulted
            ),
            "last_successful_publication_utc": (
                self.last_successful_publication_utc.isoformat()
                if self.last_successful_publication_utc is not None
                else None
            ),
            "effective_current_measurement_interval_seconds": self._interval_for(
                PublishingClass.CURRENT_MEASUREMENT
            ),
            "effective_quarter_accumulation_interval_seconds": self._interval_for(
                PublishingClass.QUARTER_ACCUMULATION
            ),
            "effective_actionable_interval_seconds": self._interval_for(PublishingClass.ACTIONABLE),
            "effective_monitoring_interval_seconds": self._interval_for(PublishingClass.MONITORING),
            "payload_bytes_in_window": payload,
            "top_entities": [{"entity_key": key, "count": count} for key, count in top],
            "estimated_recorder_bytes_per_year": int(recorder_bytes) if estimate_ready else None,
            "estimated_influxdb_bytes_per_year": int(influx_bytes) if estimate_ready else None,
            "estimated_archive_bytes_per_year": archive_bytes,
            "estimated_total_bytes_per_year": annual_total,
            "budget_bytes_per_year": STORAGE_BUDGET_BYTES_PER_YEAR,
            "budget_utilization_pct": (
                annual_total / STORAGE_BUDGET_BYTES_PER_YEAR * 100
                if annual_total is not None
                else None
            ),
            "estimate_status": (
                "truncated" if discarded_in_window else "ready" if estimate_ready else "warming_up"
            ),
            "event_history_truncated": discarded_in_window,
            "event_history_window_complete": full_observation_window and not discarded_in_window,
            "influxdb_physical_storage_verified": False,
            "estimate_method": (
                "observed entity payload plus Recorder-like SQLite allocation; "
                "InfluxDB is an unverified planning allowance"
            ),
            "policy_active_since_utc": self.started_utc.isoformat(),
        }

    def _append_event(self, event: _PublicationEvent) -> None:
        """Append one event and retain the newest discarded-event boundary."""

        if self._events.maxlen is not None and len(self._events) == self._events.maxlen:
            discarded = self._events[0].timestamp_utc
            if self._last_discarded_event_utc is None or discarded > self._last_discarded_event_utc:
                self._last_discarded_event_utc = discarded
        self._events.append(event)

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


def _actionable_zero_transition(
    key: str, previous: Any, current: Any, hysteresis_kw: float
) -> str | None:
    if not isinstance(previous, (int, float)) or not isinstance(current, (int, float)):
        return None
    activated = previous <= hysteresis_kw and current > hysteresis_kw
    cleared = previous > hysteresis_kw and current <= 0
    if key in ACTIONABLE_INCREASE_IS_ADVERSE:
        if activated:
            return "adverse"
        if cleared:
            return "improvement"
    if key in ACTIONABLE_DECREASE_IS_ADVERSE:
        if cleared:
            return "adverse"
        if activated:
            return "improvement"
    return None


def _actionable_value_direction(
    key: str, previous: Any, current: Any, hysteresis_kw: float
) -> str | None:
    """Classify a numeric move relative to the last public conservative value."""

    if not isinstance(previous, (int, float)) or not isinstance(current, (int, float)):
        return None
    delta = float(current) - float(previous)
    if delta == 0:
        return None
    if (
        key in ACTIONABLE_DECREASE_IS_ADVERSE
        and float(previous) <= hysteresis_kw
        and float(current) <= hysteresis_kw
    ):
        return None
    if key in ACTIONABLE_INCREASE_IS_ADVERSE:
        return "adverse" if delta > 0 else "improvement"
    if key in ACTIONABLE_DECREASE_IS_ADVERSE:
        return "adverse" if delta < 0 else "improvement"
    return None


def _actionable_change_is_adverse(
    key: str,
    previous: Any,
    current: Any,
    minimum_delta_kw: float,
) -> bool:
    """Return whether the latest observed change worsens actionable safety."""

    if not isinstance(previous, (int, float)) or not isinstance(current, (int, float)):
        return False
    delta = float(current) - float(previous)
    if key in ACTIONABLE_INCREASE_IS_ADVERSE:
        return delta >= minimum_delta_kw
    if key in ACTIONABLE_DECREASE_IS_ADVERSE:
        return -delta >= minimum_delta_kw
    return False


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
    *,
    profile: str,
    meter_count: int = 2,
    entity_count_per_meter: int = 48,
    routine_interval_seconds: int | None = None,
    actionable_interval_seconds: int | None = None,
    fast_entities: tuple[str, ...] | frozenset[str] = (),
) -> int:
    """Return a conservative, explicitly assumption-based Options estimate."""

    if profile == PUBLISHING_PROFILE_AUTOMATION:
        publications_per_day_per_meter = entity_count_per_meter * 24 * 12
    elif profile == PUBLISHING_PROFILE_CUSTOM:
        routine = max(15, int(routine_interval_seconds or 900))
        actionable = max(1, int(actionable_interval_seconds or 300))
        # Planning categories deliberately do not claim to predict the user's
        # future signal. Fast entities use a 15-second source-change allowance;
        # the preview labels this as an assumption rather than a guarantee.
        routine_entities = max(0, entity_count_per_meter - 12)
        publications_per_day_per_meter = (
            routine_entities * SECONDS_PER_DAY / routine
            + 8 * SECONDS_PER_DAY / actionable
            + len(fast_entities) * SECONDS_PER_DAY / 15
            + 200
        )
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
