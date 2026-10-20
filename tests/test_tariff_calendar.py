"""Independent fixtures for the official Slovenian tariff tables."""

from datetime import UTC, date, datetime, timedelta

import pytest

from custom_components.si_grid_monitor.engine import PowerSegment
from custom_components.si_grid_monitor.sustained import calculate_sustained_forecast
from custom_components.si_grid_monitor.tariffs import (
    DayType,
    RuleStatus,
    Season,
    SlovenianTariffCalendar,
)
from custom_components.si_grid_monitor.tariffs.calendar import LJUBLJANA

OFFICIAL_2026 = {
    (Season.HIGHER, DayType.WORKING): (
        3,
        3,
        3,
        3,
        3,
        3,
        2,
        1,
        1,
        1,
        1,
        1,
        1,
        1,
        2,
        2,
        1,
        1,
        1,
        1,
        2,
        2,
        3,
        3,
    ),
    (Season.HIGHER, DayType.NONWORKING): (
        4,
        4,
        4,
        4,
        4,
        4,
        3,
        2,
        2,
        2,
        2,
        2,
        2,
        2,
        3,
        3,
        2,
        2,
        2,
        2,
        3,
        3,
        4,
        4,
    ),
    (Season.LOWER, DayType.WORKING): (
        4,
        4,
        4,
        4,
        4,
        4,
        3,
        2,
        2,
        2,
        2,
        2,
        2,
        2,
        3,
        3,
        2,
        2,
        2,
        2,
        3,
        3,
        4,
        4,
    ),
    (Season.LOWER, DayType.NONWORKING): (
        5,
        5,
        5,
        5,
        5,
        5,
        4,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        4,
        4,
        3,
        3,
        3,
        3,
        4,
        4,
        5,
        5,
    ),
}

OFFICIAL_2027 = {
    (Season.HIGHER, DayType.WORKING): (
        3,
        3,
        3,
        3,
        3,
        3,
        1,
        1,
        1,
        1,
        1,
        1,
        2,
        2,
        2,
        2,
        2,
        1,
        1,
        1,
        2,
        2,
        3,
        3,
    ),
    (Season.HIGHER, DayType.NONWORKING): (
        4,
        4,
        4,
        4,
        4,
        4,
        3,
        3,
        3,
        3,
        3,
        3,
        4,
        4,
        4,
        4,
        4,
        3,
        3,
        3,
        3,
        3,
        4,
        4,
    ),
    (Season.LOWER, DayType.WORKING): (
        5,
        5,
        5,
        5,
        5,
        5,
        3,
        3,
        3,
        3,
        3,
        3,
        4,
        4,
        4,
        4,
        4,
        3,
        3,
        3,
        3,
        3,
        5,
        5,
    ),
    (Season.LOWER, DayType.NONWORKING): (
        5,
        5,
        5,
        5,
        5,
        5,
        4,
        4,
        4,
        4,
        4,
        4,
        5,
        5,
        5,
        5,
        5,
        4,
        4,
        4,
        4,
        4,
        5,
        5,
    ),
}


def local_utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=LJUBLJANA).astimezone(UTC)


@pytest.mark.parametrize(
    ("year", "month", "day", "expected"),
    [
        (2026, 1, 5, OFFICIAL_2026[(Season.HIGHER, DayType.WORKING)]),
        (2026, 1, 4, OFFICIAL_2026[(Season.HIGHER, DayType.NONWORKING)]),
        (2026, 7, 6, OFFICIAL_2026[(Season.LOWER, DayType.WORKING)]),
        (2026, 7, 5, OFFICIAL_2026[(Season.LOWER, DayType.NONWORKING)]),
        (2027, 1, 4, OFFICIAL_2027[(Season.HIGHER, DayType.WORKING)]),
        (2027, 1, 3, OFFICIAL_2027[(Season.HIGHER, DayType.NONWORKING)]),
        (2027, 7, 5, OFFICIAL_2027[(Season.LOWER, DayType.WORKING)]),
        (2027, 7, 4, OFFICIAL_2027[(Season.LOWER, DayType.NONWORKING)]),
    ],
)
def test_all_24_official_hourly_values(
    year: int, month: int, day: int, expected: tuple[int, ...]
) -> None:
    calendar = SlovenianTariffCalendar()
    actual = tuple(calendar.classify(local_utc(year, month, day, hour)).block for hour in range(24))
    assert actual == expected


