"""Shared period-analysis regression tests for V0.6."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from custom_components.si_grid_monitor.analysis import (
    PeriodType,
    block_report,
    exceedance_report,
    next_period,
    period_report,
    previous_period,
    resolve_period,
)
from custom_components.si_grid_monitor.archive import (
    ArchiveRecord,
    QuarterArchive,
    summarize_archive_rows,
)
from custom_components.si_grid_monitor.tariffs import SlovenianTariffCalendar


def record(
    start: datetime,
    *,
    namespace: str = "meter-a",
    import_kwh: float = 0.25,
    export_kwh: float = 0.0,
    target_kw: float | None = 3.5,
    block: int = 1,
    quality: str = "reconstructed",
    configuration_status: str = "known",
    contractual_status: str = "confirmed",
    simulation: bool = False,
) -> ArchiveRecord:
    demand = import_kwh * 4
    eligible = (
        quality == "reconstructed"
        and configuration_status == "known"
        and contractual_status == "confirmed"
        and target_kw is not None
        and not simulation
    )
    exceeded = None if target_kw is None else demand > target_kw + 1e-9
    return ArchiveRecord(
        namespace=namespace,
        start_utc=start,
        end_utc=start + timedelta(minutes=15),
        import_kwh=import_kwh,
        export_kwh=export_kwh,
        signed_average_kw=(import_kwh - export_kwh) * 4,
        import_demand_kw=demand,
        coverage_seconds=900 if quality == "reconstructed" else 300,
        gap_seconds=0 if quality == "reconstructed" else 600,
        quality=quality,
        provenance="live_reconstructed",
        source_id="sensor.grid",
        source_epoch=1,
        configuration_status=configuration_status,
        contractual_target_kw=target_kw,
        safety_margin_kw=0.0,
        operational_target_kw=target_kw,
        utilization_pct=(100 * demand / target_kw if target_kw else None),
        exceeded=exceeded,
        excess_kw=(max(0.0, demand - target_kw) if target_kw is not None else None),
        simulation=simulation,
        tariff_block=block,
        tariff_rule_version="si-2026-verified",
        tariff_calendar_year=2026,
        tariff_season="higher",
        tariff_day_type="working_day",
        tariff_rule_status=("official" if contractual_status == "confirmed" else "provisional"),
        tariff_source_url="https://www.uro.si/",
        tariff_policy="official_only",
        contractual_status=contractual_status,
        confirmed_exceeded=(exceeded if eligible else None),
    )


@pytest.fixture
def archive(tmp_path: Path) -> QuarterArchive:
    result = QuarterArchive(tmp_path / "analysis.db")
    result.open()
    return result


def test_period_boundaries_use_local_calendar_and_half_open_utc() -> None:
    spring = resolve_period(PeriodType.DAY, date(2026, 3, 29))
    normal = resolve_period(PeriodType.DAY, date(2026, 4, 2))
    autumn = resolve_period(PeriodType.DAY, date(2026, 10, 25))
    assert (spring.end_utc - spring.start_utc) / timedelta(minutes=15) == 92
    assert (normal.end_utc - normal.start_utc) / timedelta(minutes=15) == 96
    assert (autumn.end_utc - autumn.start_utc) / timedelta(minutes=15) == 100

    week = resolve_period(PeriodType.WEEK, date(2027, 1, 1))
    assert week.start_local.date() == date(2026, 12, 28)
    assert week.end_local.date() == date(2027, 1, 4)
    assert next_period(previous_period(week)).start_utc == week.start_utc

    first_repeated = resolve_period(
        PeriodType.HOUR, datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    )
    second_repeated = resolve_period(
        PeriodType.HOUR, datetime(2026, 10, 25, 1, 30, tzinfo=UTC)
    )
    assert first_repeated.start_local.hour == second_repeated.start_local.hour == 2
    assert first_repeated.start_utc != second_repeated.start_utc
    assert "CEST" in first_repeated.label
    assert "CET" in second_repeated.label


def test_custom_range_validation_and_leap_day() -> None:
    leap = resolve_period(
        PeriodType.CUSTOM,
        date(2028, 2, 29),
        custom_start=date(2028, 2, 28),
        custom_end=date(2028, 3, 1),
    )
    assert leap.start_local.date() == date(2028, 2, 28)
    assert leap.end_local.date() == date(2028, 3, 2)
    with pytest.raises(ValueError, match="must not precede"):
        resolve_period(
            PeriodType.CUSTOM,
            date(2026, 1, 1),
            custom_start=date(2026, 1, 2),
            custom_end=date(2026, 1, 1),
        )


def test_period_summary_separates_valid_partial_unknown_simulation_and_missing(
    archive: QuarterArchive,
) -> None:
    bounds = resolve_period(PeriodType.HOUR, datetime(2026, 1, 5, 10, tzinfo=UTC))
    starts = [bounds.start_utc + timedelta(minutes=15 * index) for index in range(4)]
    archive.upsert_quarter(record(starts[0], import_kwh=0.5, export_kwh=0.2))
    archive.upsert_quarter(record(starts[1], import_kwh=0.1, quality="incomplete"))
    archive.upsert_quarter(
        record(starts[2], import_kwh=0.25, target_kw=None, contractual_status="target_unknown")
    )
    archive.upsert_quarter(record(starts[3], import_kwh=2.0, simulation=True))

    report = period_report(
        archive,
        "meter-a",
        bounds,
        now_utc=bounds.end_utc + timedelta(hours=1),
    )
    summary = report["summary"]
    assert summary["valid_count"] == 2
    assert summary["contractual_eligible_count"] == 1
    assert summary["incomplete_count"] == 1
    assert summary["simulation_count"] == 1
    assert summary["import_kwh"] == pytest.approx(0.75)
    assert summary["export_kwh"] == pytest.approx(0.2)
    assert summary["partial_observed_import_kwh"] == pytest.approx(0.1)
    assert summary["missing_count"] == 1
    assert summary["coverage_pct"] == pytest.approx(50.0)


def test_import_and_export_are_never_netted_for_demand(archive: QuarterArchive) -> None:
    bounds = resolve_period(PeriodType.HOUR, datetime(2026, 1, 5, 10, tzinfo=UTC))
    archive.upsert_quarter(record(bounds.start_utc, import_kwh=1.0, export_kwh=2 / 3))
    report = period_report(
        archive, "meter-a", bounds, now_utc=bounds.end_utc + timedelta(minutes=1)
    )
    summary = report["summary"]
    assert summary["import_kwh"] == pytest.approx(1.0)
    assert summary["export_kwh"] == pytest.approx(2 / 3)
    assert summary["signed_net_kwh"] == pytest.approx(1 / 3)
    assert summary["maximum_import_demand_kw"] == pytest.approx(4.0)


def test_monthly_bin_preserves_individual_quarter_peak_and_historical_targets(
    archive: QuarterArchive,
) -> None:
    bounds = resolve_period(PeriodType.MONTH, date(2026, 1, 15))
    archive.upsert_quarter(record(bounds.start_utc, import_kwh=1.3, target_kw=3.5))
    archive.upsert_quarter(
        record(bounds.start_utc + timedelta(minutes=15), import_kwh=0.1, target_kw=4.2)
    )
    report = period_report(archive, "meter-a", bounds, now_utc=bounds.end_utc + timedelta(days=1))
    assert report["period"]["resolution"] == "day"
    measured = next(item for item in report["bins"] if item["archived_count"])
    assert measured["maximum_import_demand_kw"] == pytest.approx(5.2)
    assert measured["average_import_demand_kw"] == pytest.approx(2.8)
    assert measured["targets_kw"] == [3.5, 4.2]


def test_three_consecutive_exceedances_are_three_quarters(archive: QuarterArchive) -> None:
    bounds = resolve_period(PeriodType.HOUR, datetime(2026, 1, 5, 10, tzinfo=UTC))
    for index, demand in enumerate((5.2, 5.4, 5.1)):
        archive.upsert_quarter(
            record(bounds.start_utc + timedelta(minutes=15 * index), import_kwh=demand / 4)
        )
    report = period_report(
        archive, "meter-a", bounds, now_utc=bounds.end_utc + timedelta(minutes=1)
    )
    assert report["summary"]["exceeded_count"] == 3
    assert report["summary"]["exceeded_duration_minutes"] == 45


def test_partial_current_period_does_not_claim_a_comparable_previous_period(
    archive: QuarterArchive,
) -> None:
    bounds = resolve_period(PeriodType.DAY, date(2026, 1, 5))
    now = bounds.start_utc + timedelta(hours=12, minutes=7)
    archive.upsert_quarter(record(bounds.start_utc))
    report = period_report(archive, "meter-a", bounds, now_utc=now)
    assert report["period"]["partial"]
    assert report["comparison"] == {
        "available": False,
        "reason": "current_period_incomplete",
        "period": report["comparison"]["period"],
    }


def test_block_filter_and_namespace_isolation(archive: QuarterArchive) -> None:
    calendar = SlovenianTariffCalendar()
    bounds = resolve_period(PeriodType.DAY, date(2026, 1, 5))
    start = bounds.start_utc
    archive.upsert_quarter(record(start, namespace="meter-a", block=2))
    archive.upsert_quarter(record(start + timedelta(minutes=15), namespace="meter-a", block=1))
    archive.upsert_quarter(record(start, namespace="meter-b", block=2, import_kwh=2.0))
    report = period_report(
        archive,
        "meter-a",
        bounds,
        now_utc=bounds.end_utc + timedelta(days=1),
        tariff_block=2,
        classifier=calendar.classify,
    )
    assert report["summary"]["archived_count"] == 1
    assert report["summary"]["import_kwh"] == pytest.approx(0.25)


def test_five_block_totals_reconcile_and_preserve_historical_targets(
    archive: QuarterArchive,
) -> None:
    calendar = SlovenianTariffCalendar()
    bounds = resolve_period(PeriodType.DAY, date(2026, 1, 5))
    archive.upsert_quarter(record(bounds.start_utc, block=1, target_kw=3.5, import_kwh=1.0))
    archive.upsert_quarter(record(bounds.start_utc + timedelta(minutes=15), block=1, target_kw=3.9))
    archive.upsert_quarter(record(bounds.start_utc + timedelta(minutes=30), block=2, target_kw=4.1))
    archive.upsert_quarter(
        record(bounds.start_utc + timedelta(minutes=45), block=2, quality="incomplete")
    )
    blocks = block_report(
        archive,
        "meter-a",
        bounds,
        now_utc=bounds.end_utc + timedelta(days=1),
        classifier=calendar.classify,
    )
    period = period_report(
        archive,
        "meter-a",
        bounds,
        now_utc=bounds.end_utc + timedelta(days=1),
        classifier=calendar.classify,
    )
    assert [item["block"] for item in blocks["blocks"]] == [1, 2, 3, 4, 5]
    assert sum(item["valid_count"] for item in blocks["blocks"]) == period["summary"]["valid_count"]
    assert sum(item["import_kwh"] for item in blocks["blocks"]) == pytest.approx(
        period["summary"]["import_kwh"]
    )
    assert blocks["totals"]["import_kwh"] == pytest.approx(period["summary"]["import_kwh"])
    assert blocks["totals"]["valid_count"] == period["summary"]["valid_count"]
    assert blocks["blocks"][0]["targets_kw"] == [3.5, 3.9]
    assert blocks["blocks"][0]["maximum_import_demand_kw"] == pytest.approx(4.0)
    assert blocks["blocks"][3]["active"] is False


def test_exceedance_report_keeps_each_quarter_and_excludes_unconfirmed(
    archive: QuarterArchive,
) -> None:
    calendar = SlovenianTariffCalendar()
    bounds = resolve_period(PeriodType.DAY, date(2026, 1, 5))
    for index, demand in enumerate((5.2, 5.4, 5.1)):
        archive.upsert_quarter(
            record(
                bounds.start_utc + timedelta(minutes=15 * index),
                import_kwh=demand / 4,
                target_kw=4.8,
                block=2,
            )
        )
    archive.upsert_quarter(
        record(
            bounds.start_utc + timedelta(minutes=45),
            import_kwh=4.8 / 4,
            target_kw=4.8,
            block=2,
        )
    )
    archive.upsert_quarter(
        record(
            bounds.start_utc + timedelta(minutes=60),
            import_kwh=6 / 4,
            target_kw=4.8,
            block=2,
            contractual_status="provisional_estimate",
        )
    )
    archive.upsert_quarter(
        record(
            bounds.start_utc + timedelta(minutes=75),
            import_kwh=6 / 4,
            target_kw=4.8,
            block=2,
            simulation=True,
        )
    )
    report = exceedance_report(
        archive,
        "meter-a",
        bounds,
        now_utc=bounds.end_utc + timedelta(days=1),
        classifier=calendar.classify,
        sort_by="excess_kw",
        direction="desc",
        page_size=2,
    )
    assert report["summary"]["exceedance_count"] == 3
    assert report["summary"]["exceeded_duration_minutes"] == 45
    assert report["pagination"] == {"page": 1, "page_size": 2, "total": 3, "pages": 2}
    assert [item["import_demand_kw"] for item in report["items"]] == [5.4, 5.2]
    assert report["items"][0]["excess_kw"] == pytest.approx(0.6)
    assert report["items"][0]["excess_percentage"] == pytest.approx(12.5)
    assert report["items"][0]["excess_energy_kwh"] == pytest.approx(0.15)
    assert report["summary"]["most_affected_block"] == 2


def test_exceedance_tolerance_and_page_validation(archive: QuarterArchive) -> None:
    bounds = resolve_period(PeriodType.HOUR, datetime(2026, 1, 5, 10, tzinfo=UTC))
    archive.upsert_quarter(record(bounds.start_utc, import_kwh=3.5 / 4, target_kw=3.5))
    archive.upsert_quarter(
        record(
            bounds.start_utc + timedelta(minutes=15),
            import_kwh=(3.5 + 2e-9) / 4,
            target_kw=3.5,
        )
    )
    report = exceedance_report(
        archive,
        "meter-a",
        bounds,
        now_utc=bounds.end_utc + timedelta(minutes=1),
    )
    assert report["summary"]["exceedance_count"] == 1
    with pytest.raises(ValueError, match="page must be positive"):
        exceedance_report(
            archive,
            "meter-a",
            bounds,
            now_utc=bounds.end_utc,
            page=0,
        )


def test_period_reconciles_with_existing_archive_summary(archive: QuarterArchive) -> None:
    bounds = resolve_period(PeriodType.DAY, date(2026, 1, 5))
    archive.upsert_quarter(record(bounds.start_utc, import_kwh=0.4, export_kwh=0.2))
    archive.upsert_quarter(
        record(bounds.start_utc + timedelta(minutes=15), import_kwh=0.1, quality="incomplete")
    )
    rows = archive.list_quarters("meter-a", bounds.start_utc, bounds.end_utc)
    existing = summarize_archive_rows(rows)
    report = period_report(
        archive,
        "meter-a",
        bounds,
        now_utc=bounds.end_utc + timedelta(days=1),
    )["summary"]
    for field in (
        "valid_count",
        "incomplete_count",
        "exceeded_count",
        "import_kwh",
        "export_kwh",
        "partial_observed_import_kwh",
        "maximum_import_demand_kw",
        "average_import_demand_kw",
    ):
        assert report[field] == pytest.approx(getattr(existing, field))


def test_ten_year_empty_archive_stays_month_bounded(archive: QuarterArchive) -> None:
    bounds = resolve_period(
        PeriodType.CUSTOM,
        date(2021, 1, 1),
        custom_start=date(2021, 1, 1),
        custom_end=date(2030, 12, 31),
    )
    report = period_report(
        archive,
        "meter-a",
        bounds,
        now_utc=bounds.end_utc + timedelta(days=1),
    )
    assert report["period"]["resolution"] == "month"
    assert len(report["bins"]) == 120
    assert report["summary"]["archived_count"] == 0
    assert all(item["status"] == "missing" for item in report["bins"])
