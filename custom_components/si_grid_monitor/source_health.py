"""Durable source-health and measurement-quality reporting."""

from __future__ import annotations

import csv
import io
import math
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from .archive import QuarterArchive, SourceHealthIncident, archive_row_validity
from .engine import LJUBLJANA, quarter_bounds, quarter_starts_for_local_day

HEALTH_STATES = frozenset(
    {
        "healthy",
        "stale",
        "unavailable",
        "invalid_value",
        "missing_source_entity",
        "source_timestamp_mismatch",
        "configuration_transition",
        "runtime_restarting",
        "runtime_stopped",
        "unknown",
    }
)
INTERRUPTION_STATES = HEALTH_STATES - {"healthy"}
MAX_REPORT_DAYS = 366
MAX_CSV_ROWS = 10_000


def incident_dict(
    incident: SourceHealthIncident, *, now_utc: datetime | None = None
) -> dict[str, Any]:
    """Serialize one interval while keeping open-duration uncertainty explicit."""

    now = (now_utc or datetime.now(UTC)).astimezone(UTC)
    result = asdict(incident)
    for key in (
        "started_utc",
        "detected_utc",
        "last_valid_sample_utc",
        "ended_utc",
        "created_utc",
        "updated_utc",
    ):
        value = result[key]
        result[key] = value.isoformat() if value is not None else None
    end_unknown = incident.ended_utc is None or incident.recovery_code == "end_unknown_at_restart"
    if end_unknown:
        result["duration_seconds"] = None
        result["observed_open_seconds"] = (
            max(0.0, (now - incident.started_utc).total_seconds())
            if incident.ended_utc is None
            else None
        )
        result["duration_status"] = (
            "open_end_unknown" if incident.ended_utc is None else "restart_end_unknown"
        )
    else:
        result["duration_seconds"] = max(
            0.0, (incident.ended_utc - incident.started_utc).total_seconds()
        )
        result["observed_open_seconds"] = None
        result["duration_status"] = "closed_observed"
    result["start_local"] = incident.started_utc.astimezone(LJUBLJANA).isoformat()
    result["end_local"] = (
        incident.ended_utc.astimezone(LJUBLJANA).isoformat()
        if incident.ended_utc is not None
        else None
    )
    return result


