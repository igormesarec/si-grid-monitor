"""Source adapter tests."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.si_grid_monitor.adapters import (
    AdapterError,
    AlignedQuarterAdapter,
    ImportOnlyPowerAdapter,
    SeparatePowerAdapter,
    SignedPowerAdapter,
)
from custom_components.si_grid_monitor.engine import DataQuality


def test_signed_power_both_polarities_and_units() -> None:
    normal = SignedPowerAdapter(positive_means_import=True)
    assert normal.normalize(2400, "W").signed_kw == pytest.approx(2.4)
    assert normal.normalize(-2.4, "kW").export_kw == pytest.approx(2.4)

    reversed_adapter = SignedPowerAdapter(positive_means_import=False)
    sample = reversed_adapter.normalize(-2400, "W")
    assert sample.signed_kw == pytest.approx(2.4)
    assert sample.import_kw == pytest.approx(2.4)


def test_separate_power_validates_conflict() -> None:
    adapter = SeparatePowerAdapter()
    assert adapter.normalize(3000, "W", 0, "W").signed_kw == pytest.approx(3.0)
    assert adapter.normalize(0, "W", 1.5, "kW").signed_kw == pytest.approx(-1.5)
    with pytest.raises(AdapterError, match="simultaneous"):
        adapter.normalize(1000, "W", 500, "W")


def test_import_only_never_invents_export() -> None:
    sample = ImportOnlyPowerAdapter().normalize(800, "W")
    assert sample.signed_kw == pytest.approx(0.8)
    assert sample.export_kw is None
    assert not sample.export_known
    with pytest.raises(AdapterError, match="nonnegative"):
        ImportOnlyPowerAdapter().normalize(-1, "kW")


def test_bad_units_and_non_numeric_values_fail() -> None:
    adapter = SignedPowerAdapter()
    with pytest.raises(AdapterError, match="unsupported power unit"):
        adapter.normalize(10, "A")
    with pytest.raises(AdapterError, match="numeric"):
        adapter.normalize("unavailable", "W")


def test_aligned_quarter_adapter() -> None:
    start = datetime(2026, 10, 18, 8, 15, tzinfo=UTC)
    quarter = AlignedQuarterAdapter().from_import_demand(
        start=start,
        end=start + timedelta(minutes=15),
        value=4,
        unit="kW",
        export_kwh=0.25,
    )
    assert quarter.import_kwh == pytest.approx(1.0)
    assert quarter.import_demand_kw == pytest.approx(4.0)
    assert quarter.signed_average_kw == pytest.approx(3.0)
    assert quarter.quality == DataQuality.MEASURED_ALIGNED

    with pytest.raises(AdapterError, match="aligned"):
        AlignedQuarterAdapter().from_import_demand(
            start=start + timedelta(minutes=1),
            end=start + timedelta(minutes=16),
            value=1,
            unit="kWh",
        )
