"""Shared calendar and archive analysis for Period, Blocks, and Exceedances."""

from __future__ import annotations

import calendar
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import Any

from .archive import QuarterArchive
from .engine import LJUBLJANA, quarter_bounds

MAX_QUERY_DAYS = 3660


class PeriodType(StrEnum):
    """Supported calendar selections."""

    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class PeriodBounds:
    """One half-open local-calendar period represented canonically in UTC."""

    period_type: PeriodType
    start_utc: datetime
    end_utc: datetime
    start_local: datetime
    end_local: datetime
    label: str


def _local_midnight(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=LJUBLJANA)


def _month_start(year: int, month: int) -> date:
    return date(year, month, 1)


def _next_month(value: date) -> date:
    return date(value.year + (value.month == 12), value.month % 12 + 1, 1)


def _as_local_anchor(anchor: date | datetime) -> datetime:
    if isinstance(anchor, datetime):
        if anchor.tzinfo is None or anchor.utcoffset() is None:
            raise ValueError("datetime period anchors must include a UTC offset")
        return anchor.astimezone(LJUBLJANA)
    return _local_midnight(anchor)


def resolve_period(
    period_type: PeriodType | str,
    anchor: date | datetime,
    *,
    custom_start: date | None = None,
    custom_end: date | None = None,
) -> PeriodBounds:
    """Resolve a selection using Ljubljana calendar semantics and [start,end)."""

    kind = PeriodType(period_type)
    local_anchor = _as_local_anchor(anchor)
    anchor_date = local_anchor.date()
    if kind is PeriodType.HOUR:
        start_local = local_anchor.replace(minute=0, second=0, microsecond=0)
        start_utc = local_anchor.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        end_utc = start_utc + timedelta(hours=1)
        end_local = end_utc.astimezone(LJUBLJANA)
        label = (
            f"{start_local:%Y-%m-%d %H:%M} {start_local.tzname()}-"
            f"{end_local:%H:%M} {end_local.tzname()}"
        )
        return PeriodBounds(kind, start_utc, end_utc, start_local, end_local, label)
    if kind is PeriodType.DAY:
        start_date, end_date = anchor_date, anchor_date + timedelta(days=1)
    elif kind is PeriodType.WEEK:
        start_date = anchor_date - timedelta(days=anchor_date.weekday())
        end_date = start_date + timedelta(days=7)
    elif kind is PeriodType.MONTH:
        start_date = _month_start(anchor_date.year, anchor_date.month)
        end_date = _next_month(start_date)
    elif kind is PeriodType.YEAR:
        start_date, end_date = date(anchor_date.year, 1, 1), date(anchor_date.year + 1, 1, 1)
    else:
        if custom_start is None or custom_end is None:
            raise ValueError("custom periods require start and end dates")
        if custom_end < custom_start:
            raise ValueError("custom end date must not precede start date")
        if (custom_end - custom_start).days + 1 > MAX_QUERY_DAYS:
            raise ValueError(f"custom periods are limited to {MAX_QUERY_DAYS} days")
        start_date, end_date = custom_start, custom_end + timedelta(days=1)
    start_local = _local_midnight(start_date)
    end_local = _local_midnight(end_date)
    if kind is PeriodType.DAY:
        label = f"{start_date:%Y-%m-%d}"
    elif kind is PeriodType.WEEK:
        iso = start_date.isocalendar()
        last_date = end_date - timedelta(days=1)
        label = f"{iso.year}-W{iso.week:02d} · {start_date:%Y-%m-%d}-{last_date:%Y-%m-%d}"
    elif kind is PeriodType.MONTH:
        label = f"{calendar.month_name[start_date.month]} {start_date.year}"
    elif kind is PeriodType.YEAR:
        label = str(start_date.year)
    else:
        label = f"{start_date:%Y-%m-%d}-{end_date - timedelta(days=1):%Y-%m-%d}"
    return PeriodBounds(
        kind,
        start_local.astimezone(UTC),
        end_local.astimezone(UTC),
        start_local,
        end_local,
        label,
    )


