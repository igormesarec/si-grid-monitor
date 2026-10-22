"""V0.9.5 four-source-mode regression tests."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.si_grid_monitor.adapters import (
    AdapterError,
    ImportOnlyPowerAdapter,
    SeparatePowerAdapter,
    SignedPowerAdapter,
)
from custom_components.si_grid_monitor.const import (
    COUNTER_IMPORT_ONLY,
    COUNTER_NET,
    COUNTER_SEPARATE,
)
from custom_components.si_grid_monitor.engine import DataQuality, FixedQuarterEngine, PowerSample
from custom_components.si_grid_monitor.sources import CounterPowerConverter, CounterReading


def reading(value: float, unit: str, minute: int, second: int = 0) -> CounterReading:
    return CounterReading(value, unit, datetime(2026, 10, 21, 10, minute, second, tzinfo=UTC))


def test_exactly_four_public_source_modes() -> None:
    from custom_components.si_grid_monitor.sources import CAPABILITIES

    assert tuple(CAPABILITIES) == (
        "signed_power",
        "separate_power",
        "import_only",
        "cumulative_energy",
    )
    assert "aligned_quarter" not in CAPABILITIES


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


def test_mode_c_export_is_unknown_not_zero() -> None:
    normalized = ImportOnlyPowerAdapter().normalize(700, "W")
    assert normalized.import_kw == pytest.approx(0.7)
    assert normalized.export_kw is None
    assert not normalized.export_known


def test_mode_d_wh_and_kwh_derivative_and_duplicate() -> None:
    wh = CounterPowerConverter()
    assert wh.update(reading(1000, "Wh", 0)) is None
    interval = wh.update(reading(1500, "Wh", 15))
    assert interval is not None
    assert interval.import_kwh == pytest.approx(0.5)
    assert interval.normalized.import_kw == pytest.approx(2.0)
    assert interval.normalized.export_kw is None
    assert wh.update(reading(1500, "Wh", 15)) is None

    kwh = CounterPowerConverter()
    assert kwh.update(reading(20.0, "kWh", 0)) is None
    interval = kwh.update(reading(20.25, "kWh", 15))
    assert interval is not None
    assert interval.normalized.import_kw == pytest.approx(1.0)


def test_mode_d_optional_export_counter_is_not_netted_from_import() -> None:
    converter = CounterPowerConverter(behavior=COUNTER_SEPARATE, export_expected=True)
    assert converter.update(reading(10, "kWh", 0), reading(5, "kWh", 0)) is None
    interval = converter.update(reading(10.5, "kWh", 15), reading(5.25, "kWh", 15))
    assert interval is not None
    assert interval.normalized.import_kw == pytest.approx(2.0)
    assert interval.normalized.export_kw == pytest.approx(1.0)
    assert interval.normalized.signed_kw == pytest.approx(1.0)


def test_mode_d_counter_reset_establishes_new_baseline() -> None:
    converter = CounterPowerConverter()
    assert converter.update(reading(10, "kWh", 0)) is None
    with pytest.raises(AdapterError, match="reset"):
        converter.update(reading(1, "kWh", 15))
    recovered = converter.update(reading(1.25, "kWh", 30))
    assert recovered is not None
    assert recovered.normalized.import_kw == pytest.approx(1.0)


def test_mode_d_export_reset_does_not_discard_valid_import() -> None:
    converter = CounterPowerConverter(behavior=COUNTER_SEPARATE, export_expected=True)
    assert converter.update(reading(10, "kWh", 0), reading(5, "kWh", 0)) is None
    interval = converter.update(reading(10.25, "kWh", 15), reading(1, "kWh", 15))
    assert interval is not None
    assert interval.normalized.import_kw == pytest.approx(1.0)
    assert interval.normalized.export_kw is None
    recovered = converter.update(reading(10.5, "kWh", 30), reading(1.25, "kWh", 30))
    assert recovered is not None
    assert recovered.normalized.export_kw == pytest.approx(1.0)


def test_mode_d_bidirectional_net_counter_accepts_both_directions() -> None:
    converter = CounterPowerConverter(behavior=COUNTER_NET)
    assert converter.update(reading(10.0, "kWh", 0)) is None
    imported = converter.update(reading(10.25, "kWh", 15))
    exported = converter.update(reading(10.0, "kWh", 30))
    assert imported is not None and exported is not None
    assert imported.normalized.signed_kw == pytest.approx(1.0)
    assert imported.normalized.import_kw == pytest.approx(1.0)
    assert imported.normalized.export_kw == pytest.approx(0.0)
    assert exported.normalized.signed_kw == pytest.approx(-1.0)
    assert exported.normalized.import_kw == pytest.approx(0.0)
    assert exported.normalized.export_kw == pytest.approx(1.0)
    assert not imported.contractual_import_evidence
    assert not exported.contractual_import_evidence


def test_mode_d_bidirectional_net_counter_reverses_polarity() -> None:
    converter = CounterPowerConverter(
        behavior=COUNTER_NET,
        positive_means_import=False,
    )
    assert converter.update(reading(10.0, "kWh", 0)) is None
    exported = converter.update(reading(10.25, "kWh", 15))
    imported = converter.update(reading(10.0, "kWh", 30))
    assert exported is not None and imported is not None
    assert exported.normalized.signed_kw == pytest.approx(-1.0)
    assert imported.normalized.signed_kw == pytest.approx(1.0)


def test_mode_d_separate_counters_join_asynchronous_cadences_once() -> None:
    converter = CounterPowerConverter(behavior=COUNTER_SEPARATE, export_expected=True)
    assert converter.update_intervals(reading(0, "kWh", 0), reading(0, "kWh", 0)) == ()

    # Import reports at :15 and :30; export reports at :10, :20 and :30.
    assert converter.update_intervals(reading(0.5, "kWh", 15), reading(0, "kWh", 0)) == ()
    first = converter.update_intervals(reading(0.5, "kWh", 15), reading(0.1, "kWh", 10))
    second = converter.update_intervals(reading(0.5, "kWh", 15), reading(0.2, "kWh", 20))
    third = converter.update_intervals(reading(1.0, "kWh", 30), reading(0.3, "kWh", 30))

    intervals = (*first, *second, *third)
    assert [(item.start.minute, item.end.minute) for item in intervals] == [
        (0, 10),
        (10, 15),
        (15, 20),
        (20, 30),
    ]
    assert sum(item.import_kwh for item in intervals) == pytest.approx(1.0)
    assert sum(item.export_kwh or 0.0 for item in intervals) == pytest.approx(0.3)


def test_mode_d_separate_export_unavailable_keeps_import_and_rebaselines_export() -> None:
    converter = CounterPowerConverter(behavior=COUNTER_SEPARATE, export_expected=True)
    assert converter.update_intervals(reading(0, "kWh", 0), reading(0, "kWh", 0)) == ()
    import_only = converter.update_intervals(reading(0.25, "kWh", 15), None)
    assert len(import_only) == 1
    assert import_only[0].import_kwh == pytest.approx(0.25)
    assert import_only[0].export_kwh is None
    # First recovered export reading is a new baseline; its gap is not smeared.
    assert converter.update_intervals(reading(0.25, "kWh", 15), reading(0.5, "kWh", 15)) == ()
    recovered = converter.update_intervals(reading(0.5, "kWh", 30), reading(0.75, "kWh", 30))
    assert len(recovered) == 1
    assert recovered[0].import_kwh == pytest.approx(0.25)
    assert recovered[0].export_kwh == pytest.approx(0.25)


def test_mode_d_duplicate_timestamp_is_idempotent_but_conflict_is_rejected() -> None:
    converter = CounterPowerConverter(behavior=COUNTER_IMPORT_ONLY)
    baseline = reading(1.0, "kWh", 0)
    assert converter.update(baseline) is None
    assert converter.update(baseline) is None
    with pytest.raises(AdapterError, match="conflicting duplicate-timestamp"):
        converter.update(reading(1.1, "kWh", 0))


def test_mode_d_aligned_counter_interval_is_counter_derived() -> None:
    engine = FixedQuarterEngine(
        stale_after_seconds=60,
        source_id="counter",
        completed_quality=DataQuality.COUNTER_DERIVED,
    )
    start = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)
    completed = engine.ingest_interval_average(
        start=start,
        end=start + timedelta(minutes=15),
        signed_kw=2.0,
        import_kw=2.0,
        export_kw=None,
    )
    assert len(completed) == 1
    assert completed[0].import_kwh == pytest.approx(0.5)
    assert completed[0].quality == DataQuality.COUNTER_DERIVED
    assert engine.last_sample is None


def test_mode_d_cross_boundary_interval_is_never_confirmed() -> None:
    engine = FixedQuarterEngine(
        stale_after_seconds=600,
        source_id="counter",
        completed_quality=DataQuality.COUNTER_DERIVED,
    )
    start = datetime(2026, 10, 21, 10, 14, tzinfo=UTC)
    completed = engine.ingest_interval_average(
        start=start,
        end=start + timedelta(minutes=2),
        signed_kw=3.0,
        import_kw=3.0,
        export_kw=None,
    )
    assert completed[0].quality == DataQuality.INCOMPLETE
    assert completed[0].coverage_seconds == pytest.approx(60)
    assert completed[0].gap_seconds == pytest.approx(840)


def test_checkpoint_preserves_separate_import_export_semantics() -> None:
    start = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)
    original = FixedQuarterEngine(stale_after_seconds=900, source_id="separate")
    original.ingest(PowerSample(start, 1.0, import_kw=2.0, export_kw=1.0))
    original.advance(start + timedelta(minutes=5))
    payload = original.checkpoint()
    assert payload is not None

    restored = FixedQuarterEngine(stale_after_seconds=900, source_id="separate")
    assert restored.restore_checkpoint(payload)
    restored.advance(start + timedelta(minutes=15))
    assert restored.completed[0].import_demand_kw == pytest.approx(2.0)
    assert restored.completed[0].export_kwh == pytest.approx(0.25)
