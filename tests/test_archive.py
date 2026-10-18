"""SQLite archive, migration, provenance and aggregation tests."""

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.si_grid_monitor.archive import (
    ArchiveRecord,
    ConfigurationResolution,
    ConfigurationStatus,
    QuarterArchive,
    archive_record_from_quarter,
)
from custom_components.si_grid_monitor.engine import CompletedQuarter, DataQuality
from custom_components.si_grid_monitor.tariffs import SlovenianTariffCalendar


def record(
    start: datetime,
    *,
    import_kwh: float = 1.0,
    export_kwh: float = 2 / 3,
    quality: str = "reconstructed",
    simulation: bool = False,
    configuration_status: str = "known",
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
        configuration_status=configuration_status,
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
    assert archive.schema_version == 3
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


def test_configuration_epochs_resolve_historical_source_sign_and_target(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "archive.db")
    archive.open()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    first = archive.register_configuration_epoch(
        namespace="meter-a",
        source_id="sensor.old_grid",
        positive_means_import=False,
        contractual_target_kw=4.6,
        safety_margin_kw=0.1,
        effective_utc=start,
    )
    second = archive.register_configuration_epoch(
        namespace="meter-a",
        source_id="sensor.new_grid",
        positive_means_import=True,
        contractual_target_kw=5.0,
        safety_margin_kw=0.0,
        effective_utc=start + timedelta(hours=1),
    )
    assert (first.epoch, second.epoch) == (1, 2)
    resolved = archive.resolve_configuration(
        "meter-a", start + timedelta(minutes=15), start + timedelta(minutes=30)
    )
    assert resolved.status == ConfigurationStatus.KNOWN
    assert resolved.source_id == "sensor.old_grid"
    assert not resolved.positive_means_import
    assert resolved.contractual_target_kw == 4.6

    before_history = archive.resolve_configuration("meter-a", start - timedelta(minutes=15), start)
    assert before_history.status == ConfigurationStatus.SOURCE_UNKNOWN
    assert before_history.contractual_target_kw is None


def test_target_change_inside_quarter_is_explicit_and_never_exceeded(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "archive.db")
    archive.open()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    archive.register_configuration_epoch(
        namespace="meter-a",
        source_id="sensor.grid",
        positive_means_import=True,
        contractual_target_kw=4.0,
        safety_margin_kw=0.0,
        effective_utc=start,
    )
    archive.register_configuration_epoch(
        namespace="meter-a",
        source_id="sensor.grid",
        positive_means_import=True,
        contractual_target_kw=6.0,
        safety_margin_kw=0.0,
        effective_utc=start + timedelta(minutes=7),
    )
    resolution = archive.resolve_configuration("meter-a", start, start + timedelta(minutes=15))
    assert resolution.status == ConfigurationStatus.TARGET_MIXED
    quarter = CompletedQuarter(
        start_utc=start,
        end_utc=start + timedelta(minutes=15),
        import_kwh=1.25,
        export_kwh=0.0,
        signed_net_kwh=1.25,
        import_demand_kw=5.0,
        signed_average_kw=5.0,
        coverage_seconds=900,
        gap_seconds=0,
        quality=DataQuality.RECONSTRUCTED,
        source_id="sensor.grid",
    )
    row = archive_record_from_quarter(
        namespace="meter-a",
        quarter=quarter,
        configuration=resolution,
        provenance="live_reconstructed",
    )
    assert row.contractual_target_kw is None
    assert row.safety_margin_kw is None
    assert row.utilization_pct is None
    assert row.exceeded is None


def test_record_uses_immutable_configuration_snapshot() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    quarter = CompletedQuarter(
        start_utc=start,
        end_utc=start + timedelta(minutes=15),
        import_kwh=1.0,
        export_kwh=0.0,
        signed_net_kwh=1.0,
        import_demand_kw=4.0,
        signed_average_kw=4.0,
        coverage_seconds=900,
        gap_seconds=0,
        quality=DataQuality.RECONSTRUCTED,
        source_id="sensor.old",
    )
    applied = ConfigurationResolution(
        status=ConfigurationStatus.KNOWN,
        source_id="sensor.old",
        positive_means_import=False,
        source_epoch=4,
        contractual_target_kw=4.6,
        safety_margin_kw=0.1,
    )
    record_value = archive_record_from_quarter(
        namespace="meter-a",
        quarter=quarter,
        configuration=applied,
        provenance="live_reconstructed",
    )
    later_settings = {"target": 9.0, "source": "sensor.new"}
    assert later_settings["target"] != record_value.contractual_target_kw
    assert record_value.contractual_target_kw == 4.6
    assert record_value.source_id == "sensor.old"
    assert record_value.source_epoch == 4


def test_summary_excludes_incomplete_contractual_statistics(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "archive.db")
    archive.open()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    archive.upsert_quarter(record(start, import_kwh=1.0))
    archive.upsert_quarter(
        record(
            start + timedelta(minutes=15),
            import_kwh=2.0,
            export_kwh=0.5,
            quality="incomplete",
        )
    )
    summary = archive.summarize("meter-a", start, start + timedelta(hours=1))
    assert summary.valid_count == 1
    assert summary.incomplete_count == 1
    assert summary.import_kwh == pytest.approx(1.0)
    assert summary.partial_observed_import_kwh == pytest.approx(2.0)
    assert summary.partial_observed_export_kwh == pytest.approx(0.5)
    assert summary.maximum_import_demand_kw == pytest.approx(4.0)
    assert summary.average_import_demand_kw == pytest.approx(4.0)
    assert summary.exceeded_count == 0


def test_unknown_configuration_cannot_create_false_exceedance(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "archive.db")
    archive.open()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    archive.upsert_quarter(
        record(
            start,
            import_kwh=3.0,
            configuration_status="legacy_unverified",
        )
    )
    summary = archive.summarize("meter-a", start, start + timedelta(hours=1))
    assert summary.valid_count == 0
    assert summary.unknown_configuration_count == 1
    assert summary.exceeded_count == 0
    assert summary.maximum_import_demand_kw is None
    assert summary.partial_observed_import_kwh == pytest.approx(3.0)


def test_known_source_with_unknown_historical_target_keeps_exceedance_unknown() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    quarter = CompletedQuarter(
        start_utc=start,
        end_utc=start + timedelta(minutes=15),
        import_kwh=2.0,
        export_kwh=0.0,
        signed_net_kwh=2.0,
        import_demand_kw=8.0,
        signed_average_kw=8.0,
        coverage_seconds=900,
        gap_seconds=0,
        quality=DataQuality.RECONSTRUCTED,
        source_id="sensor.grid",
    )
    record_value = archive_record_from_quarter(
        namespace="meter-a",
        quarter=quarter,
        configuration=ConfigurationResolution(
            status=ConfigurationStatus.TARGET_UNKNOWN,
            source_id="sensor.grid",
            positive_means_import=True,
            source_epoch=1,
        ),
        provenance="recorder_reconstructed",
    )
    assert record_value.import_demand_kw == 8.0
    assert record_value.contractual_target_kw is None
    assert record_value.utilization_pct is None
    assert record_value.exceeded is None
    assert record_value.excess_kw is None


def test_v1_migration_marks_legacy_rows_unverified_and_suppresses_exceedance(tmp_path) -> None:
    """Previously stored target/sign assumptions are retained only as unaudited data."""

    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE source_epochs(
          namespace TEXT NOT NULL, epoch INTEGER NOT NULL,
          source_id TEXT NOT NULL, positive_means_import INTEGER NOT NULL,
          effective_utc TEXT NOT NULL, PRIMARY KEY(namespace,epoch));
        CREATE TABLE quarters(
          namespace TEXT NOT NULL,start_utc TEXT NOT NULL,end_utc TEXT NOT NULL,
          start_local TEXT NOT NULL,utc_offset_seconds INTEGER NOT NULL,
          fold INTEGER NOT NULL,import_kwh REAL NOT NULL,export_kwh REAL NOT NULL,
          signed_average_kw REAL NOT NULL,import_demand_kw REAL NOT NULL,
          coverage_seconds REAL NOT NULL,gap_seconds REAL NOT NULL,
          quality TEXT NOT NULL,provenance TEXT NOT NULL,source_id TEXT NOT NULL,
          source_epoch INTEGER NOT NULL,contractual_target_kw REAL,
          safety_margin_kw REAL NOT NULL,operational_target_kw REAL,
          utilization_pct REAL,exceeded INTEGER,excess_kw REAL,
          simulation INTEGER NOT NULL DEFAULT 0,tariff_block INTEGER,
          tariff_rule_version TEXT,created_utc TEXT NOT NULL,
          PRIMARY KEY(namespace,start_utc));
        CREATE TABLE checkpoints(
          namespace TEXT PRIMARY KEY,payload_json TEXT NOT NULL,updated_utc TEXT NOT NULL);
        PRAGMA user_version=1;
        """
    )
    start = datetime(2026, 1, 1, tzinfo=UTC)
    connection.execute(
        """INSERT INTO source_epochs VALUES(?,?,?,?,?)""",
        ("meter-a", 1, "sensor.grid", 1, start.isoformat()),
    )
    connection.execute(
        """INSERT INTO quarters VALUES(
           ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "meter-a",
            start.isoformat(),
            (start + timedelta(minutes=15)).isoformat(),
            "2026-01-01T01:00:00+01:00",
            3600,
            0,
            2.0,
            0.0,
            8.0,
            8.0,
            900.0,
            0.0,
            "reconstructed",
            "recorder_reconstructed",
            "sensor.grid",
            1,
            4.6,
            0.0,
            4.6,
            100 * 8 / 4.6,
            1,
            3.4,
            0,
            None,
            None,
            start.isoformat(),
        ),
    )
    connection.commit()
    connection.close()

    archive = QuarterArchive(path)
    archive.open()
    assert archive.schema_version == 3
    migrated = archive.list_quarters("meter-a", start, start + timedelta(hours=1))[0]
    assert migrated["configuration_status"] == "legacy_unverified"
    assert archive.list_configuration_epochs("meter-a")[0].contractual_target_kw is None
    summary = archive.summarize("meter-a", start, start + timedelta(hours=1))
    assert summary.valid_count == 0
    assert summary.unknown_configuration_count == 1
    assert summary.exceeded_count == 0
    assert summary.maximum_import_demand_kw is None
    assert summary.partial_observed_import_kwh == pytest.approx(2.0)
    archive.close()