def previous_period(bounds: PeriodBounds) -> PeriodBounds:
    """Return the immediately preceding equivalent local-calendar period."""

    kind = bounds.period_type
    if kind is PeriodType.HOUR:
        return resolve_period(kind, bounds.start_utc - timedelta(hours=1))
    start_date = bounds.start_local.date()
    if kind is PeriodType.DAY:
        return resolve_period(kind, start_date - timedelta(days=1))
    if kind is PeriodType.WEEK:
        return resolve_period(kind, start_date - timedelta(days=7))
    if kind is PeriodType.MONTH:
        prior_end = start_date - timedelta(days=1)
        return resolve_period(kind, prior_end)
    if kind is PeriodType.YEAR:
        return resolve_period(kind, date(start_date.year - 1, 1, 1))
    days = (bounds.end_local.date() - start_date).days
    return resolve_period(
        kind,
        start_date - timedelta(days=days),
        custom_start=start_date - timedelta(days=days),
        custom_end=start_date - timedelta(days=1),
    )


def next_period(bounds: PeriodBounds) -> PeriodBounds:
    """Return the next equivalent local-calendar period."""

    kind = bounds.period_type
    if kind is PeriodType.HOUR:
        return resolve_period(kind, bounds.end_utc)
    end_date = bounds.end_local.date()
    if kind in {PeriodType.DAY, PeriodType.WEEK, PeriodType.MONTH, PeriodType.YEAR}:
        return resolve_period(kind, end_date)
    days = (end_date - bounds.start_local.date()).days
    return resolve_period(
        kind,
        end_date,
        custom_start=end_date,
        custom_end=end_date + timedelta(days=days - 1),
    )


def chart_resolution(bounds: PeriodBounds) -> str:
    """Choose a bounded chart resolution without losing quarter maxima."""

    duration = bounds.end_utc - bounds.start_utc
    if bounds.period_type in {PeriodType.HOUR, PeriodType.DAY} or duration <= timedelta(days=2):
        return "quarter"
    if bounds.period_type is PeriodType.WEEK:
        return "hour"
    if bounds.period_type is PeriodType.MONTH or duration <= timedelta(days=62):
        return "day"
    return "month"


def _bin_key(timestamp: datetime, resolution: str) -> str:
    local = timestamp.astimezone(LJUBLJANA)
    if resolution == "quarter":
        return timestamp.astimezone(UTC).isoformat()
    if resolution == "hour":
        offset = int((local.utcoffset() or timedelta()).total_seconds())
        return f"{local:%Y-%m-%dT%H}|{offset}|{local.fold}"
    if resolution == "day":
        return local.date().isoformat()
    return f"{local.year:04d}-{local.month:02d}"


def _row_dict(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}  # noqa: SIM118 - sqlite3.Row values differ


def _number(value: Any, default: float = 0.0) -> float:
    return default if value is None else float(value)


def _integer(value: Any) -> int:
    return 0 if value is None else int(value)


def _expected_bins(
    bounds: PeriodBounds,
    completed_end: datetime,
    resolution: str,
    tariff_block: int | None,
    classifier: Callable[[datetime], Any] | None,
) -> tuple[Counter[str], dict[str, tuple[str, str]]]:
    expected: Counter[str] = Counter()
    intervals: dict[str, tuple[str, str]] = {}
    classified_hours: dict[datetime, int | None] = {}
    cursor = bounds.start_utc
    while cursor < completed_end:
        classified_block: int | None = None
        if tariff_block is not None and classifier is not None:
            hour = cursor.replace(minute=0, second=0, microsecond=0)
            if hour not in classified_hours:
                classified_hours[hour] = getattr(classifier(hour), "block", None)
            classified_block = classified_hours[hour]
        if tariff_block is None or classified_block == tariff_block:
            key = _bin_key(cursor, resolution)
            expected[key] += 1
            start = cursor.astimezone(UTC).isoformat()
            end = (cursor + timedelta(minutes=15)).astimezone(UTC).isoformat()
            if key in intervals:
                intervals[key] = (intervals[key][0], end)
            else:
                intervals[key] = (start, end)
        cursor += timedelta(minutes=15)
    return expected, intervals


def _comparison_quality(summary: dict[str, Any]) -> dict[str, Any]:
    """Describe whether a completed period has fully comparable measurements."""

    expected = int(summary["expected_completed_count"])
    valid = int(summary["valid_count"])
    missing = int(summary["missing_count"])
    incomplete = int(summary["incomplete_count"])
    complete = expected > 0 and valid == expected and missing == 0 and incomplete == 0
    return {
        "comparable": complete,
        "expected_count": expected,
        "valid_count": valid,
        "incomplete_count": incomplete,
        "missing_count": missing,
        "coverage_pct": summary["coverage_pct"],
    }


