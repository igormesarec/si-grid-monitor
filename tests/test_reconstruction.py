"""Controlled reconstruction safety-policy tests."""

import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from custom_components.si_grid_monitor.archive import (
    ArchiveRecord,
    QuarterArchive,
    archive_record_from_quarter,
    tariff_for_configuration,
)
from custom_components.si_grid_monitor.contracted_power import (
    ContractedPowerPeriod,
    ContractedPowerSchedule,
)
from custom_components.si_grid_monitor.engine import CompletedQuarter, DataQuality
from custom_components.si_grid_monitor.reconstruction import (
    audit_summary,
    plan_reconstruction,
)


def _record(start: datetime, quality: str, coverage: float) -> ArchiveRecord:
    return ArchiveRecord(
        namespace="meter-a",
        start_utc=start,
        end_utc=start + timedelta(minutes=15),
        import_kwh=0.2,
        export_kwh=0.1,
        signed_average_kw=0.4,
        import_demand_kw=0.8,
        coverage_seconds=coverage,
        gap_seconds=900 - coverage,
        quality=quality,
        provenance="user_confirmed_recorder_reconstruction",
        source_id="sensor.grid",
        source_epoch=1,
        configuration_status="known",
        contractual_target_kw=3.5,
        safety_margin_kw=0,
        operational_target_kw=3.5,
        utilization_pct=0.8 / 3.5 * 100,
        exceeded=False,
        excess_kw=0,
        contractual_status="confirmed",
    )


def _mapping(record: ArchiveRecord) -> dict[str, object]:
    return {
        "start_utc": record.start_utc.isoformat(),
        "quality": record.quality,
        "coverage_seconds": record.coverage_seconds,
        "import_kwh": record.import_kwh,
    }


def test_dry_run_is_idempotent_and_protects_stronger_records() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    measured = _record(start, "measured_aligned", 900)
    candidate = _record(start, "reconstructed", 900)
    missing = _record(start + timedelta(minutes=15), "reconstructed", 900)
    decisions = plan_reconstruction([_mapping(measured)], [candidate, missing])
    assert [item.action for item in decisions] == ["skip", "insert"]
    assert audit_summary(decisions) == {
        "candidate_count": 2,
        "insert_count": 1,
        "improve_count": 0,
        "skip_count": 1,
        "contractually_confirmed_count": 1,
        "contractually_unconfirmed_count": 0,
    }
    assert (
        plan_reconstruction([_mapping(candidate), _mapping(missing)], [candidate, missing])[
            0
        ].action
        == "skip"
    )


def test_only_better_incomplete_coverage_can_replace_equal_quality() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    old = _record(start, "incomplete", 300)
    better = replace(old, coverage_seconds=600, gap_seconds=300, import_kwh=0.25)
    worse = replace(old, coverage_seconds=200, gap_seconds=700)
    assert plan_reconstruction([_mapping(old)], [better])[0].action == "improve"
    assert plan_reconstruction([_mapping(old)], [worse])[0].action == "skip"


def test_unknown_contract_remains_unconfirmed_even_with_valid_energy() -> None:
    start = datetime(2025, 12, 31, tzinfo=UTC)
    candidate = replace(
        _record(start, "reconstructed", 900),
        configuration_status="target_unknown",
        contractual_target_kw=None,
        operational_target_kw=None,
        utilization_pct=None,
        exceeded=None,
        excess_kw=None,
        contractual_status="unknown_configuration",
    )
    summary = audit_summary(plan_reconstruction([], [candidate]))
    assert summary["contractually_confirmed_count"] == 0
    assert summary["contractually_unconfirmed_count"] == 1


def test_confirmed_apply_creates_backup_and_revision_without_downgrade(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "archive.db")
    archive.open()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    archive.register_configuration_epoch(
        namespace="meter-a",
        source_id="sensor.grid",
        positive_means_import=True,
        contractual_target_kw=3.5,
        safety_margin_kw=0,
        effective_utc=start - timedelta(days=1),
    )
    original = _record(start, "incomplete", 300)
    archive.upsert_quarter(original)
    improved = replace(
        original,
        quality="reconstructed",
        coverage_seconds=900,
        gap_seconds=0,
        import_kwh=0.25,
    )
    job_id = archive.begin_reconstruction_job(
        "meter-a",
        start,
        start + timedelta(minutes=15),
        "sensor.grid",
        mode="confirmed_reconstruction",
        summary={"candidate_count": 1},
    )
    backup = archive.backup(tmp_path / "before.db")
    backup_id = archive.register_backup("meter-a", job_id, backup)
    assert archive.apply_reconstructed_record(job_id, improved, reason="better coverage")
    archive.finish_reconstruction_job(job_id, "completed", {"applied_count": 1})
    row = archive.list_quarters("meter-a", start, start + timedelta(minutes=15))[0]
    assert row["quality"] == "reconstructed"
    with archive._lock:
        revision = archive._db.execute(  # type: ignore[union-attr]
            "SELECT original_json,replacement_json FROM quarter_revisions WHERE job_id=?",
            (job_id,),
        ).fetchone()
        stored_backup = archive._db.execute(  # type: ignore[union-attr]
            "SELECT filename FROM archive_backups WHERE backup_id=?", (backup_id,)
        ).fetchone()
    assert '"quality": "incomplete"' in revision["original_json"]
    assert '"quality": "reconstructed"' in revision["replacement_json"]
    assert stored_backup["filename"] == "before.db"
    # A weaker retry cannot overwrite the reconstructed record.
    assert not archive.apply_reconstructed_record(
        job_id, replace(original, coverage_seconds=100, gap_seconds=800), reason="retry"
    )


