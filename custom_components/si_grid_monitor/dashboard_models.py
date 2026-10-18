"""Pure dashboard view models shared by the WebSocket API and tests."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta
from typing import Any

from .archive import archive_row_validity, summarize_archive_rows
from .engine import LJUBLJANA, quarter_bounds, quarter_starts_for_local_day


def _completed_display_row(row: dict[str, Any]) -> dict[str, Any]:
    validity = archive_row_validity(row)
    return {
        **row,
        "display_status": "simulation" if row["simulation"] else "completed",
        "measurement_valid": validity.measured_valid,
        "contractual_eligible": validity.contractual_eligible,
        "confirmed_exceeded": validity.confirmed_exceeded,
        "export_average_kw": (
            float(row["export_kwh"]) / 0.25 if validity.measured_valid else None
        ),
        "projected_import_demand_kw": None,
    }


def _live_display_row(live: dict[str, Any]) -> dict[str, Any]:
    quarter = live["quarter"]
    projection = live.get("projection", {})
    tariff = live.get("tariff", {})
    elapsed = float(quarter.get("elapsed_seconds") or 0.0)
    elapsed_hours = elapsed / 3600.0
    return {
        "start_utc": quarter["start_utc"],
        "end_utc": quarter["end_utc"],
        "display_status": "live",
        "quality": quarter.get("quality", "unavailable"),
        "tariff_block": tariff.get("block"),
        "tariff_rule_status": tariff.get("rule_status"),
        "contractual_target_kw": tariff.get("target_kw"),
        "import_kwh": quarter.get("import_kwh"),
        "export_kwh": quarter.get("export_kwh"),
        "import_demand_kw": quarter.get("import_average_kw"),
        "export_average_kw": (
            float(quarter.get("export_kwh") or 0.0) / elapsed_hours
            if elapsed_hours > 0
            else None
        ),
        "projected_import_demand_kw": projection.get("forecast_smoothed_kw"),
        "elapsed_seconds": elapsed,
        "coverage_seconds": quarter.get("coverage_seconds"),
        "gap_seconds": quarter.get("gap_seconds"),
        "measurement_valid": False,
        "contractual_eligible": False,
        "confirmed_exceeded": False,
        "projected_exceedance": projection.get("projected_exceedance"),
    }


def build_day_view(
    *,
    runtime: Any,
    local_date: date,
    rows: list[dict[str, Any]],
    now_utc: datetime,
    live: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build one DST-correct daily view from immutable rows plus a live overlay."""

    starts = quarter_starts_for_local_day(local_date)
    current_start = quarter_bounds(now_utc).start_utc
    by_start = {str(row["start_utc"]): row for row in rows}
    live_row = _live_display_row(live) if live and live.get("available") else None
    quarters: list[dict[str, Any]] = []
    for quarter_start in starts:
        key = quarter_start.isoformat()
        stored = by_start.get(key)
        if stored is not None:
            quarters.append(_completed_display_row(stored))
            continue
        tariff = runtime.tariff_calendar.classify(quarter_start)
        base = {
            "start_utc": key,
            "end_utc": (quarter_start + timedelta(minutes=15)).isoformat(),
            "tariff_block": tariff.block,
            "tariff_rule_status": tariff.rule_status.value,
            "contractual_target_kw": runtime.target_for_tariff(tariff),
            "import_kwh": None,
            "export_kwh": None,
            "import_demand_kw": None,
            "export_average_kw": None,
            "projected_import_demand_kw": None,
            "confirmed_exceeded": False,
            "measurement_valid": False,
            "contractual_eligible": False,
        }
        if live_row is not None and key == live_row["start_utc"]:
            quarters.append(live_row)
        elif quarter_start >= current_start:
            status = "live_unavailable" if quarter_start == current_start else "upcoming"
            quarters.append(
                {
                    **base,
                    "display_status": status,
                    "quality": "unavailable" if status == "live_unavailable" else "upcoming",
                }
            )
        else:
            quarters.append({**base, "display_status": "missing", "quality": "missing"})

    summary = summarize_archive_rows(rows)
    blocks: list[dict[str, Any]] = []
    for block in range(1, 6):
        expected = [item for item in quarters if item.get("tariff_block") == block]
        archived = [row for row in rows if row.get("tariff_block") == block]
        classified = [(row, archive_row_validity(row)) for row in archived]
        valid = [row for row, validity in classified if validity.measured_valid]
        eligible = [row for row, validity in classified if validity.contractual_eligible]
        confirmed = sum(validity.confirmed_exceeded for _, validity in classified)
        demands = [float(row["import_demand_kw"]) for row in valid]
        targets = sorted(
            {
                float(row["contractual_target_kw"])
                for row, validity in classified
                if validity.included and row["contractual_target_kw"] is not None
            }
        )
        confirmed_targets = sorted(
            {float(row["contractual_target_kw"]) for row in eligible}
        )
        periods = [
            datetime.fromisoformat(item["start_utc"])
            .astimezone(LJUBLJANA)
            .strftime("%H:%M")
            for item in expected
        ]
        blocks.append(
            {
                "block": block,
                "active": bool(expected),
                "periods": periods,
                "active_hours": len(expected) * 0.25,
                "targets_kw": targets,
                "confirmed_targets_kw": confirmed_targets,
                "target_kw": targets[0] if len(targets) == 1 else None,
                "valid_count": len(valid),
                "contractual_eligible_count": len(eligible),
                "incomplete_count": sum(validity.incomplete for _, validity in classified),
                "missing_count": sum(item["display_status"] == "missing" for item in expected),
                "upcoming_count": sum(item["display_status"] == "upcoming" for item in expected),
                "maximum_import_demand_kw": max(demands, default=None),
                "average_import_demand_kw": sum(demands) / len(demands) if demands else None,
                "import_kwh": sum(float(row["import_kwh"]) for row in valid),
                "export_kwh": sum(float(row["export_kwh"]) for row in valid),
                "partial_observed_import_kwh": sum(
                    float(row["import_kwh"])
                    for row, validity in classified
                    if validity.included and not validity.measured_valid
                ),
                "partial_observed_export_kwh": sum(
                    float(row["export_kwh"])
                    for row, validity in classified
                    if validity.included and not validity.measured_valid
                ),
                "confirmed_exceedances": confirmed,
                "confirmed_exceedance_pct": (
                    100.0 * confirmed / len(eligible) if eligible else None
                ),
            }
        )
    return {
        "date": local_date.isoformat(),
        "expected_quarters": len(starts),
        "quarters": quarters,
        "summary": {
            **asdict(summary),
            "missing_count": sum(item["display_status"] == "missing" for item in quarters),
            "upcoming_count": sum(item["display_status"] == "upcoming" for item in quarters),
            "live_count": sum(item["display_status"] == "live" for item in quarters),
            "contractual_eligible_count": sum(
                archive_row_validity(row).contractual_eligible for row in rows
            ),
        },
        "blocks": blocks,
    }