def _normalize_summary(row: Any, expected_count: int) -> dict[str, Any]:
    values = _row_dict(row)
    integer_fields = (
        "archived_count",
        "valid_count",
        "contractual_eligible_count",
        "incomplete_count",
        "unknown_configuration_count",
        "valid_without_confirmed_target_count",
        "exceeded_count",
        "provisional_exceeded_count",
        "simulation_count",
    )
    for key in integer_fields:
        values[key] = _integer(values.get(key))
    for key in (
        "import_kwh",
        "export_kwh",
        "partial_observed_import_kwh",
        "partial_observed_export_kwh",
    ):
        values[key] = _number(values.get(key))
    values["signed_net_kwh"] = values["import_kwh"] - values["export_kwh"]
    values["missing_count"] = max(0, expected_count - values["archived_count"])
    values["expected_completed_count"] = expected_count
    values["exceeded_duration_minutes"] = values["exceeded_count"] * 15
    eligible = values["contractual_eligible_count"]
    values["confirmed_exceedance_pct"] = (
        100.0 * values["exceeded_count"] / eligible if eligible else None
    )
    values["coverage_pct"] = (
        100.0 * values["valid_count"] / expected_count if expected_count else None
    )
    return values


def period_report(
    archive: QuarterArchive,
    namespace: str,
    bounds: PeriodBounds,
    *,
    now_utc: datetime,
    tariff_block: int | None = None,
    classifier: Callable[[datetime], Any] | None = None,
    include_comparison: bool = True,
) -> dict[str, Any]:
    """Build one shared trustworthy report without loading the whole archive."""

    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise ValueError("now_utc must be timezone-aware")
    completed_cutoff = quarter_bounds(now_utc).start_utc
    completed_end = min(bounds.end_utc, completed_cutoff)
    if completed_end < bounds.start_utc:
        completed_end = bounds.start_utc
    resolution = chart_resolution(bounds)
    expected, expected_intervals = _expected_bins(
        bounds, completed_end, resolution, tariff_block, classifier
    )
    expected_count = sum(expected.values())
    aggregate = archive.aggregate_period(
        namespace, bounds.start_utc, completed_end, tariff_block=tariff_block
    )
    summary = _normalize_summary(aggregate, expected_count)
    raw_bins = archive.aggregate_period_bins(
        namespace,
        bounds.start_utc,
        completed_end,
        resolution=resolution,
        tariff_block=tariff_block,
    )
    stored = {_row_dict(row)["bin_key"]: _row_dict(row) for row in raw_bins}
    bins: list[dict[str, Any]] = []
    keys = sorted(
        set(expected) | set(stored),
        key=lambda item: stored.get(item, {}).get("start_utc", item),
    )
    for key in keys:
        item = stored.get(key, {"bin_key": key})
        expected_start, expected_end = expected_intervals.get(key, (None, None))
        archived_count = _integer(item.get("archived_count"))
        valid_count = _integer(item.get("valid_count"))
        expected_in_bin = expected.get(key, 0)
        targets = [float(value) for value in str(item.get("targets_kw") or "").split(",") if value]
        bins.append(
            {
                **item,
                "expected_start_utc": expected_start,
                "expected_end_utc": expected_end,
                "archived_count": archived_count,
                "valid_count": valid_count,
                "contractual_eligible_count": _integer(item.get("contractual_eligible_count")),
                "incomplete_count": _integer(item.get("incomplete_count")),
                "expected_count": expected_in_bin,
                "missing_count": max(0, expected_in_bin - archived_count),
                "coverage_pct": 100.0 * valid_count / expected_in_bin if expected_in_bin else None,
                "import_kwh": (_number(item.get("import_kwh")) if archived_count else None),
                "export_kwh": (_number(item.get("export_kwh")) if archived_count else None),
                "partial_observed_import_kwh": _number(item.get("partial_observed_import_kwh")),
                "partial_observed_export_kwh": _number(item.get("partial_observed_export_kwh")),
                "exceeded_count": _integer(item.get("exceeded_count")),
                "targets_kw": sorted(set(targets)),
                "status": (
                    "missing"
                    if archived_count == 0 and expected_in_bin
                    else "complete"
                    if expected_in_bin and valid_count == expected_in_bin
                    else "incomplete"
                ),
            }
        )
    partial = bounds.start_utc <= now_utc < bounds.end_utc or bounds.end_utc > completed_cutoff
    result: dict[str, Any] = {
        "period": {
            **asdict(bounds),
            "period_type": bounds.period_type.value,
            "partial": partial,
            "completed_end_utc": completed_end,
            "resolution": resolution,
            "tariff_block": tariff_block,
        },
        "summary": summary,
        "bins": bins,
        "status": "no_archive" if not summary["archived_count"] else "ok",
    }
    if include_comparison:
        prior = previous_period(bounds)
        current_quality = _comparison_quality(summary)
        if partial:
            result["comparison"] = {
                "available": False,
                "reason": "current_period_incomplete",
                "period": asdict(prior),
                "current_quality": current_quality,
                "previous_quality": None,
            }
        else:
            previous = period_report(
                archive,
                namespace,
                prior,
                now_utc=now_utc,
                tariff_block=tariff_block,
                classifier=classifier,
                include_comparison=False,
            )
            prior_summary = previous["summary"]
            previous_quality = _comparison_quality(prior_summary)
            if not current_quality["comparable"]:
                reason = "current_period_incomplete"
            elif not prior_summary["archived_count"]:
                reason = "no_previous_archive"
            elif not previous_quality["comparable"]:
                reason = "previous_period_incomplete"
            elif current_quality["expected_count"] != previous_quality["expected_count"]:
                reason = "period_length_mismatch"
            else:
                reason = None
            result["comparison"] = {
                "available": reason is None,
                "reason": reason,
                "period": previous["period"],
                "summary": prior_summary,
                "current_quality": current_quality,
                "previous_quality": previous_quality,
                "changes": {
                    key: (
                        summary[key] - prior_summary[key]
                        if reason is None
                        and summary[key] is not None
                        and prior_summary[key] is not None
                        else None
                    )
                    for key in (
                        "import_kwh",
                        "export_kwh",
                        "maximum_import_demand_kw",
                    )
                },
            }
    return result


