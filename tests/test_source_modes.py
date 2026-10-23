"""V1.0 three-source-mode regression tests."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.si_grid_monitor.adapters import (
    AdapterError,
    ImportOnlyPowerAdapter,
    SeparatePowerAdapter,
    SignedPowerAdapter,
)
from custom_components.si_grid_monitor.const import (
    SOURCE_CUMULATIVE_ENERGY,
    SUPPORTED_SOURCE_MODES,
)
from custom_components.si_grid_monitor.engine import FixedQuarterEngine, PowerSample, PowerSegment
from custom_components.si_grid_monitor.sustained import (
    ForecastQuality,
    calculate_sustained_forecast,
)


def test_exactly_three_public_source_modes() -> None:
    assert SUPPORTED_SOURCE_MODES == (
        "signed_power",
        "separate_power",
        "import_only",
    )
    assert SOURCE_CUMULATIVE_ENERGY not in SUPPORTED_SOURCE_MODES


def test_mode_a_preserves_signed_polarity() -> None:
    assert SignedPowerAdapter(positive_means_import=True).normalize(2500, "W").signed_kw == 2.5
    assert SignedPowerAdapter(positive_means_import=False).normalize(-2.5, "kW").import_kw == 2.5


def test_mode_b_preserves_separate_import_export_and_rejects_conflict() -> None:
    adapter = SeparatePowerAdapter()
    imported = adapter.normalize(1200, "W", 0, "W")
    exported = adapter.normalize(0, "kW", 1.7, "kW")
    assert (imported.import_kw, imported.export_kw, imported.signed_kw) == (1.2, 0.0, 1.2)
    assert (exported.import_kw, exported.export_kw, exported.signed_kw) == (0.0, 1.7, -1.7)
    with pytest.raises(AdapterError, match="conflicting simultaneous"):
        adapter.normalize(0.5, "kW", 0.2, "kW")


def test_mode_b_engine_never_nets_export_against_import() -> None:
    engine = FixedQuarterEngine(stale_after_seconds=1000)
    start = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)
    engine.ingest(PowerSample(start, 1.0, import_kw=2.0, export_kw=1.0))
    engine.advance(start + timedelta(minutes=15))
    quarter = engine.completed[0]
    assert quarter.import_kwh == pytest.approx(0.5)
    assert quarter.export_kwh == pytest.approx(0.25)
    assert quarter.import_demand_kw == pytest.approx(2.0)
    assert quarter.signed_average_kw == pytest.approx(1.0)


def test_mode_b_asynchronous_updates_preserve_each_evidenced_direction() -> None:
    """A changed channel uses the latest fresh peer without netting energies."""

    engine = FixedQuarterEngine(stale_after_seconds=1000)
    start = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)
    samples = (
        (start, 1.0, 0.0),
        (start + timedelta(minutes=5), 2.0, 0.0),
        (start + timedelta(minutes=10), 0.0, 1.0),
    )
    for timestamp, imported, exported in samples:
        engine.ingest(
            PowerSample(
                timestamp,
                imported - exported,
                import_kw=imported,
                export_kw=exported,
            )
        )
    engine.advance(start + timedelta(minutes=15))

    quarter = engine.completed[0]
    assert quarter.import_kwh == pytest.approx(0.25)
    assert quarter.export_kwh == pytest.approx(1 / 12)
    assert quarter.import_demand_kw == pytest.approx(1.0)
    assert quarter.export_evidence == "measured"


def test_mode_c_export_is_unknown_not_zero() -> None:
    normalized = ImportOnlyPowerAdapter().normalize(700, "W")
    assert normalized.import_kw == pytest.approx(0.7)
    assert normalized.export_kw is None
    assert not normalized.export_known


def test_mode_c_quarter_keeps_import_valid_and_export_unknown() -> None:
    engine = FixedQuarterEngine(stale_after_seconds=1000)
    start = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)
    normalized = ImportOnlyPowerAdapter().normalize(2.0, "kW")
    engine.ingest(
        PowerSample(
            start,
            normalized.signed_kw,
            import_kw=normalized.import_kw,
            export_kw=normalized.export_kw,
            export_known=normalized.export_known,
        )
    )
    engine.advance(start + timedelta(minutes=15))
    quarter = engine.completed[0]
    assert quarter.import_kwh == pytest.approx(0.5)
    assert quarter.import_demand_kw == pytest.approx(2.0)
    assert quarter.export_kwh == pytest.approx(0.0)
    assert quarter.export_coverage_seconds == pytest.approx(0.0)
    assert quarter.export_unknown_seconds == pytest.approx(900.0)
    assert quarter.export_evidence == "unknown"


def test_mode_c_sustained_advice_recovers_after_required_valid_history() -> None:
    now = datetime(2026, 10, 21, 10, 5, tzinfo=UTC)

    insufficient = calculate_sustained_forecast(
        now=now,
        current_import_kwh=0.1,
        current_unrecoverable=False,
        recent_segments=(PowerSegment(90, 1.0),),
        latest_signed_kw=1.0,
        measurement_age_seconds=0,
        smoothing_seconds=120,
        horizon_minutes=60,
        target_for_quarter=lambda _start, _end: 4.8,
        stale_after_seconds=60,
    )
    recovered = calculate_sustained_forecast(
        now=now,
        current_import_kwh=0.1,
        current_unrecoverable=False,
        recent_segments=(PowerSegment(120, 1.0),),
        latest_signed_kw=1.0,
        measurement_age_seconds=0,
        smoothing_seconds=120,
        horizon_minutes=60,
        target_for_quarter=lambda _start, _end: 4.8,
        stale_after_seconds=60,
    )

    assert insufficient.quality == ForecastQuality.INSUFFICIENT_COVERAGE
    assert recovered.quality == ForecastQuality.AVAILABLE
    assert recovered.can_add_kw is not None
