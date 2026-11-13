"""Statistics metadata compatibility without coupling to Recorder storage."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.si_grid_monitor.archive import ArchiveRecord, QuarterArchive


def _record(namespace: str, start: datetime, import_kwh: float) -> ArchiveRecord:
    demand = import_kwh / 0.25
    return ArchiveRecord(
        namespace=namespace,
        start_utc=start,
        end_utc=start + timedelta(minutes=15),
        import_kwh=import_kwh,
        export_kwh=0.125,
        signed_average_kw=(import_kwh - 0.125) / 0.25,
        import_demand_kw=demand,
        coverage_seconds=900,
        gap_seconds=0,
        quality="measured_aligned",
        provenance="live_measured",
        source_id=f"sensor.{namespace}",
        source_epoch=1,
        configuration_status="known",
        contractual_target_kw=4.2,
        safety_margin_kw=0.2,
        operational_target_kw=4.0,
        utilization_pct=100 * demand / 4.2,
        exceeded=demand > 4.2,
        excess_kw=max(0, demand - 4.2),
        confirmed_exceeded=demand > 4.2,
    )


def test_archive_is_independent_of_absent_home_assistant_statistics(tmp_path) -> None:
    """Removing a Recorder series cannot remove the integration-owned archive."""

    path = tmp_path / "statistics-independent.sqlite"
    start = datetime(2026, 10, 25, 0, 0, tzinfo=UTC)
    archive = QuarterArchive(path)
    archive.open()
    assert archive.upsert_quarter(_record("meter-a", start, 0.75))
    archive.save_checkpoint("meter-a", {"quarter_start_utc": start.isoformat()})
    archive.close()

    # There is deliberately no Home Assistant Recorder/statistics fixture or
    # table. Reopening the integration-owned database preserves authoritative
    # quarter and recovery evidence.
    reopened = QuarterArchive(path)
    reopened.open()
    assert reopened.schema_version == 8
    rows = reopened.list_quarters("meter-a", start, start + timedelta(hours=1))
    assert len(rows) == 1
    assert rows[0]["import_kwh"] == pytest.approx(0.75)
    assert rows[0]["contractual_target_kw"] == pytest.approx(4.2)
    assert rows[0]["quality"] == "measured_aligned"
    assert reopened.load_checkpoint("meter-a") == {"quarter_start_utc": start.isoformat()}
    reopened.close()


def test_statistics_cleanup_cannot_cross_meter_archive_namespaces(tmp_path) -> None:
    path = tmp_path / "two-meter-statistics-independent.sqlite"
    start = datetime(2026, 4, 2, 10, 0, tzinfo=UTC)
    archive = QuarterArchive(path)
    archive.open()
    archive.upsert_quarter(_record("meter-a", start, 0.25))
    archive.upsert_quarter(_record("meter-b", start, 0.50))

    rows_a = archive.list_quarters("meter-a", start, start + timedelta(hours=1))
    rows_b = archive.list_quarters("meter-b", start, start + timedelta(hours=1))
    assert [row["import_kwh"] for row in rows_a] == pytest.approx([0.25])
    assert [row["import_kwh"] for row in rows_b] == pytest.approx([0.50])
    archive.close()