def block_report(
    archive: QuarterArchive,
    namespace: str,
    bounds: PeriodBounds,
    *,
    now_utc: datetime,
    classifier: Callable[[datetime], Any],
    selected_block: int | None = None,
) -> dict[str, Any]:
    """Build a five-row block comparison from the shared validity rules."""

    if selected_block is not None and selected_block not in range(1, 6):
        raise ValueError("tariff block must be B1 through B5")
    completed_cutoff = quarter_bounds(now_utc).start_utc
    completed_end = max(bounds.start_utc, min(bounds.end_utc, completed_cutoff))
    expected_by_block: Counter[int] = Counter()
    cursor = bounds.start_utc
    while cursor < completed_end:
        block = getattr(classifier(cursor), "block", None)
        if block in range(1, 6):
            expected_by_block[int(block)] += 1
        cursor += timedelta(minutes=15)

    blocks: list[dict[str, Any]] = []
    for block in range(1, 6):
        raw = archive.aggregate_period(
            namespace, bounds.start_utc, completed_end, tariff_block=block
        )
        summary = _normalize_summary(raw, expected_by_block[block])
        raw_targets = str(raw["targets_kw"] or "")
        summary["targets_kw"] = sorted({float(value) for value in raw_targets.split(",") if value})
        peaks = archive.highest_demand_quarters(
            namespace,
            bounds.start_utc,
            completed_end,
            tariff_block=block,
            limit=10,
        )
        summary.update(
            {
                "block": block,
                "active": bool(expected_by_block[block] or summary["archived_count"]),
                "valid_measured_hours": summary["valid_count"] * 0.25,
                "peak_timestamp": peaks[0]["start_utc"] if peaks else None,
                "high_demand_quarters": [_row_dict(row) for row in peaks],
            }
        )
        blocks.append(summary)
    totals = _normalize_summary(
        archive.aggregate_period(namespace, bounds.start_utc, completed_end),
        sum(expected_by_block.values()),
    )
    return {
        "period": {
            **asdict(bounds),
            "period_type": bounds.period_type.value,
            "completed_end_utc": completed_end,
            "partial": bounds.start_utc <= now_utc < bounds.end_utc,
        },
        "selected_block": selected_block,
        "totals": totals,
        "blocks": blocks,
        "status": "ok" if any(item["archived_count"] for item in blocks) else "no_archive",
    }


