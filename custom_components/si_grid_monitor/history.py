"""Bounded, auditable HISTORY archive queries."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .archive import QuarterArchive, archive_row_validity

SUPPORTED_QUALITIES = frozenset(
    {"measured_aligned", "counter_derived", "reconstructed", "incomplete", "unavailable"}
)


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


def history_report(archive: QuarterArchive, namespace: str, query: HistoryQuery) -> dict[str, Any]:
    """Build a bounded page plus a range-wide, non-fabricated summary."""

    start = query.start_utc.astimezone(UTC)
    end = query.end_utc.astimezone(UTC)
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
        sort_by=query.sort_by,
        direction=query.direction,
    )
    facets = archive.history_facets(namespace, start, end)
    expected_count = max(0, math.ceil((end - start).total_seconds() / 900))
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
    missing_count = None if filters_active else max(0, expected_count - int(facets["total"]))
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
        "summary": {
            **facets,
            "scope": "selected_range_unfiltered",
            "matching_filtered_count": total,
            "filters_active": filters_active,
            "expected_count": expected_count,
            "missing_count": missing_count,
            "missing_count_reason": (
                None
                if missing_count is not None
                else "missing intervals cannot be classified by row-only filters"
            ),
        },
    }
