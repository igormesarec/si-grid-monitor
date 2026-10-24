"""V1.0.2 contract-management, audit, and health regressions."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta

import pytest

from custom_components.si_grid_monitor.archive import (
    ArchiveRecord,
    ConfigurationStatus,
    ContractAuditEvent,
    QuarterArchive,
)
from custom_components.si_grid_monitor.contract_health import (
    ContractHealthLevel,
    contract_issue_id,
    evaluate_contract_health,
)
from custom_components.si_grid_monitor.contracted_power import (
    ContractedPowerPeriod,
    ContractedPowerSchedule,
)

ORIGINAL = (1.0, 1.1, 1.2, 1.3, 1.4)
NEW = (2.0, 2.1, 2.2, 2.3, 2.4)


def _period(start: date, end: date, targets=ORIGINAL) -> ContractedPowerPeriod:
    return ContractedPowerPeriod(start, end, targets, "test_fixture")


def test_schedule_change_october_25_produces_two_inclusive_segments() -> None:
    schedule = ContractedPowerSchedule((_period(date(2026, 1, 1), date(2026, 12, 31)),))
    changed = schedule.schedule_change(0, _period(date(2026, 10, 25), date(2026, 12, 31), NEW))
    assert [(item.effective_from, item.effective_to) for item in changed.periods] == [
        (date(2026, 1, 1), date(2026, 10, 24)),
        (date(2026, 10, 25), date(2026, 12, 31)),
    ]
    assert changed.periods[0].block_targets_kw == ORIGINAL
    assert changed.periods[1].block_targets_kw == NEW


def test_middle_range_change_produces_three_segments() -> None:
    schedule = ContractedPowerSchedule((_period(date(2026, 1, 1), date(2026, 12, 31)),))
    changed = schedule.schedule_change(0, _period(date(2026, 7, 1), date(2026, 9, 30), NEW))
    assert [
        (item.effective_from, item.effective_to, item.block_targets_kw) for item in changed.periods
    ] == [
        (date(2026, 1, 1), date(2026, 6, 30), ORIGINAL),
        (date(2026, 7, 1), date(2026, 9, 30), NEW),
        (date(2026, 10, 1), date(2026, 12, 31), ORIGINAL),
    ]


def test_overlap_conflict_adjacent_ranges_and_gaps_are_explicit() -> None:
    first = _period(date(2026, 1, 1), date(2026, 10, 24))
    second = _period(date(2026, 10, 25), date(2026, 12, 31), NEW)
    schedule = ContractedPowerSchedule((first, second))
    assert schedule.conflict_for(_period(date(2026, 10, 24), date(2026, 10, 25))) == first
    assert schedule.gaps(date(2026, 1, 1), date(2026, 12, 31)) == ()
    gap_schedule = ContractedPowerSchedule(
        (
            _period(date(2026, 1, 1), date(2026, 6, 30)),
            _period(date(2026, 8, 1), date(2026, 12, 31)),
        )
    )
    assert gap_schedule.gaps(date(2026, 1, 1), date(2026, 12, 31)) == (
        (date(2026, 7, 1), date(2026, 7, 31)),
    )


def test_contract_health_thresholds_and_successor_suppression() -> None:
    today = date(2026, 12, 1)
    warning = ContractedPowerSchedule((_period(date(2026, 1, 1), date(2026, 12, 31)),))
    assert evaluate_contract_health(warning, today).level is ContractHealthLevel.WARNING
    urgent = evaluate_contract_health(warning, date(2026, 12, 24))
    assert urgent.level is ContractHealthLevel.URGENT
    successor = ContractedPowerSchedule(
        (
            _period(date(2026, 1, 1), date(2026, 12, 31)),
            _period(date(2027, 1, 1), date(2027, 12, 31), NEW),
        )
    )
    assert evaluate_contract_health(successor, today).level is ContractHealthLevel.OK
    missing = evaluate_contract_health(warning, date(2027, 1, 1))
    assert missing.level is ContractHealthLevel.ERROR
    assert missing.reason == "missing_current_assignment"


def test_repairs_issue_identity_is_stable_and_meter_scoped() -> None:
    assert contract_issue_id("meter-a") == "contract_assignment_meter-a"
    assert contract_issue_id("meter-a") == contract_issue_id("meter-a")
    assert contract_issue_id("meter-a") != contract_issue_id("meter-b")


def _record(start: datetime) -> ArchiveRecord:
    return ArchiveRecord(
        namespace="meter-a",
        start_utc=start,
        end_utc=start + timedelta(minutes=15),
        import_kwh=0.25,
        export_kwh=0.0,
        signed_average_kw=1.0,
        import_demand_kw=1.0,
        coverage_seconds=900.0,
        gap_seconds=0.0,
        quality="measured_aligned",
        provenance="live",
        source_id="sensor.grid",
        source_epoch=1,
        configuration_status="known",
        contractual_target_kw=1.2,
        safety_margin_kw=0.0,
        operational_target_kw=1.2,
        utilization_pct=83.333333,
        exceeded=False,
        excess_kw=0.0,
    )


def test_schema6_to_schema7_is_additive_and_audit_is_idempotent(tmp_path) -> None:
    path = tmp_path / "archive.db"
    archive = QuarterArchive(path)
    archive.open()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    archive.upsert_quarter(_record(start))
    archive.close()
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE contract_audit")
        db.execute("PRAGMA user_version=6")
        db.commit()

    reopened = QuarterArchive(path)
    reopened.open()
    assert reopened.schema_version == 7
    assert len(reopened.list_quarters("meter-a", start, start + timedelta(minutes=15))) == 1
    event = ContractAuditEvent(
        "event-1",
        "meter-a",
        datetime(2026, 10, 1, tzinfo=UTC),
        "SCHEDULED_CHANGE",
        "[]",
        "[]",
        "2026-10-25",
        "2026-12-31",
        "test_fixture",
        None,
        "user_action",
        None,
        "revision",
    )
    assert reopened.append_contract_audit(event) is True
    assert reopened.append_contract_audit(event) is False
    assert reopened.list_contract_audit("meter-a")[0]["event_type"] == "SCHEDULED_CHANGE"


def test_contract_audit_history_is_retrievable_with_bounded_pagination(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "audit-pages.db")
    archive.open()
    for index in range(225):
        event = ContractAuditEvent(
            f"event-{index:03d}",
            "meter-a",
            datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=index),
            "CORRECTED",
            "[]",
            "[]",
            "2026-01-01",
            "2026-12-31",
            f"fixture-{index}",
            None,
            "user_action",
            None,
            f"revision-{index}",
        )
        assert archive.append_contract_audit(event)

    first = archive.list_contract_audit("meter-a", 100, 0)
    third = archive.list_contract_audit("meter-a", 100, 200)
    assert archive.count_contract_audit("meter-a") == 225
    assert len(first) == 100
    assert len(third) == 25
    assert first[0]["event_id"] == "event-224"
    assert third[-1]["event_id"] == "event-000"
    assert {item["event_id"] for item in first}.isdisjoint({item["event_id"] for item in third})


@pytest.mark.parametrize(
    "failure_point",
    [
        "before_v7_schema_change",
        "after_contract_audit_table",
        "after_contract_audit_index",
        "before_v7_version_update",
    ],
)
def test_schema7_migration_rolls_back_and_retries(
    tmp_path, monkeypatch, failure_point: str
) -> None:
    path = tmp_path / f"archive-{failure_point}.db"
    archive = QuarterArchive(path)
    archive.open()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    archive.upsert_quarter(_record(start))
    archive.close()
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE contract_audit")
        db.execute("PRAGMA user_version=6")
        db.commit()

    def fail_at(self, point: str) -> None:
        if point == failure_point:
            raise OSError("injected migration interruption")

    monkeypatch.setattr(QuarterArchive, "_migration_checkpoint", fail_at)
    interrupted = QuarterArchive(path)
    with pytest.raises(OSError, match="injected migration interruption"):
        interrupted.open()
    interrupted.close()
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 6
        assert db.execute("SELECT COUNT(*) FROM quarters").fetchone()[0] == 1
        if failure_point != "before_v7_schema_change":
            assert (
                db.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE name='contract_audit'"
                ).fetchone()[0]
                == 0
            )

    monkeypatch.setattr(QuarterArchive, "_migration_checkpoint", lambda self, point: None)
    recovered = QuarterArchive(path)
    recovered.open()
    assert recovered.schema_version == 7
    assert len(recovered.list_quarters("meter-a", start, start + timedelta(minutes=15))) == 1


def test_future_only_epoch_change_does_not_mix_current_quarter(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "epochs.db")
    archive.open()
    start = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
    original = ContractedPowerSchedule((_period(date(2026, 1, 1), date(2026, 12, 31)),))
    future_changed = ContractedPowerSchedule(
        (
            _period(date(2026, 1, 1), date(2026, 12, 31)),
            _period(date(2027, 1, 1), date(2027, 12, 31), NEW),
        )
    )
    archive.register_configuration_epoch(
        namespace="meter-a",
        source_id="sensor.grid",
        positive_means_import=True,
        contractual_target_kw=1.0,
        safety_margin_kw=0.0,
        block_targets_kw=ORIGINAL,
        allow_provisional_tariff=False,
        contracted_power_schedule=original,
        effective_utc=start,
    )
    archive.register_configuration_epoch(
        namespace="meter-a",
        source_id="sensor.grid",
        positive_means_import=True,
        contractual_target_kw=1.0,
        safety_margin_kw=0.0,
        block_targets_kw=ORIGINAL,
        allow_provisional_tariff=False,
        contracted_power_schedule=future_changed,
        effective_utc=start + timedelta(minutes=5),
    )
    resolved = archive.resolve_configuration("meter-a", start, start + timedelta(minutes=15))
    assert resolved.status is ConfigurationStatus.KNOWN


def test_actual_midquarter_target_change_remains_mixed(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "mixed.db")
    archive.open()
    start = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
    first = ContractedPowerSchedule((_period(date(2026, 1, 1), date(2026, 12, 31)),))
    second = ContractedPowerSchedule((_period(date(2026, 1, 1), date(2026, 12, 31), NEW),))
    for offset, schedule, targets in ((0, first, ORIGINAL), (5, second, NEW)):
        archive.register_configuration_epoch(
            namespace="meter-a",
            source_id="sensor.grid",
            positive_means_import=True,
            contractual_target_kw=targets[0],
            safety_margin_kw=0.0,
            block_targets_kw=targets,
            allow_provisional_tariff=False,
            contracted_power_schedule=schedule,
            effective_utc=start + timedelta(minutes=offset),
        )
    resolved = archive.resolve_configuration("meter-a", start, start + timedelta(minutes=15))
    assert resolved.status is ConfigurationStatus.TARGET_MIXED
