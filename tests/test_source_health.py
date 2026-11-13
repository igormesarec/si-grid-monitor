"""V1.0.6 durable source-health and quality-report regressions."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.si_grid_monitor.archive import ArchiveRecord, QuarterArchive
from custom_components.si_grid_monitor.source_health import (
    diagnostic_csv,
    incomplete_quarter_report,
    quality_report,
    source_health_report,
)


def _archive(tmp_path, name: str = "health.db") -> QuarterArchive:
    archive = QuarterArchive(tmp_path / name)
    archive.open()
    return archive


def _record(
    namespace: str, start: datetime, *, quality: str = "measured_aligned", coverage: float = 900
) -> ArchiveRecord:
    return ArchiveRecord(
        namespace=namespace,
        start_utc=start,
        end_utc=start + timedelta(minutes=15),
        import_kwh=0.1,
        export_kwh=0.0,
        signed_average_kw=0.4,
        import_demand_kw=0.4,
        coverage_seconds=coverage,
        gap_seconds=900 - coverage,
        quality=quality,
        provenance="test",
        source_id="sensor.grid",
        source_epoch=1,
        configuration_status="known",
        contractual_target_kw=4.2,
        safety_margin_kw=0.2,
        operational_target_kw=4.0,
        utilization_pct=9.52,
        exceeded=False,
        excess_kw=0.0,
        tariff_block=1,
        tariff_rule_version="test",
        tariff_rule_status="official",
        contractual_status="confirmed",
        confirmed_exceeded=False,
    )


def test_schema8_transition_only_persistence_and_meter_isolation(tmp_path) -> None:
    archive = _archive(tmp_path)
    start = datetime(2026, 10, 25, 2, 30, tzinfo=UTC)
    first = archive.transition_source_health(
        namespace="meter-a",
        source_epoch=1,
        source_id="sensor.grid",
        health_state="healthy",
        reason_code="valid_measurement",
        observed_utc=start,
        last_valid_sample_utc=start,
    )
    duplicate = archive.transition_source_health(
        namespace="meter-a",
        source_epoch=1,
        source_id="sensor.grid",
        health_state="healthy",
        reason_code="valid_measurement",
        observed_utc=start + timedelta(seconds=5),
        last_valid_sample_utc=start,
    )
    assert duplicate.incident_id == first.incident_id
    outage = archive.transition_source_health(
        namespace="meter-a",
        source_epoch=1,
        source_id="sensor.grid",
        health_state="unavailable",
        reason_code="source_state_unavailable",
        observed_utc=start + timedelta(seconds=20),
        last_valid_sample_utc=start,
    )
    archive.transition_source_health(
        namespace="meter-b",
        source_epoch=1,
        source_id="sensor.other",
        health_state="healthy",
        reason_code="valid_measurement",
        observed_utc=start,
        last_valid_sample_utc=start,
    )
    recovered = archive.transition_source_health(
        namespace="meter-a",
        source_epoch=1,
        source_id="sensor.grid",
        health_state="healthy",
        reason_code="valid_measurement",
        observed_utc=start + timedelta(seconds=50),
        last_valid_sample_utc=start + timedelta(seconds=50),
    )
    rows, total = archive.list_source_health_incidents(
        "meter-a", start - timedelta(seconds=1), start + timedelta(minutes=1), page_size=20
    )
    assert total == 3
    assert {row.incident_id for row in rows} == {
        first.incident_id,
        outage.incident_id,
        recovered.incident_id,
    }
    assert all(row.namespace == "meter-a" for row in rows)
    assert next(
        row for row in rows if row.incident_id == outage.incident_id
    ).ended_utc == start + timedelta(seconds=50)


def test_repeated_state_reports_remain_one_storage_interval(tmp_path) -> None:
    archive = _archive(tmp_path)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    first = None
    for second in range(1_000):
        item = archive.transition_source_health(
            namespace="meter",
            source_epoch=1,
            source_id="sensor.grid",
            health_state="unavailable",
            reason_code="source_state_unavailable",
            observed_utc=start + timedelta(seconds=second),
            last_valid_sample_utc=start,
        )
        first = first or item.incident_id
        assert item.incident_id == first
    rows, total = archive.list_source_health_incidents(
        "meter", start, start + timedelta(hours=1), page_size=200
    )
    assert total == 1
    assert len(rows) == 1


def test_open_incident_duration_is_unknown_and_not_quarter_gap(tmp_path) -> None:
    archive = _archive(tmp_path)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    archive.upsert_quarter(_record("meter", start, quality="incomplete", coverage=861.9))
    archive.transition_source_health(
        namespace="meter",
        source_epoch=1,
        source_id="sensor.grid",
        health_state="unavailable",
        reason_code="source_state_unavailable",
        observed_utc=start + timedelta(minutes=5),
        last_valid_sample_utc=start + timedelta(minutes=4),
    )
    report = source_health_report(
        archive,
        "meter",
        start,
        start + timedelta(minutes=15),
        now_utc=start + timedelta(minutes=10),
    )
    item = report["items"][0]
    assert item["duration_seconds"] is None
    assert item["observed_open_seconds"] == 300
    assert report["summary"]["quarter_record_missing_seconds"] == pytest.approx(38.1)
    assert report["summary"]["incident_duration_is_not_quarter_gap_seconds"] is True


def test_recurring_pattern_requires_two_dates_and_makes_no_causal_claim(tmp_path) -> None:
    archive = _archive(tmp_path)
    start = datetime(2026, 1, 1, 3, 35, tzinfo=UTC)
    for offset in (0, 1):
        observed = start + timedelta(days=offset)
        archive.transition_source_health(
            namespace="meter",
            source_epoch=1,
            source_id="sensor.solaredge_m1_ac_power",
            health_state="unavailable",
            reason_code="source_state_unavailable",
            observed_utc=observed,
            last_valid_sample_utc=observed - timedelta(seconds=30),
        )
        archive.transition_source_health(
            namespace="meter",
            source_epoch=1,
            source_id="sensor.solaredge_m1_ac_power",
            health_state="healthy",
            reason_code="valid_measurement",
            observed_utc=observed + timedelta(minutes=5),
            last_valid_sample_utc=observed + timedelta(minutes=5),
        )
    report = source_health_report(
        archive, "meter", start - timedelta(hours=1), start + timedelta(days=2)
    )
    pattern = report["recurring_patterns"][0]
    assert pattern["classification"] == "repeated_interruptions_observed"
    assert pattern["distinct_date_count"] == 2
    assert pattern["causal_interpretation"] is None


def test_quality_report_separates_quarter_and_time_coverage(tmp_path) -> None:
    archive = _archive(tmp_path)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    archive.upsert_quarter(_record("meter", start))
    archive.upsert_quarter(
        _record("meter", start + timedelta(minutes=15), quality="incomplete", coverage=450)
    )
    report = quality_report(
        archive,
        "meter",
        start,
        start + timedelta(hours=1),
        now_utc=start + timedelta(hours=1),
    )["summary"]
    assert report["expected_completed_monitored_quarters"] == 4
    assert report["valid_completed_quarters"] == 1
    assert report["missing_completed_monitored_quarters"] == 2
    assert report["quarter_completeness_pct"] == 25
    assert report["measurement_time_coverage_pct"] == pytest.approx(37.5)
    assert report["partial_observed_import_kwh"] == pytest.approx(0.1)


def test_csv_escapes_formula_text(tmp_path) -> None:
    archive = _archive(tmp_path)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    archive.transition_source_health(
        namespace="meter",
        source_epoch=1,
        source_id='=HYPERLINK("bad")',
        health_state="invalid_value",
        reason_code="source_value_rejected",
        observed_utc=start,
        last_valid_sample_utc=None,
    )
    report = source_health_report(
        archive, "meter", start - timedelta(seconds=1), start + timedelta(minutes=1)
    )
    payload = diagnostic_csv("incidents", report)
    assert "'=HYPERLINK" in payload


def test_incomplete_quarter_csv_is_bounded_evidence(tmp_path) -> None:
    archive = _archive(tmp_path)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    archive.upsert_quarter(_record("meter", start, quality="incomplete", coverage=450))
    archive.upsert_quarter(_record("meter", start + timedelta(minutes=15)))
    report = incomplete_quarter_report(archive, "meter", start, start + timedelta(hours=1))
    assert len(report["items"]) == 1
    assert report["items"][0]["quality"] == "incomplete"
    payload = diagnostic_csv("incomplete_quarters", report)
    assert "coverage_seconds" in payload
    assert "450.0" in payload


def test_filtered_quality_does_not_assign_missing_intervals_to_filter(tmp_path) -> None:
    archive = _archive(tmp_path)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    archive.upsert_quarter(_record("meter", start))
    summary = quality_report(
        archive,
        "meter",
        start,
        start + timedelta(hours=1),
        now_utc=start + timedelta(hours=1),
        tariff_block=1,
    )["summary"]
    assert summary["missing_completed_monitored_quarters"] is None
    assert summary["quarter_completeness_pct"] is None
    assert summary["missing_intervals_unclassified_when_filtered"] is True


@pytest.mark.parametrize(
    "failure_point",
    (
        "before_v8_schema_change",
        "after_source_health_table",
        "after_source_health_indexes",
        "before_v8_version_update",
    ),
)
def test_schema7_to_8_failure_rolls_back_then_retries(tmp_path, failure_point: str) -> None:
    path = tmp_path / "migration.db"
    initial = QuarterArchive(path)
    initial.open()
    initial.upsert_quarter(_record("meter", datetime(2026, 1, 1, tzinfo=UTC)))
    initial._db.execute("DROP TABLE source_health_incidents")
    initial._db.execute("PRAGMA user_version=7")
    initial._db.commit()
    initial.close()

    class FailingArchive(QuarterArchive):
        def _migration_checkpoint(self, point: str) -> None:
            if point == failure_point:
                raise RuntimeError("interrupted")

    failing = FailingArchive(path)
    with pytest.raises(RuntimeError, match="interrupted"):
        failing.open()
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 7
        assert connection.execute("SELECT COUNT(*) FROM quarters").fetchone()[0] == 1
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
                "AND name='source_health_incidents'"
            ).fetchone()[0]
            == 0
        )
    recovered = QuarterArchive(path)
    recovered.open()
    assert recovered.schema_version == 8
    assert (
        len(
            recovered.list_quarters(
                "meter", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)
            )
        )
        == 1
    )
