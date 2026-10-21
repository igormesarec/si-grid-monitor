"""HISTORY pagination, quality, DST and archive-preservation tests."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from custom_components.si_grid_monitor.archive import ArchiveRecord, QuarterArchive
from custom_components.si_grid_monitor.engine import LJUBLJANA, quarter_starts_for_local_day
from custom_components.si_grid_monitor.history import HistoryQuery, history_report


def _record(start: datetime, index: int = 0, **changes: object) -> ArchiveRecord:
    value = 0.1 + index / 1000
    base = ArchiveRecord(
        namespace="meter-a",
        start_utc=start,
        end_utc=start + timedelta(minutes=15),
        import_kwh=value,
        export_kwh=0.02,
        signed_average_kw=(value - 0.02) * 4,
        import_demand_kw=value * 4,
        coverage_seconds=900,
        gap_seconds=0,
        quality="reconstructed",
        provenance="recorder_reconstructed",
        source_id="sensor.grid",
        source_epoch=1,
        configuration_status="known",
        contractual_target_kw=3.5,
        safety_margin_kw=0,
        operational_target_kw=3.5,
        utilization_pct=value * 400 / 3.5,
        exceeded=False,
        excess_kw=0,
        tariff_block=(index % 5) + 1,
        tariff_rule_version="si-2026-official",
        tariff_rule_status="official",
        contractual_status="confirmed",
        confirmed_exceeded=False,
    )
    return replace(base, **changes)


def _local_day_report(
    archive: QuarterArchive, local_date: date, now_local: datetime
) -> dict[str, object]:
    starts = quarter_starts_for_local_day(local_date)
    return history_report(
        archive,
        "meter-a",
        HistoryQuery(starts[0], starts[-1] + timedelta(minutes=15)),
        now_utc=now_local.astimezone(UTC),
    )


def test_current_day_does_not_count_future_quarters_as_missing(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "current-day.db")
    archive.open()
    local_date = date(2026, 4, 10)
    starts = quarter_starts_for_local_day(local_date)
    for index, start in enumerate(starts[:77]):
        archive.upsert_quarter(_record(start, index))

    report = _local_day_report(
        archive,
        local_date,
        datetime(2026, 4, 10, 19, 20, tzinfo=LJUBLJANA),
    )
    summary = report["summary"]
    assert summary["expected_count"] == 96
    assert summary["completed_expected_count"] == 77
    assert summary["completed_archived_count"] == 77
    assert summary["future_or_uncompleted_count"] == 19
    assert summary["missing_count"] == 0


def test_midnight_and_future_day_have_no_missing_completed_intervals(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "midnight-future.db")
    archive.open()
    current_date = date(2026, 1, 2)
    midnight = datetime(2026, 1, 2, 0, 0, tzinfo=LJUBLJANA)

    current = _local_day_report(archive, current_date, midnight)["summary"]
    future = _local_day_report(archive, date(2026, 1, 3), midnight)["summary"]
    for summary in (current, future):
        assert summary["completed_expected_count"] == 0
        assert summary["future_or_uncompleted_count"] == 96
        assert summary["missing_count"] == 0


def test_exact_quarter_transition_promotes_only_completed_slot(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "quarter-transition.db")
    archive.open()
    local_date = date(2026, 1, 2)
    starts = quarter_starts_for_local_day(local_date)
    for index, start in enumerate(starts[:40]):
        archive.upsert_quarter(_record(start, index))

    before = _local_day_report(
        archive,
        local_date,
        datetime(2026, 1, 2, 10, 14, 59, tzinfo=LJUBLJANA),
    )["summary"]
    boundary = _local_day_report(
        archive,
        local_date,
        datetime(2026, 1, 2, 10, 15, tzinfo=LJUBLJANA),
    )["summary"]
    assert before["completed_expected_count"] == 40
    assert before["missing_count"] == 0
    assert boundary["completed_expected_count"] == 41
    assert boundary["missing_count"] == 1


def test_past_day_separates_gaps_incomplete_and_unavailable_rows(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "quality-gaps.db")
    archive.open()
    local_date = date(2026, 1, 2)
    starts = quarter_starts_for_local_day(local_date)
    for index, start in enumerate(starts):
        if index in {5, 6}:
            continue
        changes: dict[str, object] = {}
        if index == 3:
            changes = {"quality": "incomplete", "coverage_seconds": 300, "gap_seconds": 600}
        elif index == 4:
            changes = {"quality": "unavailable", "coverage_seconds": 0, "gap_seconds": 900}
        archive.upsert_quarter(_record(start, index, **changes))

    summary = _local_day_report(
        archive,
        local_date,
        datetime(2026, 1, 3, 0, 0, tzinfo=LJUBLJANA),
    )["summary"]
    assert summary["completed_expected_count"] == 96
    assert summary["completed_archived_count"] == 94
    assert summary["missing_count"] == 2
    assert summary["incomplete_measurement_count"] == 1
    assert summary["unavailable_measurement_count"] == 1
    assert summary["incomplete_count"] == 2


@pytest.mark.parametrize(
    ("local_date", "expected"),
    [(date(2026, 3, 29), 92), (date(2026, 10, 25), 100)],
)
def test_completed_dst_days_use_actual_ljubljana_quarter_count(
    tmp_path, local_date: date, expected: int
) -> None:
    archive = QuarterArchive(tmp_path / f"dst-{local_date}.db")
    archive.open()
    starts = quarter_starts_for_local_day(local_date)
    for index, start in enumerate(starts[:-1]):
        archive.upsert_quarter(_record(start, index))

    summary = _local_day_report(
        archive,
        local_date,
        datetime.combine(local_date + timedelta(days=1), datetime.min.time(), LJUBLJANA),
    )["summary"]
    assert len(starts) == expected
    assert summary["expected_count"] == expected
    assert summary["completed_expected_count"] == expected
    assert summary["future_or_uncompleted_count"] == 0
    assert summary["missing_count"] == 1


def test_history_is_paginated_and_keeps_missing_distinct_from_zero(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "archive.db")
    archive.open()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(12):
        archive.upsert_quarter(_record(start + timedelta(minutes=15 * index), index))
    archive.upsert_quarter(
        _record(
            start + timedelta(hours=4),
            import_kwh=0,
            export_kwh=0,
            import_demand_kw=0,
            signed_average_kw=0,
            utilization_pct=0,
        )
    )
    report = history_report(
        archive,
        "meter-a",
        HistoryQuery(start, start + timedelta(hours=5), page=2, page_size=5),
    )
    assert len(report["items"]) == 5
    assert report["pagination"] == {
        "page": 2,
        "page_size": 5,
        "total": 13,
        "pages": 3,
        "scope": "active_filters",
    }
    assert report["summary"]["scope"] == "selected_range_unfiltered"
    assert report["summary"]["matching_filtered_count"] == 13
    assert report["summary"]["expected_count"] == 20
    assert report["summary"]["missing_count"] == 7
    zero = history_report(
        archive,
        "meter-a",
        HistoryQuery(start + timedelta(hours=4), start + timedelta(hours=4, minutes=15)),
    )["items"][0]
    assert zero["import_kwh"] == 0
    assert zero["measured_valid"] is True


def test_history_filters_do_not_invent_properties_for_missing_rows(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "archive.db")
    archive.open()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    archive.upsert_quarter(_record(start, tariff_block=2))
    archive.upsert_quarter(
        _record(
            start + timedelta(minutes=15),
            quality="incomplete",
            coverage_seconds=300,
            gap_seconds=600,
            contractual_status="incomplete_measurement",
        )
    )
    report = history_report(
        archive,
        "meter-a",
        HistoryQuery(
            start,
            start + timedelta(hours=1),
            qualities=("incomplete",),
            page_size=10,
        ),
    )
    assert report["pagination"]["total"] == 1
    assert report["items"][0]["coverage_pct"] == pytest.approx(100 / 3)
    assert report["summary"]["missing_count"] is None
    assert report["summary"]["filters_active"] is True
    assert report["summary"]["total"] == 2
    assert report["summary"]["matching_filtered_count"] == 1


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("all", {False, True, None}),
        ("confirmed_yes", {True}),
        ("confirmed_no", {False}),
        ("unconfirmed", {None}),
    ],
)
def test_history_exceedance_status_preserves_sql_null_semantics(
    tmp_path, status: str, expected: set[bool | None]
) -> None:
    archive = QuarterArchive(tmp_path / f"{status}.db")
    archive.open()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    archive.upsert_quarter(_record(start, confirmed_exceeded=True, exceeded=True, excess_kw=0.2))
    archive.upsert_quarter(_record(start + timedelta(minutes=15), 1, confirmed_exceeded=False))
    archive.upsert_quarter(
        _record(
            start + timedelta(minutes=30),
            2,
            confirmed_exceeded=None,
            contractual_status="unknown_configuration",
            configuration_status="target_unknown",
            contractual_target_kw=None,
        )
    )
    report = history_report(
        archive,
        "meter-a",
        HistoryQuery(
            start,
            start + timedelta(minutes=45),
            exceedance_status=status,
            direction="asc",
        ),
    )
    assert {item["confirmed_exceeded"] for item in report["items"]} == expected
    assert report["pagination"]["total"] == len(expected)


def test_history_rejects_ambiguous_exceedance_filter() -> None:
    with pytest.raises(ValueError, match="exceedance-status"):
        HistoryQuery(
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 2, tzinfo=UTC),
            exceedance_status="no_or_unconfirmed",
        )


@pytest.mark.parametrize(
    ("requested_sort", "requested_direction"),
    [
        ("import_kwh", "asc"),
        ("import_demand_kw", "asc"),
        ("quality", "asc"),
        ("utilization_pct", "asc"),
    ],
)
def test_block_quarter_report_is_always_newest_first_across_pages(
    tmp_path, requested_sort: str, requested_direction: str
) -> None:
    archive = QuarterArchive(tmp_path / f"{requested_sort}.db")
    archive.open()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(6):
        archive.upsert_quarter(
            _record(
                start + timedelta(minutes=15 * index),
                index,
                tariff_block=2,
                quality="reconstructed" if index % 2 else "measured_aligned",
            )
        )
    first = history_report(
        archive,
        "meter-a",
        HistoryQuery(
            start,
            start + timedelta(hours=2),
            tariff_block=2,
            page=1,
            page_size=2,
            sort_by=requested_sort,
            direction=requested_direction,
        ),
    )
    second = history_report(
        archive,
        "meter-a",
        HistoryQuery(
            start,
            start + timedelta(hours=2),
            tariff_block=2,
            page=2,
            page_size=2,
            sort_by=requested_sort,
            direction=requested_direction,
        ),
    )
    assert first["ordering"] == {
        "sort_by": "start_utc",
        "direction": "desc",
        "locked_for_block_report": True,
    }
    assert [item["start_utc"] for item in first["items"]] == [
        (start + timedelta(minutes=75)).isoformat(),
        (start + timedelta(minutes=60)).isoformat(),
    ]
    assert [item["start_utc"] for item in second["items"]] == [
        (start + timedelta(minutes=45)).isoformat(),
        (start + timedelta(minutes=30)).isoformat(),
    ]


def test_repeated_dst_hour_retains_two_utc_identities(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "archive.db")
    archive.open()
    first = datetime(2026, 10, 25, 0, 0, tzinfo=UTC)
    second = datetime(2026, 10, 25, 1, 0, tzinfo=UTC)
    archive.upsert_quarter(_record(first))
    archive.upsert_quarter(_record(second, 1))
    report = history_report(
        archive, "meter-a", HistoryQuery(first, second + timedelta(minutes=15), direction="asc")
    )
    assert [row["start_utc"] for row in report["items"]] == [
        first.isoformat(),
        second.isoformat(),
    ]
    assert [row["fold"] for row in report["items"]] == [0, 1]


def test_schema_five_upgrade_is_additive_and_backup_is_consistent(tmp_path) -> None:
    path = tmp_path / "archive.db"
    archive = QuarterArchive(path)
    archive.open()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    archive.upsert_quarter(_record(start))
    backup_path = archive.backup(tmp_path / "backups" / "before-repair.db")
    assert backup_path.exists()
    copy = QuarterArchive(backup_path)
    copy.open()
    assert copy.schema_version == 6
    assert copy.list_quarters("meter-a", start, start + timedelta(minutes=15))[0][
        "import_kwh"
    ] == pytest.approx(0.1)


def test_real_schema_five_upgrade_preserves_quarter_and_adds_audit_tables(tmp_path) -> None:
    path = tmp_path / "v5.db"
    start = datetime(2026, 1, 1, tzinfo=UTC)
    created = QuarterArchive(path)
    created.open()
    created.upsert_quarter(_record(start))
    created.close()
    db = sqlite3.connect(path)
    db.executescript(
        """DROP TABLE quarter_revisions;
        DROP TABLE reconstruction_jobs;
        DROP TABLE archive_backups;
        DROP INDEX idx_quarters_namespace_quality_start;
        DROP INDEX idx_quarters_namespace_source_epoch_start;
        PRAGMA user_version=5;"""
    )
    db.close()
    upgraded = QuarterArchive(path)
    upgraded.open()
    assert upgraded.schema_version == 6
    assert upgraded.list_quarters("meter-a", start, start + timedelta(minutes=15))[0][
        "import_kwh"
    ] == pytest.approx(0.1)
    with upgraded._lock:
        names = {
            row[0]
            for row in upgraded._db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {"reconstruction_jobs", "quarter_revisions", "archive_backups"} <= names


@pytest.mark.parametrize(
    "failure_point",
    [
        "before_first_schema_change",
        "after_first_table",
        "after_multiple_tables",
        "during_index_creation",
        "before_version_update",
    ],
)
def test_schema_five_migration_rolls_back_every_failure_and_retries(
    tmp_path, monkeypatch, failure_point: str
) -> None:
    path = tmp_path / f"v5-{failure_point}.db"
    start = datetime(2026, 1, 1, tzinfo=UTC)
    initial = QuarterArchive(path)
    initial.open()
    initial.register_configuration_epoch(
        namespace="meter-a",
        source_id="sensor.grid",
        positive_means_import=True,
        contractual_target_kw=3.5,
        safety_margin_kw=0.1,
        effective_utc=start - timedelta(days=1),
    )
    initial.save_checkpoint("meter-a", {"quarter_start_utc": start.isoformat()})
    initial.upsert_quarter(_record(start))
    initial.close()
    db = sqlite3.connect(path)
    db.executescript(
        """DROP TABLE quarter_revisions;
        DROP TABLE reconstruction_jobs;
        DROP TABLE archive_backups;
        DROP INDEX idx_quarters_namespace_quality_start;
        DROP INDEX idx_quarters_namespace_source_epoch_start;
        PRAGMA user_version=5;"""
    )
    db.close()

    original_checkpoint = QuarterArchive._migration_checkpoint

    def fail_at(self, point: str) -> None:
        if point == failure_point:
            raise sqlite3.OperationalError(f"interrupted at {point}")

    monkeypatch.setattr(QuarterArchive, "_migration_checkpoint", fail_at)
    with pytest.raises(sqlite3.OperationalError):
        QuarterArchive(path).open()

    inspected = sqlite3.connect(path)
    assert inspected.execute("PRAGMA user_version").fetchone()[0] == 5
    assert inspected.execute("SELECT COUNT(*) FROM quarters").fetchone()[0] == 1
    assert inspected.execute("SELECT COUNT(*) FROM source_epochs").fetchone()[0] == 1
    assert inspected.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0] == 1
    auxiliary = {
        row[0]
        for row in inspected.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('reconstruction_jobs','quarter_revisions','archive_backups')"
        )
    }
    assert auxiliary == set()
    inspected.close()

    monkeypatch.setattr(QuarterArchive, "_migration_checkpoint", original_checkpoint)
    retry = QuarterArchive(path)
    retry.open()
    assert retry.schema_version == 6
    assert retry.list_quarters("meter-a", start, start + timedelta(minutes=15))[0][
        "import_kwh"
    ] == pytest.approx(0.1)
    preserved = retry.list_quarters("meter-a", start, start + timedelta(minutes=15))[0]
    assert preserved["tariff_rule_version"] == "si-2026-official"
    assert preserved["contractual_target_kw"] == pytest.approx(3.5)
    assert retry.load_checkpoint("meter-a") == {"quarter_start_utc": start.isoformat()}


def test_schema_five_recovers_expected_partial_auxiliary_objects(tmp_path) -> None:
    path = tmp_path / "partial-v6.db"
    archive = QuarterArchive(path)
    archive.open()
    archive.close()
    db = sqlite3.connect(path)
    db.executescript(
        """DROP TABLE quarter_revisions;
        DROP TABLE archive_backups;
        DROP INDEX idx_quarters_namespace_quality_start;
        DROP INDEX idx_quarters_namespace_source_epoch_start;
        PRAGMA user_version=5;"""
    )
    db.close()
    recovered = QuarterArchive(path)
    recovered.open()
    assert recovered.schema_version == 6


def test_schema_five_rejects_incompatible_partial_objects_without_touching_history(
    tmp_path,
) -> None:
    path = tmp_path / "incompatible-partial-v6.db"
    start = datetime(2026, 1, 1, tzinfo=UTC)
    archive = QuarterArchive(path)
    archive.open()
    archive.upsert_quarter(_record(start))
    archive.close()
    db = sqlite3.connect(path)
    db.executescript(
        """DROP TABLE archive_backups;
        CREATE TABLE archive_backups(backup_id TEXT PRIMARY KEY);
        PRAGMA user_version=5;"""
    )
    db.close()
    with pytest.raises(RuntimeError, match="incompatible partial V6 table archive_backups"):
        QuarterArchive(path).open()
    inspected = sqlite3.connect(path)
    assert inspected.execute("PRAGMA user_version").fetchone()[0] == 5
    assert inspected.execute("SELECT import_kwh FROM quarters").fetchone()[0] == pytest.approx(0.1)
    inspected.close()


def test_dense_ten_year_history_uses_bounded_pages_and_indexed_sql(tmp_path) -> None:
    """Use actual quarter density, not a sparse proxy, without timing assumptions."""

    archive = QuarterArchive(tmp_path / "dense.db")
    archive.open()
    start = datetime(2021, 1, 1, tzinfo=UTC)
    end = datetime(2031, 1, 1, tzinfo=UTC)
    count = int((end - start).total_seconds() // 900)

    def values():
        cursor = start
        while cursor < end:
            following = cursor + timedelta(minutes=15)
            yield (
                "meter-a",
                cursor.isoformat(),
                following.isoformat(),
                cursor.isoformat(),
                0,
                0,
                0.01,
                0.0,
                0.04,
                0.04,
                900.0,
                0.0,
                "reconstructed",
                "dense_fixture",
                "known",
                0,
                "unknown_configuration",
                cursor.isoformat(),
            )
            cursor = following

    with archive._lock, archive._db:
        archive._db.executemany(
            """INSERT INTO quarters(
                 namespace,start_utc,end_utc,start_local,utc_offset_seconds,fold,
                 import_kwh,export_kwh,signed_average_kw,import_demand_kw,
                 coverage_seconds,gap_seconds,quality,provenance,
                 configuration_status,simulation,contractual_status,created_utc)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            values(),
        )
        plan = archive._db.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM quarters WHERE namespace=? "
            "AND start_utc>=? AND start_utc<? ORDER BY start_utc DESC LIMIT 50",
            ("meter-a", start.isoformat(), end.isoformat()),
        ).fetchall()
    report = history_report(
        archive,
        "meter-a",
        HistoryQuery(start, end, page=1, page_size=50),
    )
    assert count > 350_000
    assert report["pagination"]["total"] == count
    assert len(report["items"]) == 50
    assert report["summary"]["total"] == count
    assert any("INDEX" in str(row[3]).upper() for row in plan)