def _job(archive: QuarterArchive, start: datetime) -> str:
    archive.register_configuration_epoch(
        namespace="meter-a",
        source_id="sensor.grid",
        positive_means_import=True,
        contractual_target_kw=3.5,
        safety_margin_kw=0,
        effective_utc=start - timedelta(days=1),
    )
    return archive.begin_reconstruction_job(
        "meter-a",
        start,
        start + timedelta(hours=1),
        "sensor.grid",
        mode="confirmed_reconstruction",
        summary={"candidate_count": 1},
    )


def _decision(archive: QuarterArchive, start: datetime, candidate: ArchiveRecord):
    rows = archive.list_quarters("meter-a", start, start + timedelta(minutes=15))
    return plan_reconstruction(rows, [candidate])[0]


def _targets(value: float | tuple[float, float, float, float, float]) -> tuple[float, ...]:
    return (value,) * 5 if isinstance(value, (int, float)) else value


def _schedule(
    *,
    target_2026: float | tuple[float, float, float, float, float] = 3.5,
    target_2027: float | tuple[float, float, float, float, float] = 4.7,
) -> ContractedPowerSchedule:
    return ContractedPowerSchedule(
        (
            ContractedPowerPeriod(
                date(2026, 1, 1), date(2026, 12, 31), _targets(target_2026), "2026 assignment"
            ),
            ContractedPowerPeriod(
                date(2027, 1, 1), date(2027, 12, 31), _targets(target_2027), "2027 assignment"
            ),
        )
    )


def _scheduled_record(
    archive: QuarterArchive, start: datetime, schedule: ContractedPowerSchedule
) -> ArchiveRecord:
    epoch = archive.register_configuration_epoch(
        namespace="meter-a",
        source_id="sensor.grid",
        positive_means_import=True,
        contractual_target_kw=schedule.periods[0].block_targets_kw[0],
        safety_margin_kw=0,
        contracted_power_schedule=schedule,
        effective_utc=datetime(2025, 12, 1, tzinfo=UTC),
    )
    configuration = archive.resolve_configuration("meter-a", start, start + timedelta(minutes=15))
    quarter = CompletedQuarter(
        start_utc=start,
        end_utc=start + timedelta(minutes=15),
        import_kwh=0.2,
        export_kwh=0.1,
        signed_net_kwh=0.1,
        signed_average_kw=0.4,
        import_demand_kw=0.8,
        coverage_seconds=900,
        gap_seconds=0,
        quality=DataQuality.RECONSTRUCTED,
        source_id="sensor.grid|positive_means_import=True",
    )
    record = archive_record_from_quarter(
        namespace="meter-a",
        quarter=quarter,
        configuration=configuration,
        provenance="user_confirmed_recorder_reconstruction",
        tariff=tariff_for_configuration(start, configuration),
    )
    assert record.source_epoch == epoch.epoch
    return record


def _scheduled_job(archive: QuarterArchive, start: datetime) -> str:
    return archive.begin_reconstruction_job(
        "meter-a",
        start,
        start + timedelta(minutes=15),
        "sensor.grid",
        mode="confirmed_reconstruction",
        summary={"candidate_count": 1},
    )


def test_reconstruction_revalidates_exact_dated_assignment_and_block_target(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "archive.db")
    archive.open()
    schedule = _schedule(target_2026=3.5, target_2027=4.7)
    start = datetime(2027, 1, 4, 8, tzinfo=UTC)
    candidate = _scheduled_record(archive, start, schedule)
    assert candidate.contractual_target_kw == 4.7
    stale_2026_target = replace(
        candidate,
        contractual_target_kw=3.5,
        operational_target_kw=3.5,
        target_effective_from="2026-01-01",
        target_effective_to="2026-12-31",
        target_provenance="2026 assignment",
    )
    assert not archive.apply_reconstructed_record(
        _scheduled_job(archive, start), stale_2026_target, reason="stale dated assignment"
    )
    assert archive.apply_reconstructed_record(
        _scheduled_job(archive, start), candidate, reason="exact 2027 assignment"
    )


