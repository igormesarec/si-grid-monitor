"""Shared period-analysis regression tests for V0.6."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

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

    first_repeated = resolve_period(PeriodType.HOUR, datetime(2026, 10, 25, 0, 30, tzinfo=UTC))
    second_repeated = resolve_period(PeriodType.HOUR, datetime(2026, 10, 25, 1, 30, tzinfo=UTC))
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
    comparison = report["comparison"]
    assert comparison["available"] is False
    assert comparison["reason"] == "current_period_incomplete"
    assert comparison["current_quality"]["coverage_pct"] == pytest.approx(100 / 48)
    assert comparison["previous_quality"] is None


def _fill_period(
    archive: QuarterArchive,
    bounds: object,
    *,
    quality: str = "reconstructed",
    limit: int | None = None,
) -> None:
    cursor = bounds.start_utc
    count = 0
    while cursor < bounds.end_utc and (limit is None or count < limit):
        archive.upsert_quarter(record(cursor, quality=quality))
        cursor += timedelta(minutes=15)
        count += 1


def test_previous_period_comparison_requires_complete_equal_coverage(
    archive: QuarterArchive,
) -> None:
    current = resolve_period(PeriodType.DAY, date(2026, 1, 6))
    previous = previous_period(current)
    _fill_period(archive, previous)
    _fill_period(archive, current)
    report = period_report(archive, "meter-a", current, now_utc=current.end_utc)
    comparison = report["comparison"]
    assert comparison["available"] is True
    assert comparison["reason"] is None
    assert comparison["current_quality"]["comparable"] is True
    assert comparison["previous_quality"]["comparable"] is True
    assert comparison["changes"]["import_kwh"] == pytest.approx(0)


@pytest.mark.parametrize(
    ("valid", "incomplete", "expected_reason"),
    [
        (1, 0, "previous_period_incomplete"),
        (0, 96, "previous_period_incomplete"),
        (80, 8, "previous_period_incomplete"),
    ],
)
def test_previous_period_limited_incomplete_or_missing_is_not_compared(
    archive: QuarterArchive,
    valid: int,
    incomplete: int,
    expected_reason: str,
) -> None:
    current = resolve_period(PeriodType.DAY, date(2026, 1, 6))
    previous = previous_period(current)
    _fill_period(archive, current)
    _fill_period(archive, previous, limit=valid)
    cursor = previous.start_utc + timedelta(minutes=15 * valid)
    for _index in range(incomplete):
        archive.upsert_quarter(record(cursor, quality="incomplete"))
        cursor += timedelta(minutes=15)
    comparison = period_report(archive, "meter-a", current, now_utc=current.end_utc)["comparison"]
    assert comparison["available"] is False
    assert comparison["reason"] == expected_reason
    assert comparison["previous_quality"]["comparable"] is False
    assert comparison["changes"]["import_kwh"] is None


def test_different_calendar_lengths_and_dst_days_are_not_compared(
    archive: QuarterArchive,
) -> None:
    march = resolve_period(PeriodType.MONTH, date(2026, 3, 10))
    february = previous_period(march)
    _fill_period(archive, february)
    _fill_period(archive, march)
    comparison = period_report(archive, "meter-a", march, now_utc=march.end_utc)["comparison"]
    assert comparison["reason"] == "period_length_mismatch"
    assert (
        comparison["current_quality"]["expected_count"]
        != comparison["previous_quality"]["expected_count"]
    )

    after_fallback = resolve_period(PeriodType.DAY, date(2026, 10, 26))
    fallback = previous_period(after_fallback)
    _fill_period(archive, fallback)
    _fill_period(archive, after_fallback)
    dst_comparison = period_report(
        archive, "meter-a", after_fallback, now_utc=after_fallback.end_utc
    )["comparison"]
    assert dst_comparison["reason"] == "period_length_mismatch"
    assert dst_comparison["previous_quality"]["expected_count"] == 100
    assert dst_comparison["current_quality"]["expected_count"] == 96


def test_missing_repeated_dst_hour_bins_keep_distinct_expected_utc_bounds(
    archive: QuarterArchive,
) -> None:
    week = resolve_period(PeriodType.WEEK, date(2026, 10, 25))
    report = period_report(
        archive,
        "meter-a",
        week,
        now_utc=week.end_utc,
        include_comparison=False,
    )
    repeated = [item for item in report["bins"] if item["bin_key"].startswith("2026-10-25T02|")]
    assert len(repeated) == 2
    assert {item["expected_start_utc"] for item in repeated} == {
        "2026-10-25T00:00:00+00:00",
        "2026-10-25T01:00:00+00:00",
    }
    assert all(item["status"] == "missing" for item in repeated)
    assert all(item["import_kwh"] is None for item in repeated)


def _assert_bins_in_utc_order(report: dict[str, object]) -> None:
    starts = [
        datetime.fromisoformat(str(item["expected_start_utc"] or item["start_utc"])).astimezone(UTC)
        for item in report["bins"]
    ]
    assert starts == sorted(starts)


@pytest.mark.parametrize(
    ("first_measured", "second_measured"), [(False, True), (True, False), (True, True)]
)
def test_hour_bins_remain_chronological_across_repeated_dst_hour(
    archive: QuarterArchive,
    first_measured: bool,
    second_measured: bool,
) -> None:
    week = resolve_period(PeriodType.WEEK, date(2026, 10, 25))
    first = datetime(2026, 10, 25, 0, 0, tzinfo=UTC)
    second = datetime(2026, 10, 25, 1, 0, tzinfo=UTC)
    if first_measured:
        archive.upsert_quarter(record(first))
    if second_measured:
        archive.upsert_quarter(record(second))
    report = period_report(
        archive,
        "meter-a",
        week,
        now_utc=week.end_utc,
        include_comparison=False,
    )
    _assert_bins_in_utc_order(report)
    repeated = [item for item in report["bins"] if item["bin_key"].startswith("2026-10-25T02|")]
    assert [item["expected_start_utc"] for item in repeated] == [
        "2026-10-25T00:00:00+00:00",
        "2026-10-25T01:00:00+00:00",
    ]
    assert [bool(item["archived_count"]) for item in repeated] == [
        first_measured,
        second_measured,
    ]


def test_mixed_bins_sort_across_local_midnight_and_all_resolutions(
    archive: QuarterArchive,
) -> None:
    day = resolve_period(PeriodType.DAY, date(2026, 1, 2))
    assert day.start_utc.date() == date(2026, 1, 1)
    archive.upsert_quarter(record(day.start_utc + timedelta(minutes=15)))
    day_report = period_report(
        archive, "meter-a", day, now_utc=day.end_utc, include_comparison=False
    )
    assert day_report["period"]["resolution"] == "quarter"
    _assert_bins_in_utc_order(day_report)
    assert day_report["bins"][0]["expected_start_utc"] == day.start_utc.isoformat()

    month = resolve_period(PeriodType.MONTH, date(2026, 2, 10))
    archive.upsert_quarter(record(month.start_utc + timedelta(days=12)))
    month_report = period_report(
        archive, "meter-a", month, now_utc=month.end_utc, include_comparison=False
    )
    assert month_report["period"]["resolution"] == "day"
    _assert_bins_in_utc_order(month_report)

    year = resolve_period(PeriodType.YEAR, date(2026, 6, 1))
    year_report = period_report(
        archive, "meter-a", year, now_utc=year.end_utc, include_comparison=False
    )
    assert year_report["period"]["resolution"] == "month"
    _assert_bins_in_utc_order(year_report)


def test_tariff_filtered_mixed_bins_sort_by_expected_utc_start(
    archive: QuarterArchive,
) -> None:
    calendar = SlovenianTariffCalendar()
    day = resolve_period(PeriodType.DAY, date(2026, 1, 5))
    expected_b1: list[datetime] = []
    outside_b1: list[datetime] = []
    cursor = day.start_utc
    while cursor < day.end_utc:
        if calendar.classify(cursor).block == 1:
            expected_b1.append(cursor)
        else:
            outside_b1.append(cursor)
        cursor += timedelta(minutes=15)
    assert len(expected_b1) > 4
    assert outside_b1
    archive.upsert_quarter(record(expected_b1[1], block=1))
    archive.upsert_quarter(record(expected_b1[-2], block=1))
    # An exceptional archived-only row retains its stored historical block and
    # therefore needs the same UTC fallback ordering as expected calendar bins.
    archive.upsert_quarter(record(outside_b1[0], block=1))
    report = period_report(
        archive,
        "meter-a",
        day,
        now_utc=day.end_utc,
        tariff_block=1,
        classifier=calendar.classify,
        include_comparison=False,
    )
    _assert_bins_in_utc_order(report)
    actual_starts = [item["expected_start_utc"] or item["start_utc"] for item in report["bins"]]
    assert actual_starts == [
        instant.isoformat() for instant in sorted([*expected_b1, outside_b1[0]])
    ]
    assert sum(item["expected_start_utc"] is None for item in report["bins"]) == 1


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
    second_page = exceedance_report(
        archive,
        "meter-a",
        bounds,
        now_utc=bounds.end_utc + timedelta(days=1),
        classifier=calendar.classify,
        sort_by="excess_kw",
        direction="desc",
        page=2,
        page_size=2,
    )
    assert len(second_page["items"]) == 1
    assert second_page["items"][0]["import_demand_kw"] == pytest.approx(5.1)


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
    with pytest.raises(ValueError, match="page must be between"):
        exceedance_report(
            archive,
            "meter-a",
            bounds,
            now_utc=bounds.end_utc,
            page=0,
        )


def test_exceedance_unconfirmed_count_uses_distinct_quarters(
    archive: QuarterArchive,
) -> None:
    bounds = resolve_period(PeriodType.DAY, date(2026, 1, 5))
    archive.upsert_quarter(
        record(
            bounds.start_utc,
            quality="incomplete",
            configuration_status="unknown",
            target_kw=None,
        )
    )
    archive.upsert_quarter(
        record(
            bounds.start_utc + timedelta(minutes=15),
            configuration_status="unknown",
            target_kw=None,
        )
    )
    archive.upsert_quarter(
        record(
            bounds.start_utc + timedelta(minutes=30),
            configuration_status="target_unknown",
            target_kw=None,
            contractual_status="target_unknown",
        )
    )
    archive.upsert_quarter(record(bounds.start_utc + timedelta(minutes=45), simulation=True))
    archive.upsert_quarter(record(bounds.start_utc + timedelta(minutes=60)))
    report = exceedance_report(
        archive,
        "meter-a",
        bounds,
        now_utc=bounds.end_utc,
    )
    summary = report["summary"]
    assert summary["expected_completed_count"] == 96
    assert summary["contractual_eligible_count"] == 1
    assert summary["incomplete_or_unconfirmed_count"] == 95
    assert summary["incomplete_or_unconfirmed_count"] <= summary["expected_completed_count"]
    assert (
        summary["incomplete_count"]
        + summary["unknown_configuration_count"]
        + summary["valid_without_confirmed_target_count"]
        + summary["missing_count"]
        > summary["incomplete_or_unconfirmed_count"]
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
    assert all(item["import_kwh"] is None for item in report["bins"])
    assert all(item["export_kwh"] is None for item in report["bins"])


def test_ten_year_populated_report_is_bounded_and_classifies_at_most_hourly(
    archive: QuarterArchive,
) -> None:
    bounds = resolve_period(
        PeriodType.CUSTOM,
        date(2021, 1, 1),
        custom_start=date(2021, 1, 1),
        custom_end=date(2030, 12, 31),
    )
    cursor = bounds.start_utc
    while cursor < bounds.end_utc:
        archive.upsert_quarter(record(cursor))
        cursor += timedelta(days=3)

    classifier_calls = 0

    def counting_classifier(_timestamp: datetime) -> object:
        nonlocal classifier_calls
        classifier_calls += 1
        return SimpleNamespace(block=1)

    started = perf_counter()
    report = period_report(
        archive,
        "meter-a",
        bounds,
        now_utc=bounds.end_utc,
        tariff_block=1,
        classifier=counting_classifier,
        include_comparison=False,
    )
    elapsed = perf_counter() - started
    assert len(report["bins"]) == 120
    assert report["summary"]["archived_count"] > 1_200
    assert classifier_calls <= 24 * 3660
    assert elapsed < 5.0


def test_dense_ten_year_archive_returns_bounded_bins_without_frontend_sized_rows(
    archive: QuarterArchive,
) -> None:
    bounds = resolve_period(
        PeriodType.CUSTOM,
        date(2021, 1, 1),
        custom_start=date(2021, 1, 1),
        custom_end=date(2030, 12, 31),
    )
    cursor = bounds.start_utc
    while cursor < bounds.end_utc:
        archive.upsert_quarter(record(cursor))
        cursor += timedelta(days=1)
    report = period_report(
        archive,
        "meter-a",
        bounds,
        now_utc=bounds.end_utc,
        include_comparison=False,
    )
    assert report["summary"]["archived_count"] > 3_600
    assert len(report["bins"]) == 120
    assert all(item["expected_count"] <= 31 * 96 + 4 for item in report["bins"])