def test_tariff_and_selected_block_target_are_immutable_archive_fields(tmp_path) -> None:
    start = datetime(2027, 1, 4, 11, 0, tzinfo=UTC)  # 12:00 local, higher working B2
    quarter = CompletedQuarter(
        start_utc=start,
        end_utc=start + timedelta(minutes=15),
        import_kwh=1.0,
        export_kwh=0.0,
        signed_net_kwh=1.0,
        import_demand_kw=4.0,
        signed_average_kw=4.0,
        coverage_seconds=900,
        gap_seconds=0,
        quality=DataQuality.RECONSTRUCTED,
        source_id="sensor.grid",
    )
    tariff = SlovenianTariffCalendar().classify(start)
    archived = archive_record_from_quarter(
        namespace="meter-a",
        quarter=quarter,
        configuration=ConfigurationResolution(
            status=ConfigurationStatus.KNOWN,
            source_id="sensor.grid",
            source_epoch=2,
            contractual_target_kw=3.0,
            safety_margin_kw=0.1,
            block_targets_kw=(3.0, 4.0, 5.0, 6.0, 7.0),
        ),
        provenance="live_reconstructed",
        tariff=tariff,
    )
    assert tariff.block == 2
    assert archived.contractual_target_kw == 4.0
    assert archived.tariff_rule_version == "SI-URO-2027"
    assert archived.tariff_rule_status == "official"
    assert archived.tariff_calendar_year == 2027
    assert archived.tariff_season == "higher"
    assert archived.tariff_day_type == "working"

    archive = QuarterArchive(tmp_path / "tariff.db")
    archive.open()
    archive.upsert_quarter(archived)
    row = archive.list_quarters("meter-a", start, start + timedelta(hours=1))[0]
    assert row["tariff_block"] == 2
    assert row["contractual_target_kw"] == 4.0
    assert row["tariff_rule_status"] == "official"
    archive.close()