def test_reconstruction_rejects_another_blocks_target_from_same_assignment(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "archive.db")
    archive.open()
    start = datetime(2027, 1, 4, 8, tzinfo=UTC)
    schedule = _schedule(target_2027=(3.1, 3.2, 3.3, 3.4, 3.5))
    candidate = _scheduled_record(archive, start, schedule)
    wrong_target = next(
        target
        for index, target in enumerate(schedule.periods[1].block_targets_kw, start=1)
        if index != candidate.tariff_block
    )
    wrong_block_value = replace(
        candidate,
        contractual_target_kw=wrong_target,
        operational_target_kw=wrong_target,
    )
    assert not archive.apply_reconstructed_record(
        _scheduled_job(archive, start), wrong_block_value, reason="wrong block target"
    )


def test_reconstruction_rejects_audit_plan_after_configuration_schedule_changes(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "archive.db")
    archive.open()
    start = datetime(2027, 2, 1, 8, tzinfo=UTC)
    candidate = _scheduled_record(archive, start, _schedule(target_2027=4.7))
    archive.register_configuration_epoch(
        namespace="meter-a",
        source_id="sensor.grid",
        positive_means_import=True,
        contractual_target_kw=3.5,
        safety_margin_kw=0,
        contracted_power_schedule=_schedule(target_2027=5.1),
        effective_utc=start - timedelta(days=1),
    )
    assert not archive.apply_reconstructed_record(
        _scheduled_job(archive, start), candidate, reason="stale audit schedule"
    )
    assert archive.list_quarters("meter-a", start, start + timedelta(minutes=15)) == []


def test_stale_audit_cannot_overwrite_newer_live_evidence(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "archive.db")
    archive.open()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    old = _record(start, "incomplete", 300)
    archive.upsert_quarter(old)
    candidate = replace(old, quality="reconstructed", coverage_seconds=900, gap_seconds=0)
    decision = _decision(archive, start, candidate)
    archive.upsert_quarter(
        replace(old, provenance="live_engine", coverage_seconds=700, gap_seconds=200)
    )
    assert not archive.apply_reconstructed_record(
        _job(archive, start),
        candidate,
        reason=decision.reason,
        expected_fingerprint=decision.expected_fingerprint,
        planned_action=decision.action,
    )
    row = archive.list_quarters("meter-a", start, start + timedelta(minutes=15))[0]
    assert row["provenance"] == "live_engine"
    assert row["coverage_seconds"] == 700


def test_stale_audit_detects_measurement_change_with_same_quality(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "archive.db")
    archive.open()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    old = _record(start, "incomplete", 300)
    archive.upsert_quarter(old)
    candidate = replace(old, quality="reconstructed", coverage_seconds=900, gap_seconds=0)
    decision = _decision(archive, start, candidate)
    archive.upsert_quarter(replace(old, import_kwh=0.27))
    assert not archive.apply_reconstructed_record(
        _job(archive, start),
        candidate,
        reason=decision.reason,
        expected_fingerprint=decision.expected_fingerprint,
        planned_action="improve",
    )
    assert archive.list_quarters("meter-a", start, start + timedelta(minutes=15))[0][
        "import_kwh"
    ] == pytest.approx(0.27)


def test_quality_promotion_between_audit_and_apply_rejects_stale_plan(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "archive.db")
    archive.open()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    old = _record(start, "incomplete", 300)
    archive.upsert_quarter(old)
    candidate = replace(old, quality="reconstructed", coverage_seconds=900, gap_seconds=0)
    decision = _decision(archive, start, candidate)
    archive.upsert_quarter(
        replace(old, quality="measured_aligned", coverage_seconds=900, gap_seconds=0)
    )
    assert not archive.apply_reconstructed_record(
        _job(archive, start),
        candidate,
        reason=decision.reason,
        expected_fingerprint=decision.expected_fingerprint,
        planned_action="improve",
    )


def test_configuration_epoch_change_inside_quarter_rejects_apply(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "archive.db")
    archive.open()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    old = _record(start, "incomplete", 300)
    archive.upsert_quarter(old)
    candidate = replace(old, quality="reconstructed", coverage_seconds=900, gap_seconds=0)
    decision = _decision(archive, start, candidate)
    job = _job(archive, start)
    archive.register_configuration_epoch(
        namespace="meter-a",
        source_id="sensor.replacement",
        positive_means_import=True,
        contractual_target_kw=4.2,
        safety_margin_kw=0,
        effective_utc=start + timedelta(minutes=10),
    )
    assert not archive.apply_reconstructed_record(
        job,
        candidate,
        reason=decision.reason,
        expected_fingerprint=decision.expected_fingerprint,
        planned_action="improve",
    )
    assert (
        archive.list_quarters("meter-a", start, start + timedelta(minutes=15))[0]["quality"]
        == "incomplete"
    )


