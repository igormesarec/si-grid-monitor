"""Frozen specification formula tests."""

import pytest

from custom_components.si_grid_monitor.engine import calculate_projection, round_for_display


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


def test_unrecoverable_export_does_not_clear_warning_or_require_reduction() -> None:
    result = calculate_projection(
        target_kw=0.40,
        safety_margin_kw=0.0,
        import_kwh=0.101,
        elapsed_hours=0.20,
        remaining_hours=0.05,
        current_signed_power_kw=-0.44,
        smoothed_import_power_kw=0.0,
    )
    assert result.unrecoverable
    assert result.can_add_kw == 0
    assert result.must_reduce_kw == 0
    assert result.projected_exceedance


@pytest.mark.parametrize(
    ("raw", "displayed"),
    [(9.37873100104167, 9.38), (9.5309222859597, 9.53), (159.564090135, 159.56)],
)
def test_percentage_presentation_rounds_only_at_boundary(raw: float, displayed: float) -> None:
    assert round_for_display(raw, 2) == displayed


def test_separate_instant_and_smoothed_forecast_utilization() -> None:
    result = calculate_projection(
        target_kw=4.0,
        safety_margin_kw=0.0,
        import_kwh=0.25,
        elapsed_hours=0.125,
        remaining_hours=0.125,
        current_signed_power_kw=-2.0,
        smoothed_import_power_kw=1.0,
    )
    assert result.forecast_instant_kw == pytest.approx(1.0)
    assert result.forecast_smoothed_kw == pytest.approx(1.5)
    assert result.forecast_instant_utilization_pct == pytest.approx(25.0)
    assert result.forecast_smoothed_utilization_pct == pytest.approx(37.5)
