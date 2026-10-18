"""Regression coverage for metering without a verified tariff target."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.si_grid_monitor.archive import (
    ConfigurationResolution,
    ConfigurationStatus,
    QuarterArchive,
    archive_record_from_quarter,
)
from custom_components.si_grid_monitor.engine import FixedQuarterEngine, PowerSample
from custom_components.si_grid_monitor.tariffs import SlovenianTariffCalendar
from custom_components.si_grid_monitor.tariffs.calendar import LJUBLJANA
from custom_components.si_grid_monitor.tariffs.models import RuleStatus


def _utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=LJUBLJANA).astimezone(UTC)


def _configuration() -> ConfigurationResolution:
    return ConfigurationResolution(
        status=ConfigurationStatus.KNOWN,
        source_id="sensor.grid",
        positive_means_import=True,
        source_epoch=1,
        contractual_target_kw=4.8,
        safety_margin_kw=0.0,
        block_targets_kw=(4.8, 4.8, 4.8, 4.8, 4.8),
        allow_provisional_tariff=False,
    )


def test_2027_to_2028_keeps_metering_archiving_and_checkpointing(tmp_path) -> None:
    calendar = SlovenianTariffCalendar()
    before = _utc(2027, 12, 31, 23, 50)
    after = _utc(2028, 1, 1, 0, 5)
    assert calendar.classify(before).rule_status == RuleStatus.OFFICIAL
    assert calendar.classify(after).rule_status == RuleStatus.UNVERIFIED

    engine = FixedQuarterEngine(stale_after_seconds=3600, source_id="sensor.grid")
    engine.ingest(PowerSample(before, 4.0))
    completed = engine.ingest(PowerSample(after, 4.0))
    snapshot = engine.snapshot(now=after, target_kw=None)

    assert len(completed) == 1
    assert completed[0].import_kwh == pytest.approx(4 * 10 / 60)
    assert snapshot.current_signed_power_kw == 4.0
    assert snapshot.quarter_import_kwh == pytest.approx(4 * 5 / 60)
    assert snapshot.projection.forecast_instant_kw is None
    assert snapshot.projection.can_add_kw is None

    archive = QuarterArchive(tmp_path / "boundary.db")
    archive.open()
    record = archive_record_from_quarter(
        namespace="meter-a",
        quarter=completed[0],
        configuration=_configuration(),
        provenance="live_reconstructed",
        tariff=calendar.classify(completed[0].start_utc),
    )
    archive.upsert_quarter(record)
    archive.save_checkpoint("meter-a", engine.checkpoint())
    rows = archive.list_quarters("meter-a", completed[0].start_utc, completed[0].end_utc)
    assert len(rows) == 1
    assert rows[0]["import_kwh"] == pytest.approx(4 * 10 / 60)
    assert archive.load_checkpoint("meter-a") is not None
    archive.close()


@pytest.mark.parametrize("year", [2028, 2029, 2030])
def test_unverified_years_keep_physical_operation_without_advice(tmp_path, year: int) -> None:
    calendar = SlovenianTariffCalendar()
    start = _utc(year, 6, 5, 10, 0)
    tariff = calendar.classify(start)
    assert tariff.block is None
    assert tariff.rule_status == RuleStatus.UNVERIFIED

    engine = FixedQuarterEngine(stale_after_seconds=3600, source_id="sensor.grid")
    engine.ingest(PowerSample(start, 3.0))
    engine.ingest(PowerSample(start + timedelta(minutes=5), -2.0))
    completed = engine.ingest(PowerSample(start + timedelta(minutes=15), -2.0))
    snapshot = engine.snapshot(
        now=start + timedelta(minutes=15),
        target_kw=None,
        smoothing_seconds=120,
    )
    assert completed[0].import_kwh == pytest.approx(0.25)
    assert completed[0].export_kwh == pytest.approx(1 / 3)
    assert snapshot.current_signed_power_kw == -2.0
    assert snapshot.projection.operational_target_kw is None
    assert snapshot.projection.must_reduce_kw is None

    archive = QuarterArchive(tmp_path / f"{year}.db")
    archive.open()
    archived = archive_record_from_quarter(
        namespace="meter-a",
        quarter=completed[0],
        configuration=_configuration(),
        provenance="live_reconstructed",
        tariff=tariff,
    )
    assert archived.contractual_target_kw is None
    assert archived.contractual_status == "unavailable_rule"
    assert archived.exceeded is None
    archive.upsert_quarter(archived)
    archive.save_checkpoint("meter-a", engine.checkpoint())
    row = archive.list_quarters("meter-a", completed[0].start_utc, completed[0].end_utc)[0]
    assert row["import_kwh"] == pytest.approx(0.25)
    assert row["export_kwh"] == pytest.approx(1 / 3)
    assert row["contractual_status_reason"]
    assert archive.load_checkpoint("meter-a") is not None
    archive.close()
