"""Frozen specification formula tests."""

import pytest

from custom_components.si_grid_monitor.engine import calculate_projection


def test_concrete_positive_import_example() -> None:
    result = calculate_projection(
        target_kw=4.8,
        safety_margin_kw=0.0,
        import_kwh=0.70,
        elapsed_hours=10 / 60,
        remaining_hours=5 / 60,
        current_signed_power_kw=3.0,
        smoothed_signed_power_kw=3.0,
    )
    assert result.forecast_instant_kw == pytest.approx(3.80)
    assert result.budget_remaining_kwh == pytest.approx(0.50)
    assert result.allowed_remaining_import_kw == pytest.approx(6.00)
    assert result.can_add_kw == pytest.approx(3.00)
    assert result.must_reduce_kw == pytest.approx(0.00)
    assert not result.unrecoverable


def test_concrete_export_surplus_example() -> None:
    result = calculate_projection(
        target_kw=4.8,
        safety_margin_kw=0.0,
        import_kwh=0.70,
        elapsed_hours=10 / 60,
        remaining_hours=5 / 60,
        current_signed_power_kw=-2.0,
        smoothed_signed_power_kw=-2.0,
    )
    assert result.forecast_instant_kw == pytest.approx(2.80)
    assert result.allowed_remaining_import_kw == pytest.approx(6.00)
    assert result.can_add_kw == pytest.approx(8.00)
    assert result.must_reduce_kw == pytest.approx(0.00)


def test_unrecoverable_does_not_pretend_energy_can_be_undone() -> None:
    result = calculate_projection(
        target_kw=4.0,
        safety_margin_kw=0.0,
        import_kwh=1.01,
        elapsed_hours=0.2,
        remaining_hours=0.05,
        current_signed_power_kw=2.5,
        smoothed_signed_power_kw=2.0,
    )
    assert result.unrecoverable
    assert result.allowed_remaining_import_kw == 0
    assert result.can_add_kw == 0
    assert result.must_reduce_kw == pytest.approx(2.5)


def test_margin_changes_operational_not_contractual_utilization() -> None:
    result = calculate_projection(
        target_kw=5.0,
        safety_margin_kw=0.5,
        import_kwh=0.5,
        elapsed_hours=0.125,
        remaining_hours=0.125,
        current_signed_power_kw=2.0,
        smoothed_signed_power_kw=2.0,
    )
    assert result.operational_target_kw == pytest.approx(4.5)
    assert result.budget_kwh == pytest.approx(1.125)
    assert result.current_utilization_pct == pytest.approx(80.0)
    assert result.forecast_instant_kw == pytest.approx(3.0)
    assert result.forecast_utilization_pct == pytest.approx(60.0)


def test_zero_remaining_time_never_divides_by_zero() -> None:
    result = calculate_projection(
        target_kw=5.0,
        safety_margin_kw=0.0,
        import_kwh=1.0,
        elapsed_hours=0.25,
        remaining_hours=0.0,
        current_signed_power_kw=2.0,
        smoothed_signed_power_kw=2.0,
    )
    assert result.allowed_remaining_import_kw is None
    assert result.can_add_kw is None
    assert result.forecast_instant_kw == pytest.approx(4.0)
