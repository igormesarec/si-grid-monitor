"""Sustained multi-quarter import-only forecast tests."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.si_grid_monitor.engine import PowerSegment
from custom_components.si_grid_monitor.sustained import (
    ForecastQuality,
    calculate_sustained_forecast,
)


def forecast(
    *,
    now: datetime = datetime(2026, 10, 18, 10, 10, tzinfo=UTC),
    imported: float = 0.0,
    pattern: tuple[PowerSegment, ...] = (PowerSegment(120, -1.5),),
    latest: float = -1.5,
    horizon: int = 60,
    target=lambda _start, _end: 4.8,
    age: float = 0.0,
    unrecoverable: bool = False,
):
    return calculate_sustained_forecast(
        now=now,
        current_import_kwh=imported,
        current_unrecoverable=unrecoverable,
        recent_segments=pattern,
        latest_signed_kw=latest,
        measurement_age_seconds=age,
        smoothing_seconds=120,
        horizon_minutes=horizon,
        target_for_quarter=target,
        stale_after_seconds=60,
    )


def test_export_example_is_limited_by_future_full_quarter() -> None:
    result = forecast()
    assert result.quality == ForecastQuality.AVAILABLE
    assert result.can_add_kw == pytest.approx(6.3, abs=2e-6)
    assert result.must_reduce_kw == 0.0
    assert result.limiting_quarter_start_utc == datetime(2026, 10, 18, 10, 15, tzinfo=UTC)


def test_load_starts_mid_quarter_and_only_applies_for_scheduled_duration() -> None:
    result = forecast(horizon=15)
    # Five minutes current + ten minutes next; the next quarter is evaluated whole.
    assert result.can_add_kw == pytest.approx(8.7, abs=2e-6)


def test_alternating_signed_path_clamps_after_proposed_load() -> None:
    pattern = (PowerSegment(60, 6.0), PowerSegment(60, -8.0))
    result = forecast(
        now=datetime(2026, 10, 18, 10, 15, tzinfo=UTC),
        pattern=pattern,
        latest=-8.0,
    )
    # A 15-minute quarter contains eight +6 minutes and seven -8 minutes.
    # Applying A before clamping therefore limits this phase-aligned path to 3 kW.
    assert result.can_add_kw == pytest.approx(3.0, abs=2e-6)


def test_instant_scenario_catches_sudden_appliance_before_smoothing() -> None:
    pattern = (PowerSegment(120, 0.0),)
    result = forecast(pattern=pattern, latest=3.0)
    assert result.can_add_kw == pytest.approx(1.8, abs=2e-6)


def test_future_lower_target_is_supported_without_tariff_engine() -> None:
    def target(start: datetime, _end: datetime) -> float:
        return 3.0 if start >= datetime(2026, 10, 18, 10, 30, tzinfo=UTC) else 4.8

    result = forecast(pattern=(PowerSegment(120, 1.0),), latest=1.0, target=target)
    assert result.can_add_kw == pytest.approx(2.0, abs=2e-6)
    assert result.limiting_target_kw == 3.0


def test_abundant_current_budget_does_not_hide_stricter_next_quarter() -> None:
    boundary = datetime(2026, 10, 18, 10, 15, tzinfo=UTC)

    def target(start: datetime, _end: datetime) -> float:
        return 20.0 if start < boundary else 4.0

    result = forecast(
        now=datetime(2026, 10, 18, 10, 10, tzinfo=UTC),
        pattern=(PowerSegment(120, 0.0),),
        latest=0.0,
        target=target,
    )
    assert result.can_add_kw == pytest.approx(4.0, abs=2e-6)
    assert result.limiting_quarter_start_utc == boundary


def test_sustained_reduction_import_and_export() -> None:
    importing = forecast(
        now=datetime(2026, 10, 18, 10, 15, tzinfo=UTC),
        pattern=(PowerSegment(120, 6.0),),
        latest=6.0,
    )
    assert importing.can_add_kw == 0.0
    assert importing.must_reduce_kw == pytest.approx(1.2, abs=2e-6)

    exporting = forecast(
        now=datetime(2026, 10, 18, 10, 15, tzinfo=UTC),
        pattern=(PowerSegment(120, -2.0),),
        latest=-2.0,
    )
    assert exporting.must_reduce_kw == 0.0


def test_unrecoverable_quarter_does_not_claim_recovery() -> None:
    result = forecast(
        imported=1.3,
        pattern=(PowerSegment(120, 3.0),),
        latest=3.0,
        unrecoverable=True,
    )
    assert result.current_quarter_unrecoverable
    assert result.can_add_kw == 0.0
    assert result.must_reduce_kw == pytest.approx(3.0, abs=2e-6)
    assert result.reason == "current_quarter_already_unrecoverable"


@pytest.mark.parametrize("horizon", [15, 30, 60, 120])
def test_all_supported_horizons(horizon: int) -> None:
    result = forecast(horizon=horizon)
    assert result.horizon_minutes == horizon
    assert result.can_add_kw is not None


def test_stale_and_insufficient_measurements_are_not_safe_values() -> None:
    stale = forecast(age=61)
    assert stale.quality == ForecastQuality.STALE
    assert stale.can_add_kw is None

    incomplete = forecast(pattern=(PowerSegment(30, 0.0),))
    assert incomplete.quality == ForecastQuality.INSUFFICIENT_COVERAGE
    assert incomplete.can_add_kw is None

    missing_quarter_energy = calculate_sustained_forecast(
        now=datetime(2026, 10, 18, 10, 10, tzinfo=UTC),
        current_import_kwh=0.0,
        current_unrecoverable=False,
        recent_segments=(PowerSegment(120, 0.0),),
        latest_signed_kw=0.0,
        measurement_age_seconds=0.0,
        smoothing_seconds=120,
        horizon_minutes=60,
        target_for_quarter=lambda _start, _end: 4.8,
        stale_after_seconds=60,
        current_quarter_complete=False,
    )
    assert missing_quarter_energy.quality == ForecastQuality.INSUFFICIENT_COVERAGE
    assert missing_quarter_energy.reason == "current_quarter_energy_incomplete"


def test_partial_final_quarter_that_cannot_be_recovered_is_unavailable() -> None:
    result = forecast(pattern=(PowerSegment(120, 20.0),), latest=20.0)
    assert result.quality == ForecastQuality.UNAVAILABLE
    assert result.must_reduce_kw is None
    assert result.reason == "scheduled_reduction_cannot_recover_limiting_quarter"


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 10, 18, 23, 59, 45, tzinfo=UTC),
        datetime(2026, 3, 29, 0, 59, 45, tzinfo=UTC),
        datetime(2026, 10, 25, 0, 59, 45, tzinfo=UTC),
        datetime(2026, 10, 18, 10, 15, tzinfo=UTC),
    ],
)
def test_midnight_dst_and_exact_quarter_crossings(now: datetime) -> None:
    starts: list[datetime] = []

    def target(start: datetime, _end: datetime) -> float:
        starts.append(start)
        return 4.8

    result = forecast(now=now, target=target)
    assert result.quality == ForecastQuality.AVAILABLE
    assert all(start.second == 0 and start.minute in {0, 15, 30, 45} for start in starts)
    assert sorted(set(starts)) == sorted(starts[: len(set(starts))])


def test_pure_forecast_has_no_archive_side_effects(tmp_path) -> None:
    before = tuple(tmp_path.iterdir())
    forecast(now=datetime.now(UTC) - timedelta(seconds=1))
    assert tuple(tmp_path.iterdir()) == before