@pytest.mark.parametrize("month", range(1, 13))
@pytest.mark.parametrize("nonworking", [False, True])
def test_every_month_and_day_type_uses_official_2027_fixture(month: int, nonworking: bool) -> None:
    candidate = date(2027, month, 1)
    desired_weekday = 6 if nonworking else 2
    while candidate.weekday() != desired_weekday:
        candidate += timedelta(days=1)
    season = Season.HIGHER if month in {11, 12, 1, 2} else Season.LOWER
    day_type = DayType.NONWORKING if nonworking else DayType.WORKING
    expected = OFFICIAL_2027[(season, day_type)]
    actual = tuple(
        SlovenianTariffCalendar().classify(local_utc(2027, month, candidate.day, hour)).block
        for hour in range(24)
    )
    assert actual == expected


@pytest.mark.parametrize("minute", [0, 15, 30, 45])
def test_every_quarter_in_hour_has_same_official_block(minute: int) -> None:
    value = SlovenianTariffCalendar().classify(local_utc(2027, 1, 4, 12, minute))
    assert value.block == 2


def test_holiday_on_weekday_and_weekend_is_named_and_nonworking() -> None:
    calendar = SlovenianTariffCalendar()
    monday = calendar.classify(local_utc(2027, 2, 8, 9))
    weekend = calendar.classify(local_utc(2026, 8, 15, 9))
    assert monday.day_type == DayType.NONWORKING
    assert monday.holiday_name == "Prešeren Day"
    assert weekend.day_type == DayType.NONWORKING
    assert weekend.holiday_name == "Assumption Day"


@pytest.mark.parametrize(
    ("year", "movable"),
    [
        (2026, {(4, 5), (4, 6), (5, 24)}),
        (2027, {(3, 28), (3, 29), (5, 16)}),
        (2028, {(4, 16), (4, 17), (6, 4)}),
        (2029, {(4, 1), (4, 2), (5, 20)}),
        (2030, {(4, 21), (4, 22), (6, 9)}),
    ],
)
def test_complete_official_work_free_holiday_fixture(
    year: int, movable: set[tuple[int, int]]
) -> None:
    fixed = {
        (1, 1),
        (1, 2),
        (2, 8),
        (4, 27),
        (5, 1),
        (5, 2),
        (6, 25),
        (8, 15),
        (10, 31),
        (11, 1),
        (12, 25),
        (12, 26),
    }
    calendar = SlovenianTariffCalendar(allow_provisional=True)
    for month, day in fixed | movable:
        value = calendar.classify(local_utc(year, month, day, 12))
        assert value.holiday_name is not None
        assert value.day_type == DayType.NONWORKING


def test_season_and_official_rule_transition_at_year_boundary() -> None:
    calendar = SlovenianTariffCalendar()
    old = calendar.classify(local_utc(2026, 12, 31, 6))
    new = calendar.classify(local_utc(2027, 1, 1, 6))
    assert old.rule_version == "SI-URO-2026"
    assert new.rule_version == "SI-URO-2027"
    assert old.rule_status == new.rule_status == RuleStatus.OFFICIAL


@pytest.mark.parametrize("year", [2028, 2029, 2030])
def test_future_rules_are_unverified_unless_explicitly_enabled(year: int) -> None:
    timestamp = local_utc(year, 7, 1, 12)
    unavailable = SlovenianTariffCalendar().classify(timestamp)
    intrinsic = SlovenianTariffCalendar().classify_rule(timestamp)
    provisional = SlovenianTariffCalendar(allow_provisional=True).classify(timestamp)
    assert unavailable.block is None
    assert unavailable.rule_status == RuleStatus.UNVERIFIED
    assert provisional.block is not None
    assert provisional.rule_status == RuleStatus.PROVISIONAL
    assert intrinsic.block == provisional.block
    assert intrinsic.rule_status == RuleStatus.PROVISIONAL
    assert "PROVISIONAL" in (provisional.rule_version or "")


