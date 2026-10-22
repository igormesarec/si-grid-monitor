"""Bounded, auditable HISTORY archive queries."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .archive import QuarterArchive, archive_row_validity
from .engine import quarter_bounds

SUPPORTED_QUALITIES = frozenset(
    {"measured_aligned", "counter_derived", "reconstructed", "incomplete", "unavailable"}
)


def _export_provenance(source_id: str, archive_provenance: str) -> str:
    """Classify archived export without changing schema-6 measurements."""

    provenance_parts = set(archive_provenance.split(":"))
    if "export_unknown" in provenance_parts:
        return "unknown"
    if "export_mixed" in provenance_parts:
        return "mixed_known_unknown"
    if "export_inferred_net" in provenance_parts:
        return "inferred_from_net"
    if "export_measured" in provenance_parts:
        return "directly_measured"
    if not source_id:
        return "unknown"
    if "counter_behavior=net" in source_id:
        return "inferred_from_net"
    if "mode=import_only" in source_id or "export_configured=False" in source_id:
        return "unknown"
    return "directly_measured"


def _provenance_seconds(archive_provenance: str, field: str) -> float | None:
    """Read optional export-evidence seconds from additive provenance text."""

    marker = f"{field}="
    for part in archive_provenance.split(":"):
        if part.startswith(marker):
            try:
                return float(part[len(marker) :])
            except ValueError:
                return None
    return None


@dataclass(frozen=True, slots=True)
class HistoryQuery:
    """Validated HISTORY query supplied by the authenticated dashboard."""

    start_utc: datetime
    end_utc: datetime
    tariff_block: int | None = None
    qualities: tuple[str, ...] = ()
    exceedance_status: str = "all"
    source_epoch: int | None = None
    page: int = 1
    page_size: int = 50
    sort_by: str = "start_utc"
    direction: str = "desc"

    def __post_init__(self) -> None:
        if self.start_utc.tzinfo is None or self.end_utc.tzinfo is None:
            raise ValueError("history timestamps must be timezone-aware")
        if self.end_utc <= self.start_utc:
            raise ValueError("history range must have a positive duration")
        if self.tariff_block is not None and self.tariff_block not in range(1, 6):
            raise ValueError("tariff block must be B1 through B5")
        if not set(self.qualities).issubset(SUPPORTED_QUALITIES):
            raise ValueError("unsupported quality filter")
        if self.exceedance_status not in {
            "all",
            "confirmed_yes",
            "confirmed_no",
            "unconfirmed",
        }:
            raise ValueError("unsupported exceedance-status filter")
        if self.page < 1 or not 1 <= self.page_size <= 200:
            raise ValueError("invalid history page")


def history_report(
    archive: QuarterArchive,
    namespace: str,
    query: HistoryQuery,
    *,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Build a bounded page plus a range-wide, non-fabricated summary."""

    start = query.start_utc.astimezone(UTC)
    end = query.end_utc.astimezone(UTC)
    now = datetime.now(UTC) if now_utc is None else now_utc
    if now.tzinfo is None:
        raise ValueError("history current timestamp must be timezone-aware")
    completed_end = min(end, max(start, quarter_bounds(now).start_utc))
    chronological_block_report = query.tariff_block is not None
    effective_sort = "start_utc" if chronological_block_report else query.sort_by
    effective_direction = "desc" if chronological_block_report else query.direction
    rows, total = archive.query_history(
        namespace,
        start,
        end,
        tariff_block=query.tariff_block,
        qualities=query.qualities,
        exceedance_status=query.exceedance_status,
        source_epoch=query.source_epoch,
        page=query.page,
        page_size=query.page_size,
        sort_by=effective_sort,
        direction=effective_direction,
    )
    facets = archive.history_facets(
        namespace,
        start,
        end,
        completed_before_utc=completed_end,
    )
    range_expected_count = max(0, math.ceil((end - start).total_seconds() / 900))
    completed_expected_count = max(0, math.ceil((completed_end - start).total_seconds() / 900))
    uncompleted_count = max(0, range_expected_count - completed_expected_count)
    monitoring_raw = facets.get("monitoring_started_utc")
    monitoring_start = (
        quarter_bounds(datetime.fromisoformat(str(monitoring_raw))).start_utc
        if monitoring_raw
        else start
    )
    monitored_start = min(completed_end, max(start, monitoring_start))
    pre_monitoring_count = max(0, math.ceil((monitored_start - start).total_seconds() / 900))
    monitored_completed_expected_count = max(
        0, math.ceil((completed_end - monitored_start).total_seconds() / 900)
    )
    monitored_facets = (
        facets
        if monitored_start == start
        else archive.history_facets(
            namespace,
            monitored_start,
            end,
            completed_before_utc=completed_end,
        )
    )
    # Missing is meaningful only for the unfiltered range. Filtered views cannot
    # infer what a missing row's block, quality, or epoch would have been.
    filters_active = any(
        (
            query.tariff_block is not None,
            bool(query.qualities),
            query.exceedance_status != "all",
            query.source_epoch is not None,
        )
    )
    missing_count = (
        None
        if filters_active
        else max(
            0,
            monitored_completed_expected_count - int(monitored_facets["completed_total"]),
        )
    )
    items = []
    for row in rows:
        item = {key: row[key] for key in row.keys()}  # noqa: SIM118 - sqlite Row values differ
        validity = archive_row_validity(item)
        stored_confirmed = item["confirmed_exceeded"]
        item["measured_valid"] = validity.measured_valid
        item["contractual_eligible"] = validity.contractual_eligible
        item["confirmed_exceeded"] = None if stored_confirmed is None else bool(stored_confirmed)
        item["validated_confirmed_exceeded"] = validity.confirmed_exceeded
        item["coverage_pct"] = max(0.0, min(100.0, 100.0 * float(item["coverage_seconds"]) / 900.0))
        item["detailed_trace_available"] = False
        item["measured_peak_kw"] = None
        item["measured_peak_evidence"] = "not_archived"
        source_id = str(item.get("source_id") or "")
        archive_provenance = str(item.get("provenance") or "")
        export_provenance = _export_provenance(
            source_id,
            archive_provenance,
        )
        item["export_provenance"] = export_provenance
        item["export_known"] = export_provenance not in {"unknown", "mixed_known_unknown"}
        item["export_coverage_seconds"] = _provenance_seconds(
            archive_provenance, "export_known_seconds"
        )
        item["export_unknown_seconds"] = _provenance_seconds(
            archive_provenance, "export_unknown_seconds"
        )
        items.append(item)
    return {
        "range": {"start_utc": start, "end_utc": end},
        "items": items,
        "pagination": {
            "page": query.page,
            "page_size": query.page_size,
            "total": total,
            "pages": math.ceil(total / query.page_size) if total else 0,
            "scope": "active_filters",
        },
        "ordering": {
            "sort_by": effective_sort,
            "direction": effective_direction,
            "locked_for_block_report": chronological_block_report,
        },
        "summary": {
            **facets,
            "scope": "selected_range_unfiltered",
            "matching_filtered_count": total,
            "filters_active": filters_active,
            # ``expected_count`` remains the complete selected calendar range for
            # API compatibility. Missing intervals use only quarters whose end
            # boundary has passed at ``now_utc``.
            "expected_count": range_expected_count,
            "completed_expected_count": completed_expected_count,
            "pre_monitoring_completed_count": pre_monitoring_count,
            "monitored_completed_expected_count": monitored_completed_expected_count,
            "completed_archived_count": int(facets["completed_total"]),
            "future_or_uncompleted_count": uncompleted_count,
            "missing_count": missing_count,
            "incomplete_measurement_count": int(
                facets["quality_distribution"].get("incomplete", 0)
            ),
            "unavailable_measurement_count": int(
                facets["quality_distribution"].get("unavailable", 0)
            ),
            "missing_count_reason": (
                None
                if missing_count is not None
                else "missing intervals cannot be classified by row-only filters"
            ),
        },
    }