def test_equal_quality_requires_more_coverage_and_never_replaces_live(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "archive.db")
    archive.open()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    old = _record(start, "incomplete", 300)
    archive.upsert_quarter(old)
    more = replace(old, coverage_seconds=600, gap_seconds=300)
    decision = _decision(archive, start, more)
    assert archive.apply_reconstructed_record(
        _job(archive, start),
        more,
        reason=decision.reason,
        expected_fingerprint=decision.expected_fingerprint,
        planned_action="improve",
    )
    less = replace(old, coverage_seconds=500, gap_seconds=400)
    assert not archive.apply_reconstructed_record(_job(archive, start), less, reason="less")
    archive.upsert_quarter(
        replace(more, provenance="live_engine", coverage_seconds=700, gap_seconds=200)
    )
    assert not archive.apply_reconstructed_record(
        _job(archive, start),
        replace(more, coverage_seconds=800, gap_seconds=100),
        reason="equal-quality live evidence",
    )


@pytest.mark.parametrize(
    "failure",
    [
        sqlite3.IntegrityError("revision failed"),
        sqlite3.OperationalError("database or disk is full"),
        sqlite3.OperationalError("attempt to write a readonly database"),
    ],
)
def test_quarter_and_revision_roll_back_together_on_failure(
    tmp_path, monkeypatch, failure: Exception
) -> None:
    archive = QuarterArchive(tmp_path / "archive.db")
    archive.open()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    old = _record(start, "incomplete", 300)
    archive.upsert_quarter(old)
    candidate = replace(old, quality="reconstructed", coverage_seconds=900, gap_seconds=0)
    decision = _decision(archive, start, candidate)

    def fail_revision(self, point: str) -> None:
        if point == "before_revision_insert":
            raise failure

    monkeypatch.setattr(QuarterArchive, "_reconstruction_checkpoint", fail_revision)
    with pytest.raises(type(failure), match=str(failure)):
        archive.apply_reconstructed_record(
            _job(archive, start),
            candidate,
            reason=decision.reason,
            expected_fingerprint=decision.expected_fingerprint,
            planned_action="improve",
        )
    row = archive.list_quarters("meter-a", start, start + timedelta(minutes=15))[0]
    assert row["quality"] == "incomplete"
    assert row["coverage_seconds"] == 300
    with archive._lock:
        assert archive._db.execute("SELECT COUNT(*) FROM quarter_revisions").fetchone()[0] == 0


def test_interrupted_multi_quarter_apply_is_atomic_per_record_and_namespaced(
    tmp_path, monkeypatch
) -> None:
    archive = QuarterArchive(tmp_path / "archive.db")
    archive.open()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    first = _record(start, "incomplete", 300)
    second = _record(start + timedelta(minutes=15), "incomplete", 300)
    other = replace(_record(start, "measured_aligned", 900), namespace="meter-b")
    for record in (first, second, other):
        archive.upsert_quarter(record)
    first_candidate = replace(first, quality="reconstructed", coverage_seconds=900, gap_seconds=0)
    second_candidate = replace(second, quality="reconstructed", coverage_seconds=900, gap_seconds=0)
    first_decision = _decision(archive, start, first_candidate)
    second_decision = _decision(archive, start + timedelta(minutes=15), second_candidate)
    job = _job(archive, start)
    assert archive.apply_reconstructed_record(
        job,
        first_candidate,
        reason=first_decision.reason,
        expected_fingerprint=first_decision.expected_fingerprint,
        planned_action="improve",
    )

    def interrupt(self, point: str) -> None:
        raise RuntimeError("interrupted")

    monkeypatch.setattr(QuarterArchive, "_reconstruction_checkpoint", interrupt)
    with pytest.raises(RuntimeError, match="interrupted"):
        archive.apply_reconstructed_record(
            job,
            second_candidate,
            reason=second_decision.reason,
            expected_fingerprint=second_decision.expected_fingerprint,
            planned_action="improve",
        )
    assert [
        row["quality"]
        for row in archive.list_quarters("meter-a", start, start + timedelta(minutes=30))
    ] == ["reconstructed", "incomplete"]
    assert (
        archive.list_quarters("meter-b", start, start + timedelta(minutes=15))[0]["quality"]
        == "measured_aligned"
    )