def test_leap_day_2028_is_supported_but_not_claimed_official() -> None:
    value = SlovenianTariffCalendar(allow_provisional=True).classify(local_utc(2028, 2, 29, 8))
    assert value.calendar_year == 2028
    assert value.local_datetime.date() == date(2028, 2, 29)
    assert value.rule_status == RuleStatus.PROVISIONAL


def test_dst_days_have_23_and_25_real_hours_with_fold_preserved() -> None:
    calendar = SlovenianTariffCalendar()
    spring = calendar.daily_view(date(2027, 3, 28))
    autumn = calendar.daily_view(date(2027, 10, 31))
    assert len(spring) == 23
    assert len(autumn) == 25
    repeated = [row for row in autumn if row["local_datetime"].hour == 2]
    assert len(repeated) == 2
    assert {row["fold"] for row in repeated} == {0, 1}
    assert {row["utc_offset_seconds"] for row in repeated} == {3600, 7200}


def test_next_transition_and_calendar_query_shapes() -> None:
    calendar = SlovenianTariffCalendar()
    now = local_utc(2027, 1, 4, 11, 45)
    transition = calendar.next_transition(now)
    assert transition is not None
    assert transition.local_datetime.hour == 12
    assert transition.block == 2
    assert len(calendar.upcoming_quarters(now, count=5)) == 5
    assert len(calendar.weekly_view(date(2027, 1, 4))) == 7
    assert len(calendar.monthly_view(2027, 2)) == 28
    assert len(calendar.yearly_view(2028)) == 12


def test_out_of_supported_range_is_explicit() -> None:
    value = SlovenianTariffCalendar().classify(datetime(2031, 1, 1, tzinfo=UTC))
    assert value.block is None
    assert value.rule_status == RuleStatus.OUT_OF_RANGE


def test_quarter_identity_comes_from_utc_across_fall_back() -> None:
    first = datetime(2027, 10, 31, 0, 15, tzinfo=UTC)
    second = first + timedelta(hours=1)
    calendar = SlovenianTariffCalendar()
    one = calendar.classify(first)
    two = calendar.classify(second)
    assert one.local_datetime.hour == two.local_datetime.hour == 2
    assert one.fold == 0 and two.fold == 1
    assert one.timestamp_utc != two.timestamp_utc


def test_sustained_forecast_selects_each_future_quarters_block_target() -> None:
    calendar = SlovenianTariffCalendar()
    now = local_utc(2027, 1, 4, 11, 45)
    targets = (9.0, 2.0, 8.0, 7.0, 6.0)

    def target(start: datetime, _end: datetime) -> float:
        tariff = calendar.classify(start)
        assert tariff.block is not None
        return targets[tariff.block - 1]

    result = calculate_sustained_forecast(
        now=now,
        current_import_kwh=0.0,
        current_unrecoverable=False,
        current_quarter_complete=True,
        recent_segments=(PowerSegment(120, 0.0),),
        latest_signed_kw=0.0,
        measurement_age_seconds=0.0,
        smoothing_seconds=120,
        horizon_minutes=120,
        target_for_quarter=target,
        stale_after_seconds=60,
    )
    assert calendar.classify(now).block == 1
    assert calendar.classify(local_utc(2027, 1, 4, 12)).block == 2
    assert result.can_add_kw == pytest.approx(2.0, abs=2e-6)
    assert result.limiting_target_kw == 2.0


def test_rule_status_report_never_promotes_provisional_years() -> None:
    disabled = SlovenianTariffCalendar(allow_provisional=False).rule_status_report(
        date(2028, 1, 1)
    )
    enabled = SlovenianTariffCalendar(allow_provisional=True).rule_status_report(
        date(2028, 1, 1)
    )
    assert disabled["official_coverage_end"] == date(2027, 12, 31)
    assert disabled["current_status"] == "unverified"
    assert enabled["current_status"] == "provisional"
    assert disabled["remote_rules_activated"] is False
    years = {item["year"]: item for item in disabled["years"]}
    assert years[2026]["status"] == "official"
    assert years[2027]["status"] == "official"
    assert all(years[year]["status"] == "provisional" for year in (2028, 2029, 2030))
