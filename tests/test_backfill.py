"""Detailed-recorder reconstruction tests."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.si_grid_monitor.backfill import (
    HistoricalPowerReading,
    normalize_historical_readings,
    reconstruct_quarters,
)
from custom_components.si_grid_monitor.engine import DataQuality, PowerSample


def test_backfill_uses_same_import_only_rules_as_live_engine() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    quarters = reconstruct_quarters(
        [
            PowerSample(start, 6.0),
            PowerSample(start + timedelta(minutes=5), -8.0),
            PowerSample(start + timedelta(minutes=10), 6.0),
        ],
        end_utc=start + timedelta(minutes=15),
        source_id="sensor.grid",
        stale_after_seconds=600,
    )
    assert len(quarters) == 1
    assert quarters[0].import_demand_kw == pytest.approx(4.0)
    assert quarters[0].signed_average_kw == pytest.approx(4 / 3)


def test_backfill_preserves_gaps_as_incomplete() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    quarters = reconstruct_quarters(
        [PowerSample(start, 2.0)],
        end_utc=start + timedelta(minutes=15),
        source_id="sensor.grid",
        stale_after_seconds=30,
    )
    assert quarters[0].quality == DataQuality.INCOMPLETE
    assert quarters[0].coverage_seconds == pytest.approx(30)
    assert quarters[0].gap_seconds == pytest.approx(870)


def test_historical_epoch_polarity_is_used_instead_of_current_polarity() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    readings = [HistoricalPowerReading(start, -6000, "W")]
    historical = normalize_historical_readings(readings, positive_means_import=False)
    current = normalize_historical_readings(readings, positive_means_import=True)
    assert historical[0].signed_kw == pytest.approx(6.0)
    assert current[0].signed_kw == pytest.approx(-6.0)
