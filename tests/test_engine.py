"""Rolling and fixed-quarter engine tests."""

from datetime import UTC, date, datetime, timedelta

import pytest

from custom_components.si_grid_monitor.engine import (
    DataQuality,
    FixedQuarterEngine,
    PowerSample,
    TimeWeightedBuffer,
    quarter_bounds,
    quarter_starts_for_local_day,
)


def utc(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 10, 18, hour, minute, second, tzinfo=UTC)


def test_rolling_signed_and_import_only_are_time_weighted() -> None:
    buffer = TimeWeightedBuffer(stale_after_seconds=3600)
    buffer.add(PowerSample(utc(7, 55), 2.0))
    buffer.add(PowerSample(utc(8, 0), -1.0))
    buffer.add(PowerSample(utc(8, 10), 3.0))

    signed, imported = buffer.averages(end=utc(8, 15), window_seconds=900)
    assert signed.complete and imported.complete
    assert signed.value_kw == pytest.approx(1 / 3)
    assert imported.value_kw == pytest.approx(1.0)


@pytest.mark.parametrize("window", [5, 30, 60, 120])
def test_supported_smoothing_window_design(window: int) -> None:
    buffer = TimeWeightedBuffer(stale_after_seconds=300)
    buffer.add(PowerSample(utc(8, 0), 2.0))
    signed, imported = buffer.averages(
        end=utc(8, 0) + timedelta(seconds=window), window_seconds=window
    )
    assert signed.value_kw == pytest.approx(2.0)
    assert imported.value_kw == pytest.approx(2.0)
    assert signed.complete


def test_fixed_quarter_never_nets_export_against_import_demand() -> None:
    engine = FixedQuarterEngine(stale_after_seconds=1000)
    engine.ingest(PowerSample(utc(8, 0), 4.0))
    engine.ingest(PowerSample(utc(8, 5), -2.0))
    completed = engine.ingest(PowerSample(utc(8, 15), 0.0))

    assert len(completed) == 1
    quarter = completed[0]
    assert quarter.import_kwh == pytest.approx(4 * 5 / 60)
    assert quarter.export_kwh == pytest.approx(2 * 10 / 60)
    assert quarter.import_demand_kw == pytest.approx(4 * quarter.import_kwh)
    assert quarter.import_demand_kw == pytest.approx(4 / 3)
    assert quarter.signed_average_kw == pytest.approx(0.0)
    assert quarter.quality == DataQuality.RECONSTRUCTED


def test_boundary_split_and_smoothing_carryover_without_energy_carryover() -> None:
    engine = FixedQuarterEngine(stale_after_seconds=120)
    engine.ingest(PowerSample(utc(8, 14, 40), 4.0))
    engine.ingest(PowerSample(utc(8, 14, 50), 2.0))
    completed = engine.ingest(PowerSample(utc(8, 15, 5), 0.0))
    assert len(completed) == 1

    snapshot = engine.snapshot(
        now=utc(8, 15, 10),
        target_kw=4.8,
        smoothing_seconds=30,
    )
    assert snapshot.quarter_import_kwh == pytest.approx(2 * 5 / 3600)
    assert snapshot.smoothed_signed.value_kw == pytest.approx((4 * 10 + 2 * 15) / 30)
    assert not snapshot.rolling_15m_signed.complete
    assert snapshot.projection.forecast_instant_kw == pytest.approx(
        snapshot.quarter_import_kwh / 0.25
    )


def test_sparse_data_stops_at_stale_limit_and_marks_gap() -> None:
    engine = FixedQuarterEngine(stale_after_seconds=30)
    engine.ingest(PowerSample(utc(8, 0), 3.0))
    snapshot = engine.snapshot(
        now=utc(8, 2), target_kw=4.8, smoothing_seconds=60
    )
    assert snapshot.quarter_import_kwh == pytest.approx(3 * 30 / 3600)
    assert snapshot.coverage_seconds == pytest.approx(30)
    assert snapshot.gap_seconds == pytest.approx(90)
    assert snapshot.quality == DataQuality.INCOMPLETE
    assert snapshot.input_stale
    assert snapshot.current_signed_power_kw is None
    assert snapshot.projection.forecast_instant_kw is None
    assert not snapshot.rolling_15m_signed.complete


def test_crossing_boundary_splits_once() -> None:
    engine = FixedQuarterEngine(stale_after_seconds=60)
    engine.ingest(PowerSample(utc(8, 14, 50), 2.0))
    completed = engine.ingest(PowerSample(utc(8, 15, 10), 2.0))
    assert len(completed) == 1
    assert completed[0].import_kwh == pytest.approx(2 * 10 / 3600)
    snapshot = engine.snapshot(now=utc(8, 15, 10), target_kw=4.8)
    assert snapshot.quarter_import_kwh == pytest.approx(2 * 10 / 3600)


def test_ljubljana_quarter_boundaries_and_dst_day_lengths() -> None:
    bounds = quarter_bounds(datetime(2026, 7, 1, 10, 10, tzinfo=UTC))
    assert bounds.start_local.minute in {0, 15, 30, 45}
    assert bounds.start_local.second == 0

    assert len(quarter_starts_for_local_day(date(2026, 3, 29))) == 92
    autumn = quarter_starts_for_local_day(date(2026, 10, 25))
    assert len(autumn) == 100
    repeated_two_oclock = [
        start.astimezone(bounds.start_local.tzinfo)
        for start in autumn
        if start.astimezone(bounds.start_local.tzinfo).hour == 2
        and start.astimezone(bounds.start_local.tzinfo).minute == 0
    ]
    assert len(repeated_two_oclock) == 2
    assert repeated_two_oclock[0].utcoffset() != repeated_two_oclock[1].utcoffset()
