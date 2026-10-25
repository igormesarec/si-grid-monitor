"""Regression tests for calculation-rate independent HA publication."""

from __future__ import annotations

import re
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path

from custom_components.si_grid_monitor.const import (
    CONF_PUBLISHING_ACTIONABLE_INTERVAL_SECONDS,
    CONF_PUBLISHING_PROFILE,
    CONF_PUBLISHING_ROUTINE_INTERVAL_SECONDS,
    PUBLISHING_PROFILE_AUTOMATION,
    PUBLISHING_PROFILE_CUSTOM,
)
from custom_components.si_grid_monitor.publishing import (
    STORAGE_BUDGET_BYTES_PER_YEAR,
    PublicationState,
    PublishingClass,
    PublishingController,
    PublishingSettings,
    projected_profile_bytes_per_year,
)


def _settings(**overrides: object) -> PublishingSettings:
    return PublishingSettings.from_mapping(
        {
            CONF_PUBLISHING_PROFILE: PUBLISHING_PROFILE_CUSTOM,
            CONF_PUBLISHING_ROUTINE_INTERVAL_SECONDS: 900,
            CONF_PUBLISHING_ACTIONABLE_INTERVAL_SECONDS: 300,
            **overrides,
        }
    )


def test_every_public_entity_has_an_explicit_policy() -> None:
    root = Path(__file__).parents[1] / "custom_components" / "si_grid_monitor"
    for filename, description_name, policy_name in (
        ("sensor.py", "SENSORS", "SENSOR_PUBLISHING_POLICIES"),
        ("binary_sensor.py", "BINARY_SENSORS", "BINARY_SENSOR_PUBLISHING_POLICIES"),
    ):
        source = (root / filename).read_text(encoding="utf-8")
        descriptions = source.split(description_name, 1)[1].split(policy_name, 1)[0]
        policies = source.split(policy_name, 1)[1].split("}\n", 1)[0]
        entity_keys = set(re.findall(r'key="([a-z0-9_]+)"', descriptions))
        policy_keys = set(re.findall(r'^\s+"([a-z0-9_]+)":', policies, re.MULTILINE))
        assert policy_keys == entity_keys


def test_one_second_calculation_does_not_publish_identical_state() -> None:
    controller = PublishingController(_settings())
    state = PublicationState(2.5, True, {"source_mode": "signed_power"})
    writes: list[int] = []
    controller.register(
        "current_power", PublishingClass.MONITORING, lambda: state, lambda: writes.append(1)
    )
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for second in range(3600):
        controller.process(start + timedelta(seconds=second))

    assert controller.publishing_evaluations == 3600
    assert len(writes) == 1
    assert controller.suppressed_unchanged == 3599


def test_deadband_and_attribute_changes_are_coalesced() -> None:
    controller = PublishingController(_settings())
    mutable = {"value": 1.0, "age": 0}
    writes: list[float] = []
    controller.register(
        "current_power",
        PublishingClass.MONITORING,
        lambda: PublicationState(mutable["value"], True, {"age": mutable["age"]}),
        lambda: writes.append(mutable["value"]),
    )
    start = datetime(2026, 1, 1, tzinfo=UTC)
    controller.process(start)
    for second in range(1, 900):
        mutable["age"] = second
        controller.process(start + timedelta(seconds=second))
    assert len(writes) == 1
    assert controller.suppressed_attribute_only == 899
    mutable["value"] += 0.1
    controller.process(start + timedelta(seconds=900))
    assert len(writes) == 2


def test_critical_and_availability_transitions_publish_in_one_cycle() -> None:
    controller = PublishingController(_settings())
    mutable = {"value": False, "available": True, "detail": 0}
    writes: list[tuple[bool, bool]] = []
    controller.register(
        "projected_exceedance",
        PublishingClass.CRITICAL,
        lambda: PublicationState(
            mutable["value"], mutable["available"], {"detail": mutable["detail"]}
        ),
        lambda: writes.append((mutable["value"], mutable["available"])),
    )
    start = datetime(2026, 1, 1, tzinfo=UTC)
    controller.process(start)
    mutable["detail"] = 1
    controller.process(start + timedelta(seconds=1))
    assert len(writes) == 1
    mutable["value"] = True
    controller.process(start + timedelta(seconds=2))
    mutable["available"] = False
    controller.process(start + timedelta(seconds=3))
    assert writes == [(False, True), (True, True), (True, False)]


def test_actionable_zero_crossing_is_immediate() -> None:
    controller = PublishingController(_settings())
    mutable = {"value": 0.0}
    writes: list[float] = []
    controller.register(
        "must_reduce_power",
        PublishingClass.ACTIONABLE,
        lambda: PublicationState(mutable["value"], True, {}),
        lambda: writes.append(mutable["value"]),
    )
    start = datetime(2026, 1, 1, tzinfo=UTC)
    controller.process(start)
    mutable["value"] = 0.5
    controller.process(start + timedelta(seconds=1))
    mutable["value"] = 0.0
    controller.process(start + timedelta(seconds=2))
    assert writes == [0.0, 0.5, 0.0]


