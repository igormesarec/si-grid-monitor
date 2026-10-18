"""Behavioral contracts for V0.4 Today/archive view models."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from custom_components.si_grid_monitor.archive import summarize_archive_rows
from custom_components.si_grid_monitor.dashboard_models import build_day_view
from custom_components.si_grid_monitor.engine import quarter_starts_for_local_day
from custom_components.si_grid_monitor.tariffs import SlovenianTariffCalendar


class RuntimeStub:
    def __init__(self) -> None:
        self.tariff_calendar = SlovenianTariffCalendar()

    @staticmethod
    def target_for_tariff(tariff: object) -> float | None:
        block = getattr(tariff, "block", None)
        return None if block is None else (3.5, 3.9, 4.1, 4.2, 4.2)[block - 1]


def row(
    start: datetime,
    *,
    block: int = 1,
    import_kwh: float = 0.75,
    export_kwh: float = 0.25,
    quality: str = "reconstructed",
    configuration_status: str = "known",
    contractual_status: str = "confirmed",
    rule_status: str = "official",
    simulation: bool = False,
    confirmed_exceeded: int | None = 0,
) -> dict[str, object]:
    target = (3.5, 3.9, 4.1, 4.2, 4.2)[block - 1]
    return {
        "start_utc": start.isoformat(),
        "end_utc": (start + timedelta(minutes=15)).isoformat(),
        "import_kwh": import_kwh,
        "export_kwh": export_kwh,
        "signed_average_kw": 2.0,
        "import_demand_kw": import_kwh / 0.25,
        "quality": quality,
        "configuration_status": configuration_status,
        "contractual_target_kw": target,
        "tariff_block": block,
        "tariff_rule_status": rule_status,
        "contractual_status": contractual_status,
        "simulation": int(simulation),
        "confirmed_exceeded": confirmed_exceeded,
        "exceeded": int(import_kwh / 0.25 > target),
    }


def live(start: datetime) -> dict[str, object]:
    return {
        "available": True,
        "now_utc": (start + timedelta(minutes=7)).isoformat(),
        "quarter": {
            "start_utc": start.isoformat(),
            "end_utc": (start + timedelta(minutes=15)).isoformat(),
            "elapsed_seconds": 420.0,
            "import_kwh": 0.35,
            "export_kwh": 0.07,
            "import_average_kw": 3.0,
            "coverage_seconds": 390.0,
            "gap_seconds": 30.0,
            "quality": "reconstructed",
        },
        "projection": {"forecast_smoothed_kw": 3.4, "projected_exceedance": False},
        "tariff": {"block": 2, "rule_status": "official", "target_kw": 3.9},
    }


def test_today_live_upcoming_and_missing_are_distinct() -> None:
    now = datetime(2026, 1, 5, 9, 7, tzinfo=UTC)
    current = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
    previous = current - timedelta(minutes=30)
    view = build_day_view(
        runtime=RuntimeStub(),
        local_date=date(2026, 1, 5),
        rows=[row(previous)],
        now_utc=now,
        live=live(current),
    )
    statuses = {item["start_utc"]: item["display_status"] for item in view["quarters"]}
    assert statuses[previous.isoformat()] == "completed"
    assert statuses[(current - timedelta(minutes=15)).isoformat()] == "missing"
    assert statuses[current.isoformat()] == "live"
    assert statuses[(current + timedelta(minutes=15)).isoformat()] == "upcoming"
    live_row = next(item for item in view["quarters"] if item["display_status"] == "live")
    assert live_row["import_kwh"] == pytest.approx(0.35)
    assert live_row["export_kwh"] == pytest.approx(0.07)
    assert live_row["projected_import_demand_kw"] == pytest.approx(3.4)
    assert not live_row["contractual_eligible"]
    assert view["summary"]["live_count"] == 1


def test_live_quarter_becomes_completed_after_boundary_archive() -> None:
    completed_start = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
    new_start = completed_start + timedelta(minutes=15)
    view = build_day_view(
        runtime=RuntimeStub(),
        local_date=date(2026, 1, 5),
        rows=[row(completed_start)],
        now_utc=new_start + timedelta(seconds=30),
        live=live(new_start),
    )
    values = {item["start_utc"]: item for item in view["quarters"]}
    assert values[completed_start.isoformat()]["display_status"] == "completed"
    assert values[new_start.isoformat()]["display_status"] == "live"


def test_block_statistics_reconcile_and_exclude_unconfirmed_data() -> None:
    start = datetime(2026, 1, 5, 5, 0, tzinfo=UTC)
    rows = [
        row(start, block=2, import_kwh=1.1, confirmed_exceeded=1),
        row(
            start + timedelta(minutes=15),
            block=2,
            contractual_status="provisional_estimate",
            rule_status="provisional",
            confirmed_exceeded=None,
        ),
        row(start + timedelta(minutes=30), block=2, simulation=True, confirmed_exceeded=1),
        row(
            start + timedelta(minutes=45),
            block=2,
            quality="incomplete",
            confirmed_exceeded=None,
        ),
        row(
            start + timedelta(minutes=60),
            block=1,
            configuration_status="legacy_unverified",
            confirmed_exceeded=None,
        ),
    ]
    view = build_day_view(
        runtime=RuntimeStub(),
        local_date=date(2026, 1, 5),
        rows=rows,
        now_utc=datetime(2026, 1, 6, tzinfo=UTC),
        live=None,
    )
    summary = summarize_archive_rows(rows)
    assert sum(block["valid_count"] for block in view["blocks"]) == summary.valid_count
    assert sum(block["import_kwh"] for block in view["blocks"]) == pytest.approx(
        summary.import_kwh
    )
    assert sum(block["export_kwh"] for block in view["blocks"]) == pytest.approx(
        summary.export_kwh
    )
    assert sum(block["confirmed_exceedances"] for block in view["blocks"]) == 1
    block_two = view["blocks"][1]
    assert block_two["valid_count"] == 2
    assert block_two["contractual_eligible_count"] == 1
    assert block_two["incomplete_count"] == 1
    assert block_two["confirmed_exceedance_pct"] == pytest.approx(100.0)


@pytest.mark.parametrize(
    ("selected", "count"),
    ((date(2026, 3, 29), 92), (date(2026, 10, 25), 100), (date(2026, 4, 2), 96)),
)
def test_today_preserves_dst_quarter_counts(selected: date, count: int) -> None:
    starts = quarter_starts_for_local_day(selected)
    view = build_day_view(
        runtime=RuntimeStub(),
        local_date=selected,
        rows=[],
        now_utc=starts[-1] + timedelta(days=1),
        live=None,
    )
    assert view["expected_quarters"] == count
    assert len(view["quarters"]) == count