def source_health_report(
    archive: QuarterArchive,
    namespace: str,
    start_utc: datetime,
    end_utc: datetime,
    *,
    states: tuple[str, ...] = (),
    source_epoch: int | None = None,
    page: int = 1,
    page_size: int = 50,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Return one bounded incident page and mathematically explicit metrics."""

    _validate_range(start_utc, end_utc)
    if not set(states).issubset(HEALTH_STATES):
        raise ValueError("unsupported source-health state")
    now = (now_utc or datetime.now(UTC)).astimezone(UTC)
    incidents, total = archive.list_source_health_incidents(
        namespace,
        start_utc,
        end_utc,
        health_states=states,
        source_epoch=source_epoch,
        page=page,
        page_size=page_size,
    )
    aggregate = archive.source_health_aggregate(
        namespace,
        start_utc,
        end_utc,
        health_states=states,
        source_epoch=source_epoch,
    )
    metric_intervals = archive.source_health_metric_intervals(
        namespace,
        start_utc,
        end_utc,
        health_states=states,
        source_epoch=source_epoch,
    )
    affected_quarters: set[str] = set()
    pattern_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in metric_intervals:
        started = datetime.fromisoformat(str(item["started_utc"])).astimezone(UTC)
        ended = (
            datetime.fromisoformat(str(item["ended_utc"])).astimezone(UTC)
            if item["ended_utc"] is not None
            else None
        )
        local = started.astimezone(LJUBLJANA)
        bucket = f"{local.hour:02d}:{0 if local.minute < 30 else 30:02d}"
        pattern_groups[(str(item["health_state"]), bucket)].append(item)
        uncertain_restart_end = item["recovery_code"] == "end_unknown_at_restart"
        interval_end = ended or min(now, end_utc)
        supported_start = max(start_utc, started)
        supported_end = min(end_utc, interval_end)
        if supported_end > supported_start and not uncertain_restart_end:
            cursor = quarter_bounds(supported_start).start_utc
            while cursor < supported_end:
                affected_quarters.add(cursor.isoformat())
                cursor += timedelta(minutes=15)
    quarter_rows = archive.list_quarters(namespace, start_utc, end_utc)
    incomplete = sum(str(row["quality"]) in {"incomplete", "unavailable"} for row in quarter_rows)
    missing_seconds = sum(float(row["gap_seconds"]) for row in quarter_rows)
    recurring_patterns = []
    for (state, bucket), grouped in sorted(pattern_groups.items()):
        dates = sorted(
            {
                datetime.fromisoformat(str(item["started_utc"]))
                .astimezone(LJUBLJANA)
                .date()
                .isoformat()
                for item in grouped
            }
        )
        if len(dates) < 2:
            continue
        closed_durations = [
            (
                datetime.fromisoformat(str(item["ended_utc"]))
                - datetime.fromisoformat(str(item["started_utc"]))
            ).total_seconds()
            for item in grouped
            if item["ended_utc"] is not None and item["recovery_code"] != "end_unknown_at_restart"
        ]
        recurring_patterns.append(
            {
                "classification": "repeated_interruptions_observed",
                "health_state": state,
                "local_half_hour_bucket": bucket,
                "occurrence_count": len(grouped),
                "distinct_date_count": len(dates),
                "dates": dates[:31],
                "minimum_supported_duration_seconds": min(closed_durations, default=None),
                "maximum_supported_duration_seconds": max(closed_durations, default=None),
                "causal_interpretation": None,
            }
        )
    local_today = now.astimezone(LJUBLJANA).date()
    today_starts = quarter_starts_for_local_day(local_today)
    today_start = today_starts[0]
    today_end = today_starts[-1] + timedelta(minutes=15)
    today_aggregate = archive.source_health_aggregate(namespace, today_start, today_end)
    today_intervals = archive.source_health_metric_intervals(namespace, today_start, today_end)
    today_affected: set[str] = set()
    for item in today_intervals:
        started = datetime.fromisoformat(str(item["started_utc"])).astimezone(UTC)
        ended = (
            datetime.fromisoformat(str(item["ended_utc"])).astimezone(UTC)
            if item["ended_utc"] is not None
            else None
        )
        supported_start = max(today_start, started)
        supported_end = min(today_end, ended or now)
        cursor = quarter_bounds(supported_start).start_utc
        while cursor < supported_end:
            today_affected.add(cursor.isoformat())
            cursor += timedelta(minutes=15)
    today_rows = archive.list_quarters(namespace, today_start, min(today_end, now))
    serialized_items = []
    for item in incidents:
        serialized = incident_dict(item, now_utc=now)
        overlap_end = min(end_utc, item.ended_utc or now)
        cursor = quarter_bounds(max(start_utc, item.started_utc)).start_utc
        affected = []
        while cursor < overlap_end:
            affected.append(cursor.isoformat())
            cursor += timedelta(minutes=15)
        serialized["affected_quarter_start_utcs"] = affected
        serialized_items.append(serialized)
    return {
        "range": {"start_utc": start_utc, "end_utc": end_utc},
        "items": serialized_items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": math.ceil(total / page_size) if total else 0,
        },
        "summary": {
            "incident_count": aggregate["incident_count"],
            "matching_transition_count": aggregate["matching_transition_count"],
            "unavailable_observed_seconds": aggregate["observed_seconds_by_state"].get(
                "unavailable", 0.0
            ),
            "stale_observed_seconds": aggregate["observed_seconds_by_state"].get("stale", 0.0),
            "unknown_duration_count": aggregate["unknown_duration_count"],
            "affected_quarter_count": len(affected_quarters),
            "incomplete_archived_quarter_count": incomplete,
            "quarter_record_missing_seconds": missing_seconds,
            "metrics_complete": True,
            "metrics_truncated": False,
            "incident_duration_is_not_quarter_gap_seconds": True,
            "first_transition_utc": aggregate["first_transition_utc"],
            "last_transition_utc": aggregate["last_transition_utc"],
        },
        "recurring_patterns": recurring_patterns,
        "facets": {"source_epochs": archive.source_health_epochs(namespace, start_utc, end_utc)},
        "today_summary": {
            "matching_transition_count": today_aggregate["matching_transition_count"],
            "metrics_complete": True,
            "metrics_truncated": False,
            "incident_count": today_aggregate["incident_count"],
            "affected_quarter_count": len(today_affected),
            "incomplete_archived_quarter_count": sum(
                str(row["quality"]) in {"incomplete", "unavailable"} for row in today_rows
            ),
        },
    }


def quality_report(
    archive: QuarterArchive,
    namespace: str,
    start_utc: datetime,
    end_utc: datetime,
    *,
    now_utc: datetime | None = None,
    tariff_block: int | None = None,
    source_epoch: int | None = None,
) -> dict[str, Any]:
    """Aggregate quarter completeness and measurement-time coverage separately."""

    _validate_range(start_utc, end_utc)
    now = (now_utc or datetime.now(UTC)).astimezone(UTC)
    completed_end = min(end_utc, quarter_bounds(now).start_utc)
    rows = archive.list_quarters(namespace, start_utc, completed_end)
    filtered_scope = tariff_block is not None or source_epoch is not None
    if tariff_block is not None:
        rows = [row for row in rows if row["tariff_block"] == tariff_block]
    if source_epoch is not None:
        rows = [row for row in rows if row["source_epoch"] == source_epoch]
    facets = archive.history_facets(
        namespace, start_utc, end_utc, completed_before_utc=completed_end
    )
    monitoring_value = facets.get("monitoring_started_utc")
    monitoring_start = (
        quarter_bounds(datetime.fromisoformat(str(monitoring_value))).start_utc
        if monitoring_value
        else start_utc
        if rows
        else completed_end
    )
    monitored_start = min(completed_end, max(start_utc, monitoring_start))
    expected_monitored = max(0, round((completed_end - monitored_start).total_seconds() / 900))
    expected_total = max(0, round((completed_end - start_utc).total_seconds() / 900))
    valid_rows = [row for row in rows if archive_row_validity(row).measured_valid]
    incomplete_rows = [row for row in rows if str(row["quality"]) == "incomplete"]
    unavailable_rows = [row for row in rows if str(row["quality"]) == "unavailable"]
    archived_monitored = [
        row
        for row in rows
        if datetime.fromisoformat(str(row["start_utc"])).astimezone(UTC) >= monitored_start
    ]
    # Missing rows have no evidence-backed block or source epoch. Never assign
    # them to a filtered category merely to complete its denominator.
    missing_count = None if filtered_scope else max(0, expected_monitored - len(archived_monitored))
    coverage_seconds = sum(float(row["coverage_seconds"]) for row in archived_monitored)
    applicable_seconds = None if filtered_scope else expected_monitored * 900.0
    confirmed_eligible = sum(archive_row_validity(row).contractual_eligible for row in rows)
    confirmed_exceeded = sum(archive_row_validity(row).confirmed_exceeded for row in rows)
    partial = [row for row in rows if not archive_row_validity(row).measured_valid]
    by_day: dict[date, list[Any]] = defaultdict(list)
    for row in rows:
        local_day = datetime.fromisoformat(str(row["start_utc"])).astimezone(LJUBLJANA).date()
        by_day[local_day].append(row)
    daily = []
    cursor = start_utc.astimezone(LJUBLJANA).date()
    last_day = (end_utc - timedelta(microseconds=1)).astimezone(LJUBLJANA).date()
    while cursor <= last_day:
        starts = quarter_starts_for_local_day(cursor)
        day_rows = by_day.get(cursor, [])
        day_completed = sum(start + timedelta(minutes=15) <= completed_end for start in starts)
        day_valid = sum(archive_row_validity(row).measured_valid for row in day_rows)
        day_coverage = sum(float(row["coverage_seconds"]) for row in day_rows)
        daily.append(
            {
                "date": cursor.isoformat(),
                "expected_calendar_quarters": len(starts),
                "completed_expected_quarters": day_completed,
                "archived_quarters": len(day_rows),
                "valid_quarters": day_valid,
                "incomplete_quarters": sum(str(row["quality"]) == "incomplete" for row in day_rows),
                "unavailable_quarters": sum(
                    str(row["quality"]) == "unavailable" for row in day_rows
                ),
                "measurement_coverage_seconds": day_coverage,
            }
        )
        cursor += timedelta(days=1)
    return {
        "range": {"start_utc": start_utc, "end_utc": end_utc},
        "summary": {
            "expected_calendar_quarters": max(
                0, round((end_utc - start_utc).total_seconds() / 900)
            ),
            "expected_completed_quarters": expected_total,
            "future_or_uncompleted_quarters": max(
                0,
                round((end_utc - start_utc).total_seconds() / 900) - expected_total,
            ),
            "expected_completed_monitored_quarters": (
                None if filtered_scope else expected_monitored
            ),
            "valid_completed_quarters": len(valid_rows),
            "incomplete_completed_quarters": len(incomplete_rows),
            "unavailable_completed_quarters": len(unavailable_rows),
            "missing_completed_monitored_quarters": missing_count,
            "pre_monitoring_completed_quarters": max(0, expected_total - expected_monitored),
            "confirmed_contractual_eligible_quarters": confirmed_eligible,
            "confirmed_exceedances": confirmed_exceeded,
            "unconfirmed_quarters": len(rows) - confirmed_eligible,
            "valid_import_kwh": sum(float(row["import_kwh"]) for row in valid_rows),
            "partial_observed_import_kwh": sum(float(row["import_kwh"]) for row in partial),
            "observed_export_kwh": sum(float(row["export_kwh"]) for row in rows),
            "measurement_coverage_seconds": coverage_seconds,
            "missing_measurement_seconds": (
                None
                if applicable_seconds is None
                else max(0.0, applicable_seconds - coverage_seconds)
            ),
            "quarter_completeness_pct": (
                100.0 * len(valid_rows) / expected_monitored
                if expected_monitored and not filtered_scope
                else None
            ),
            "measurement_time_coverage_pct": (
                100.0 * coverage_seconds / applicable_seconds if applicable_seconds else None
            ),
            "coverage_denominator_seconds": applicable_seconds,
            "denominator_scope": (
                "filtered_archived_records_only" if filtered_scope else "completed_monitored_time"
            ),
            "missing_intervals_unclassified_when_filtered": filtered_scope,
        },
        "daily": daily,
    }


def incomplete_quarter_report(
    archive: QuarterArchive,
    namespace: str,
    start_utc: datetime,
    end_utc: datetime,
    *,
    source_epoch: int | None = None,
) -> dict[str, Any]:
    """Return bounded incomplete/unavailable quarter evidence for CSV export."""

    _validate_range(start_utc, end_utc)
    total = archive.count_incomplete_quarters(
        namespace, start_utc, end_utc, source_epoch=source_epoch
    )
    rows = archive.list_incomplete_quarters(
        namespace,
        start_utc,
        end_utc,
        limit=MAX_CSV_ROWS,
        source_epoch=source_epoch,
    )
    items = []
    for row in rows:
        item = {
            key: row[key]
            for key in row.keys()  # noqa: SIM118 - sqlite Row iterates values
        }
        start = datetime.fromisoformat(str(item["start_utc"])).astimezone(UTC)
        item["start_local"] = start.astimezone(LJUBLJANA).isoformat()
        items.append(item)
    return {
        "range": {"start_utc": start_utc, "end_utc": end_utc},
        "items": items,
        "total": total,
        "exported_rows": len(items),
        "row_limit": MAX_CSV_ROWS,
        "truncated": total > len(items),
        "export_complete": total == len(items),
    }


def incident_export_report(
    archive: QuarterArchive,
    namespace: str,
    start_utc: datetime,
    end_utc: datetime,
    *,
    states: tuple[str, ...] = (),
    source_epoch: int | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Collect a complete filtered incident export through bounded SQLite pages."""

    _validate_range(start_utc, end_utc)
    if not set(states).issubset(HEALTH_STATES):
        raise ValueError("unsupported source-health state")
    first, total = archive.list_source_health_incidents(
        namespace,
        start_utc,
        end_utc,
        health_states=states,
        source_epoch=source_epoch,
        page=1,
        page_size=200,
        newest_first=False,
    )
    if total > MAX_CSV_ROWS:
        raise ValueError(
            f"filtered incident export contains {total} rows; narrow the date range or filters "
            f"to at most {MAX_CSV_ROWS} rows"
        )
    incidents = list(first)
    page = 2
    while len(incidents) < total:
        rows, confirmed_total = archive.list_source_health_incidents(
            namespace,
            start_utc,
            end_utc,
            health_states=states,
            source_epoch=source_epoch,
            page=page,
            page_size=200,
            newest_first=False,
        )
        if confirmed_total != total or not rows:
            raise ValueError("source-health export changed while it was being paged; retry")
        incidents.extend(rows)
        page += 1
    now = (now_utc or datetime.now(UTC)).astimezone(UTC)
    return {
        "range": {"start_utc": start_utc, "end_utc": end_utc},
        "items": [incident_dict(item, now_utc=now) for item in incidents],
        "total": total,
        "exported_rows": len(incidents),
        "row_limit": MAX_CSV_ROWS,
        "truncated": False,
        "export_complete": True,
        "filters": {"states": list(states), "source_epoch": source_epoch},
    }


def diagnostic_csv(kind: str, report: dict[str, Any]) -> str:
    """Create bounded UTF-8 CSV with spreadsheet-formula neutralization."""

    if report.get("truncated") or report.get("export_complete") is False:
        raise ValueError("diagnostic CSV export is incomplete; narrow the requested filters")

    if kind == "incidents":
        rows = report.get("items", [])[:MAX_CSV_ROWS]
        fields = (
            "incident_id",
            "source_epoch",
            "source_id",
            "health_state",
            "reason_code",
            "started_utc",
            "start_local",
            "ended_utc",
            "end_local",
            "duration_seconds",
            "last_valid_sample_utc",
            "recovery_code",
            "evidence_type",
        )
    elif kind == "quality":
        rows = report.get("daily", [])[:MAX_CSV_ROWS]
        fields = tuple(rows[0].keys()) if rows else ("date",)
    elif kind == "incomplete_quarters":
        rows = report.get("items", [])[:MAX_CSV_ROWS]
        fields = (
            "start_utc",
            "start_local",
            "end_utc",
            "quality",
            "coverage_seconds",
            "gap_seconds",
            "import_kwh",
            "export_kwh",
            "source_id",
            "source_epoch",
            "provenance",
            "configuration_status",
            "contractual_status",
            "tariff_block",
        )
    else:
        raise ValueError("unsupported diagnostic CSV kind")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _csv_safe(row.get(field)) for field in fields})
    return "\ufeff" + output.getvalue()


def _csv_safe(value: Any) -> Any:
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _validate_range(start_utc: datetime, end_utc: datetime) -> None:
    if start_utc.tzinfo is None or end_utc.tzinfo is None or end_utc <= start_utc:
        raise ValueError("source-health range must be positive and timezone-aware")
    if end_utc - start_utc > timedelta(days=MAX_REPORT_DAYS + 1):
        raise ValueError(f"source-health range cannot exceed {MAX_REPORT_DAYS} days")
