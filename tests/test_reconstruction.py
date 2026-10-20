"""Controlled reconstruction safety-policy tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from custom_components.si_grid_monitor.archive import ArchiveRecord, QuarterArchive
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