def test_monitoring_power_near_zero_cannot_bypass_interval() -> None:
    controller = PublishingController(_settings())
    mutable = {"value": -0.01}
    writes: list[float] = []
    controller.register(
        "current_power",
        PublishingClass.MONITORING,
        lambda: PublicationState(mutable["value"], True, {}),
        lambda: writes.append(mutable["value"]),
    )
    start = datetime(2026, 1, 1, tzinfo=UTC)
    controller.process(start)
    for second in range(1, 300):
        mutable["value"] = 0.01 if second % 2 else -0.01
        controller.process(start + timedelta(seconds=second))
    assert writes == [-0.01]


def test_actionable_hysteresis_and_large_change_latency() -> None:
    controller = PublishingController(_settings())
    mutable = {"value": 0.0}
    writes: list[tuple[int, float]] = []
    start = datetime(2026, 1, 1, tzinfo=UTC)
    now = start
    controller.register(
        "can_add_power",
        PublishingClass.ACTIONABLE,
        lambda: PublicationState(mutable["value"], True, {}),
        lambda: writes.append((int((now - start).total_seconds()), mutable["value"])),
    )
    controller.process(start)
    for second, value in ((1, 0.01), (2, 0.04), (3, 0.051)):
        now = start + timedelta(seconds=second)
        mutable["value"] = value
        controller.process(now)
    assert writes == [(0, 0.0), (3, 0.051)]

    mutable["value"] = 2.5
    now = start + timedelta(seconds=4)
    controller.process(now)
    assert writes[-1] == (3, 0.051)

    urgent = PublishingController(_settings())
    urgent_value = {"value": 0.1}
    urgent_writes: list[float] = []
    urgent.register(
        "can_add_power",
        PublishingClass.ACTIONABLE,
        lambda: PublicationState(urgent_value["value"], True, {}),
        lambda: urgent_writes.append(urgent_value["value"]),
    )
    urgent.process(start)
    urgent_value["value"] = 2.5
    urgent.process(start + timedelta(seconds=1))
    assert urgent_writes == [0.1, 2.5]


def test_diagnostics_warmup_and_timer_tick_accounting() -> None:
    controller = PublishingController(_settings())
    start = datetime(2026, 1, 1, tzinfo=UTC)
    controller.started_utc = start
    controller.register(
        "current_power",
        PublishingClass.MONITORING,
        lambda: PublicationState(1.0, True, {}),
        lambda: None,
    )
    for second in range(60):
        controller.record_internal_timer_tick()
        controller.process(start + timedelta(seconds=second))
        controller.process(start + timedelta(seconds=second, milliseconds=500))
    warmup = controller.diagnostics(start + timedelta(minutes=1))
    assert warmup["internal_timer_ticks"] == 60
    assert warmup["publishing_evaluations"] == 120
    assert warmup["estimate_status"] == "warming_up"
    assert warmup["estimated_total_bytes_per_year"] is None
    assert warmup["influxdb_physical_storage_verified"] is False


def test_bounded_event_history_reports_truncation() -> None:
    controller = PublishingController(_settings())
    controller._events = deque(maxlen=2)
    mutable = {"value": False}
    controller.register(
        "projected_exceedance",
        PublishingClass.CRITICAL,
        lambda: PublicationState(mutable["value"], True, {}),
        lambda: None,
    )
    start = datetime(2026, 1, 1, tzinfo=UTC)
    controller.started_utc = start
    for second in range(4):
        mutable["value"] = bool(second % 2)
        controller.process(start + timedelta(seconds=second))
    metrics = controller.diagnostics(start + timedelta(hours=1))
    assert metrics["event_history_truncated"] is True
    assert metrics["publications"] == 4
    assert metrics["publications_in_window"] == 2


def test_profiles_and_default_two_meter_plan_are_bounded() -> None:
    automation = PublishingSettings.from_mapping(
        {CONF_PUBLISHING_PROFILE: PUBLISHING_PROFILE_AUTOMATION}
    )
    assert automation.routine_interval_seconds == 60
    assert automation.actionable_interval_seconds == 15
    assert projected_profile_bytes_per_year(profile="storage_optimized", meter_count=2) < (
        STORAGE_BUDGET_BYTES_PER_YEAR
    )
    assert (
        projected_profile_bytes_per_year(profile=PUBLISHING_PROFILE_AUTOMATION, meter_count=2)
        > STORAGE_BUDGET_BYTES_PER_YEAR
    )


def test_two_controllers_are_isolated() -> None:
    first = PublishingController(_settings())
    second = PublishingController(_settings())
    first_writes: list[int] = []
    second_writes: list[int] = []
    state = PublicationState(1.0, True, {})
    first.register(
        "current_power", PublishingClass.MONITORING, lambda: state, lambda: first_writes.append(1)
    )
    second.register(
        "current_power", PublishingClass.MONITORING, lambda: state, lambda: second_writes.append(1)
    )
    now = datetime(2026, 1, 1, tzinfo=UTC)
    first.process(now)
    assert first_writes == [1]
    assert second_writes == []