def exceedance_report(
    archive: QuarterArchive,
    namespace: str,
    bounds: PeriodBounds,
    *,
    now_utc: datetime,
    tariff_block: int | None = None,
    sort_by: str = "date",
    direction: str = "desc",
    page: int = 1,
    page_size: int = 50,
    classifier: Callable[[datetime], Any] | None = None,
) -> dict[str, Any]:
    """Build one paginated contractual exceedance report."""

    if not 1 <= page <= 1_000_000:
        raise ValueError("page must be between 1 and 1000000")
    completed_cutoff = quarter_bounds(now_utc).start_utc
    completed_end = max(bounds.start_utc, min(bounds.end_utc, completed_cutoff))
    aggregate = archive.aggregate_period(
        namespace, bounds.start_utc, completed_end, tariff_block=tariff_block
    )
    expected, _expected_intervals = _expected_bins(
        bounds, completed_end, "quarter", tariff_block, classifier
    )
    period_summary = _normalize_summary(aggregate, sum(expected.values()))
    exceedance = archive.aggregate_exceedances(
        namespace, bounds.start_utc, completed_end, tariff_block=tariff_block
    )
    total, rows = archive.list_exceedances(
        namespace,
        bounds.start_utc,
        completed_end,
        tariff_block=tariff_block,
        sort_by=sort_by,
        direction=direction,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    if bounds.period_type in {PeriodType.HOUR, PeriodType.DAY}:
        resolution = "quarter"
    elif bounds.period_type in {PeriodType.WEEK, PeriodType.MONTH}:
        resolution = "day"
    elif bounds.period_type is PeriodType.YEAR:
        resolution = "month"
    else:
        resolution = chart_resolution(bounds)
    raw_bins = archive.aggregate_period_bins(
        namespace,
        bounds.start_utc,
        completed_end,
        resolution=resolution,
        tariff_block=tariff_block,
    )
    bins = [
        {
            **_row_dict(row),
            "exceeded_count": _integer(row["exceeded_count"]),
            "maximum_excess_kw": (
                None if row["maximum_excess_kw"] is None else float(row["maximum_excess_kw"])
            ),
        }
        for row in raw_bins
    ]
    count = int(exceedance["exceedance_count"] or 0)
    summary = {
        **exceedance,
        "exceedance_count": count,
        "exceeded_duration_minutes": count * 15,
        "confirmed_exceedance_rate_pct": period_summary["confirmed_exceedance_pct"],
        "contractual_eligible_count": period_summary["contractual_eligible_count"],
        "expected_completed_count": period_summary["expected_completed_count"],
        "incomplete_count": period_summary["incomplete_count"],
        "unknown_configuration_count": period_summary["unknown_configuration_count"],
        "valid_without_confirmed_target_count": period_summary[
            "valid_without_confirmed_target_count"
        ],
        "missing_count": period_summary["missing_count"],
        "simulation_count": period_summary["simulation_count"],
        # This is a distinct-quarter count. The diagnostic categories above may
        # overlap (for example one row can be incomplete and configuration-unknown),
        # so summing them would double-count. Simulations are not contractual
        # observations and therefore remain in the unconfirmed complement.
        "incomplete_or_unconfirmed_count": max(
            0,
            period_summary["expected_completed_count"]
            - period_summary["contractual_eligible_count"],
        ),
        "coverage_pct": period_summary["coverage_pct"],
    }
    return {
        "period": {
            **asdict(bounds),
            "period_type": bounds.period_type.value,
            "completed_end_utc": completed_end,
            "partial": bounds.start_utc <= now_utc < bounds.end_utc,
            "resolution": resolution,
        },
        "filter": {
            "tariff_block": tariff_block,
            "sort_by": sort_by,
            "direction": direction,
        },
        "summary": summary,
        "bins": bins,
        "items": [_row_dict(row) for row in rows],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size,
        },
        "status": "ok" if total else "empty",
    }