def test_v2_to_v3_migration_copies_common_target_to_all_blocks(tmp_path) -> None:
    path = tmp_path / "v2.db"
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE source_epochs(
          namespace TEXT NOT NULL,epoch INTEGER NOT NULL,source_id TEXT NOT NULL,
          positive_means_import INTEGER NOT NULL,effective_utc TEXT NOT NULL,
          contractual_target_kw REAL,safety_margin_kw REAL,
          PRIMARY KEY(namespace,epoch));
        CREATE TABLE quarters(
          namespace TEXT NOT NULL,start_utc TEXT NOT NULL,end_utc TEXT NOT NULL,
          start_local TEXT NOT NULL,utc_offset_seconds INTEGER NOT NULL,fold INTEGER NOT NULL,
          import_kwh REAL NOT NULL,export_kwh REAL NOT NULL,signed_average_kw REAL NOT NULL,
          import_demand_kw REAL NOT NULL,coverage_seconds REAL NOT NULL,gap_seconds REAL NOT NULL,
          quality TEXT NOT NULL,provenance TEXT NOT NULL,source_id TEXT,source_epoch INTEGER,
          configuration_status TEXT NOT NULL,contractual_target_kw REAL,safety_margin_kw REAL,
          operational_target_kw REAL,utilization_pct REAL,exceeded INTEGER,excess_kw REAL,
          simulation INTEGER NOT NULL DEFAULT 0,tariff_block INTEGER,
          tariff_rule_version TEXT,created_utc TEXT NOT NULL,
          PRIMARY KEY(namespace,start_utc));
        CREATE TABLE checkpoints(
          namespace TEXT PRIMARY KEY,payload_json TEXT NOT NULL,updated_utc TEXT NOT NULL);
        INSERT INTO source_epochs VALUES(
          'meter-a',1,'sensor.grid',1,'2026-01-01T00:00:00+00:00',4.8,0.0);
        PRAGMA user_version=2;
        """
    )
    db.commit()
    db.close()

    archive = QuarterArchive(path)
    archive.open()
    assert archive.schema_version == 3
    epoch = archive.list_configuration_epochs("meter-a")[0]
    assert epoch.block_targets_kw == (4.8, 4.8, 4.8, 4.8, 4.8)
    archive.close()


def test_unverified_tariff_never_creates_contractual_target_or_exceedance() -> None:
    start = datetime(2028, 1, 3, 11, 0, tzinfo=UTC)
    quarter = CompletedQuarter(
        start_utc=start,
        end_utc=start + timedelta(minutes=15),
        import_kwh=2.0,
        export_kwh=0.0,
        signed_net_kwh=2.0,
        import_demand_kw=8.0,
        signed_average_kw=8.0,
        coverage_seconds=900,
        gap_seconds=0,
        quality=DataQuality.RECONSTRUCTED,
        source_id="sensor.grid",
    )
    tariff = SlovenianTariffCalendar().classify(start)
    assert tariff.block is None
    archived = archive_record_from_quarter(
        namespace="meter-a",
        quarter=quarter,
        configuration=ConfigurationResolution(
            status=ConfigurationStatus.KNOWN,
            source_id="sensor.grid",
            source_epoch=1,
            contractual_target_kw=4.8,
            safety_margin_kw=0.0,
            block_targets_kw=(3.0, 4.0, 5.0, 6.0, 7.0),
        ),
        provenance="live_reconstructed",
        tariff=tariff,
    )
    assert archived.contractual_target_kw is None
    assert archived.utilization_pct is None
    assert archived.exceeded is None
    assert archived.excess_kw is None


def test_classifying_legacy_row_in_unverified_year_suppresses_old_exceedance(
    tmp_path,
) -> None:
    start = datetime(2028, 1, 3, 11, 0, tzinfo=UTC)
    archive = QuarterArchive(tmp_path / "unverified.db")
    archive.open()
    archive.upsert_quarter(record(start, import_kwh=2.0))

    changed = archive.classify_existing_quarters("meter-a", SlovenianTariffCalendar().classify)

    assert changed == 1
    row = archive.list_quarters("meter-a", start, start + timedelta(hours=1))[0]
    assert row["tariff_rule_status"] == "unverified"
    assert row["tariff_block"] is None
    assert row["exceeded"] is None
    assert row["excess_kw"] is None
    assert row["import_kwh"] == 2.0
    assert row["contractual_target_kw"] == 4.6
    archive.close()
