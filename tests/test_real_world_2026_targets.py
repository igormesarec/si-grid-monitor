"""Real-world 2026 contracted-power validation fixture.

The target values are a user-provided distributor assignment, not integration
defaults.  Calendar block expectations below are independent fixtures from the
official 2026 hourly table.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from custom_components.si_grid_monitor.archive import (
    ConfigurationResolution,
    ConfigurationStatus,
    QuarterArchive,
    archive_record_from_quarter,
)
from custom_components.si_grid_monitor.contracted_power import (
    ContractedPowerPeriod,
    ContractedPowerSchedule,
)
from custom_components.si_grid_monitor.engine import (
    CompletedQuarter,
    DataQuality,
    calculate_projection,
)
from custom_components.si_grid_monitor.tariffs import SlovenianTariffCalendar
from custom_components.si_grid_monitor.tariffs.calendar import LJUBLJANA

REAL_2026_TARGETS = (3.50, 3.90, 4.10, 4.20, 4.20)
REAL_2026_PERIOD = ContractedPowerPeriod(
    effective_from=date(2026, 1, 1),
    effective_to=date(2026, 12, 31),
    block_targets_kw=REAL_2026_TARGETS,
    provenance="user-provided distributor assignment based on 15-minute measurements",
    recorded_on=date(2025, 10, 17),
)
REAL_SCHEDULE = ContractedPowerSchedule((REAL_2026_PERIOD,))


def local_utc(month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """Build an unambiguous 2026 Ljubljana instant on the UTC timeline."""

    return datetime(2026, month, day, hour, minute, tzinfo=LJUBLJANA).astimezone(UTC)


# Expected blocks are transcribed from the official 2026 patterns, rather than
# calculated from the implementation under test.
REPRESENTATIVE_BLOCKS = (
    (local_utc(1, 5, 7), 1, 3.50),  # higher-season working day
    (local_utc(1, 5, 6), 2, 3.90),
    (local_utc(1, 5, 0), 3, 4.10),
    (local_utc(7, 6, 0), 4, 4.20),  # lower-season working day
    (local_utc(7, 5, 0), 5, 4.20),  # lower-season Sunday
)


@pytest.mark.parametrize(("instant", "expected_block", "expected_target"), REPRESENTATIVE_BLOCKS)
def test_official_2026_calendar_selects_distributor_target(
    instant: datetime, expected_block: int, expected_target: float
) -> None:
    tariff = SlovenianTariffCalendar().classify(instant)

    assert tariff.block == expected_block
    assert tariff.verified is True
    assert REAL_SCHEDULE.target_for(tariff) == expected_target


@pytest.mark.parametrize(("instant", "expected_block", "target"), REPRESENTATIVE_BLOCKS)
def test_live_advice_and_forecasts_use_selected_block_target(
    instant: datetime, expected_block: int, target: float
) -> None:
    tariff = SlovenianTariffCalendar().classify(instant)
    selected_target = REAL_SCHEDULE.target_for(tariff)
    assert tariff.block == expected_block
    assert selected_target == target

    projection = calculate_projection(
        target_kw=selected_target,
        safety_margin_kw=0.0,
        import_kwh=0.50,
        elapsed_hours=1 / 6,
        remaining_hours=1 / 12,
        current_signed_power_kw=7.0,
        smoothed_import_power_kw=6.0,
    )
    allowed = max(0.0, (target * 0.25 - 0.50) / (1 / 12))

    assert projection.current_utilization_pct == pytest.approx(100 * 3.0 / target)
    assert projection.forecast_instant_kw == pytest.approx((0.50 + (1 / 12) * 7) / 0.25)
    assert projection.forecast_smoothed_kw == pytest.approx((0.50 + (1 / 12) * 6) / 0.25)
    assert projection.allowed_remaining_import_kw == pytest.approx(allowed)
    assert projection.can_add_kw == pytest.approx(max(0.0, allowed - 7.0))
    assert projection.must_reduce_kw == pytest.approx(max(0.0, 7.0 - allowed))


def test_archived_exceedances_retain_effective_2026_target_provenance(tmp_path) -> None:
    archive = QuarterArchive(tmp_path / "real-world-2026.db")
    archive.open()
    configuration = ConfigurationResolution(
        status=ConfigurationStatus.KNOWN,
        source_id="sensor.grid_power",
        positive_means_import=True,
        source_epoch=1,
        contractual_target_kw=4.8,
        safety_margin_kw=0.0,
        block_targets_kw=REAL_2026_TARGETS,
        allow_provisional_tariff=False,
    )

    for instant, expected_block, target in REPRESENTATIVE_BLOCKS:
        demand = target + 0.10
        quarter = CompletedQuarter(
            start_utc=instant,
            end_utc=instant + timedelta(minutes=15),
            import_kwh=demand * 0.25,
            export_kwh=0.0,
            signed_net_kwh=demand * 0.25,
            import_demand_kw=demand,
            signed_average_kw=demand,
            coverage_seconds=900,
            gap_seconds=0,
            quality=DataQuality.RECONSTRUCTED,
            source_id="sensor.grid_power",
        )
        tariff = SlovenianTariffCalendar().classify(instant)
        record = archive_record_from_quarter(
            namespace="real-world-2026",
            quarter=quarter,
            configuration=configuration,
            provenance=REAL_2026_PERIOD.provenance,
            tariff=tariff,
        )

        assert record.tariff_block == expected_block
        assert record.contractual_target_kw == target
        assert record.utilization_pct == pytest.approx(100 * demand / target)
        assert record.exceeded is True
        assert record.confirmed_exceeded is True
        assert record.contractual_status == "confirmed"
        assert record.tariff_policy == "official_only"
        archive.upsert_quarter(record)

    rows = archive.list_quarters(
        "real-world-2026", local_utc(1, 1, 0), local_utc(12, 31, 23) + timedelta(hours=1)
    )
    assert len(rows) == 5
    assert {(row["tariff_block"], row["contractual_target_kw"]) for row in rows} == {
        (1, 3.50),
        (2, 3.90),
        (3, 4.10),
        (4, 4.20),
        (5, 4.20),
    }
    summary = archive.summarize(
        "real-world-2026", local_utc(1, 1, 0), local_utc(12, 31, 23) + timedelta(hours=1)
    )
    assert summary.exceeded_count == 5
    assert summary.provisional_exceeded_count == 0
    archive.close()


def test_target_changes_at_official_tariff_transition() -> None:
    calendar = SlovenianTariffCalendar()
    before = calendar.classify(local_utc(1, 5, 6, 45))
    transition = calendar.next_transition(before.timestamp_utc)

    assert before.block == 2
    assert REAL_SCHEDULE.target_for(before) == 3.90
    assert transition is not None
    assert transition.local_datetime == datetime(2026, 1, 5, 7, 0, tzinfo=LJUBLJANA)
    assert transition.block == 1
    assert REAL_SCHEDULE.target_for(transition) == 3.50

    before_projection = calculate_projection(
        target_kw=3.90,
        safety_margin_kw=0.0,
        import_kwh=0.50,
        elapsed_hours=1 / 6,
        remaining_hours=1 / 12,
        current_signed_power_kw=5.0,
        smoothed_import_power_kw=5.0,
    )
    after_projection = calculate_projection(
        target_kw=3.50,
        safety_margin_kw=0.0,
        import_kwh=0.50,
        elapsed_hours=1 / 6,
        remaining_hours=1 / 12,
        current_signed_power_kw=5.0,
        smoothed_import_power_kw=5.0,
    )
    assert after_projection.allowed_remaining_import_kw < (
        before_projection.allowed_remaining_import_kw or 0
    )
    assert after_projection.can_add_kw < (before_projection.can_add_kw or 0)
    assert after_projection.must_reduce_kw > (before_projection.must_reduce_kw or 0)


def test_contracted_power_period_does_not_leak_into_future_years() -> None:
    calendar = SlovenianTariffCalendar(allow_provisional=True)
    assert REAL_SCHEDULE.period_for(date(2025, 12, 31)) is None
    assert REAL_SCHEDULE.period_for(date(2027, 1, 1)) is None
    assert REAL_SCHEDULE.period_for(date(2030, 12, 31)) is None
    assert REAL_SCHEDULE.target_for(calendar.classify(datetime(2027, 1, 1, tzinfo=UTC))) is None

    synthetic_2027 = ContractedPowerPeriod(
        effective_from=date(2027, 1, 1),
        effective_to=date(2027, 12, 31),
        block_targets_kw=(5.0, 5.1, 5.2, 5.3, 5.4),
        provenance="synthetic future-period test only",
    )
    multi_year = ContractedPowerSchedule((REAL_2026_PERIOD, synthetic_2027))
    tariff_2027 = calendar.classify(datetime(2027, 1, 4, 7, tzinfo=LJUBLJANA))
    assert tariff_2027.block == 1
    assert multi_year.target_for(tariff_2027) == 5.0
    assert multi_year.period_for(date(2028, 1, 1)) is None
