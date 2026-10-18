"""SQLite archive, migration, provenance and aggregation tests."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.si_grid_monitor.archive import ArchiveRecord, QuarterArchive


def record(
    start: datetime,
    *,
    import_kwh: float = 1.0,
    export_kwh: float = 2 / 3,
    quality: str = "reconstructed",
    simulation: bool = False,
) -> ArchiveRecord:
    demand = import_kwh / 0.25
    target = 4.6
    return ArchiveRecord(
        namespace="meter-a",
        start_utc=start,
        end_utc=start + timedelta(minutes=15),
        import_kwh=import_kwh,
        export_kwh=export_kwh,
        signed_average_kw=(import_kwh - export_kwh) / 0.25,
        import_demand_kw=demand,
        coverage_seconds=900,
        gap_seconds=0,
        quality=quality,
        provenance="live_reconstructed",
        source_id="sensor.grid",
        source_epoch=1,
        contractual_target_kw=target,
        safety_margin_kw=0,
        operational_target_kw=target,
        utilization_pct=100 * demand / target,
        exceeded=demand > target,
        excess_kw=max(0, demand - target),
        simulation=simulation,
    )


def test_schema_idempotence_import_only_storage_and_dst_context(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "archive.db")
    archive.open()
    assert archive.schema_version == 1
    start = datetime(2026, 10, 25, 0, 0, tzinfo=UTC)
    assert archive.upsert_quarter(record(start))
    assert not archive.upsert_quarter(record(start))
    rows = archive.list_quarters("meter-a", start, start + timedelta(hours=1))
    assert len(rows) == 1
    assert rows[0]["import_kwh"] == pytest.approx(1.0)
    assert rows[0]["export_kwh"] == pytest.approx(2 / 3)
    assert rows[0]["import_demand_kw"] == pytest.approx(4.0)
    assert rows[0]["signed_average_kw"] == pytest.approx(4 / 3)
    assert rows[0]["start_local"].endswith("+02:00")
    archive.close()

    reopened = QuarterArchive(tmp_path / "archive.db")
    reopened.open()
    assert len(reopened.list_quarters("meter-a", start, start + timedelta(hours=1))) == 1
    reopened.close()


def test_lower_quality_backfill_never_overwrites_better_record(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "archive.db")
    archive.open()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    archive.upsert_quarter(record(start, quality="measured_aligned"))
    assert not archive.upsert_quarter(record(start, import_kwh=0.1, quality="incomplete"))
    row = archive.list_quarters("meter-a", start, start + timedelta(hours=1))[0]
    assert row["import_kwh"] == pytest.approx(1.0)


def test_simulation_is_excluded_from_genuine_exceedance_summary(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "archive.db")
    archive.open()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    archive.upsert_quarter(record(start, import_kwh=2.0, simulation=True))
    archive.upsert_quarter(record(start + timedelta(minutes=15), import_kwh=1.5))
    summary = archive.summarize("meter-a", start, start + timedelta(hours=1))
    assert summary.valid_count == 1
    assert summary.exceeded_count == 1
    assert summary.maximum_import_demand_kw == pytest.approx(6.0)
    with_simulation = archive.summarize(
        "meter-a", start, start + timedelta(hours=1), include_simulation=True
    )
    assert with_simulation.valid_count == 2
    assert with_simulation.maximum_import_demand_kw == pytest.approx(8.0)
    assert with_simulation.exceeded_count == 1


def test_source_epochs_and_checkpoint_survive_restart(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "archive.db")
    archive.open()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    first = archive.register_source_epoch(
        namespace="meter-a",
        source_id="sensor.grid",
        positive_means_import=True,
        effective_utc=now,
    )
    same = archive.register_source_epoch(
        namespace="meter-a",
        source_id="sensor.grid",
        positive_means_import=True,
        effective_utc=now + timedelta(minutes=1),
    )
    reversed_epoch = archive.register_source_epoch(
        namespace="meter-a",
        source_id="sensor.grid",
        positive_means_import=False,
        effective_utc=now + timedelta(minutes=2),
    )
    assert (first, same, reversed_epoch) == (1, 1, 2)
    archive.save_checkpoint("meter-a", {"schema": 1, "import_kwh": 0.25})
    assert archive.load_checkpoint("meter-a") == {"schema": 1, "import_kwh": 0.25}
