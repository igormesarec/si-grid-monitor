"""Safety policy for user-initiated Recorder audit and reconstruction."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .archive import ArchiveRecord, archive_row_fingerprint

QUALITY_RANK = {
    "unavailable": 0,
    "incomplete": 1,
    "reconstructed": 2,
    "counter_derived": 3,
    "measured_aligned": 4,
}


@dataclass(frozen=True, slots=True)
class ReconstructionDecision:
    """One dry-run decision; candidates never mutate the archive implicitly."""

    start_utc: str
    action: str
    reason: str
    existing_quality: str | None
    proposed_quality: str
    existing_coverage_seconds: float | None
    proposed_coverage_seconds: float
    import_difference_kwh: float | None
    contractual_status: str
    expected_fingerprint: str


def plan_reconstruction(
    existing_rows: Iterable[Mapping[str, Any]], candidates: Iterable[ArchiveRecord]
) -> tuple[ReconstructionDecision, ...]:
    """Choose only absent rows or evidence-backed quality improvements."""

    existing = {str(row["start_utc"]): row for row in existing_rows}
    decisions: list[ReconstructionDecision] = []
    for candidate in candidates:
        identity = candidate.start_utc.isoformat()
        current = existing.get(identity)
        if current is None:
            action, reason = "insert", "missing archive quarter has detailed Recorder samples"
        else:
            old_rank = QUALITY_RANK.get(str(current["quality"]), -1)
            new_rank = QUALITY_RANK.get(candidate.quality, -1)
            old_coverage = float(current["coverage_seconds"])
            columns = current.keys()
            trustworthy_live = "provenance" in columns and str(current["provenance"]).startswith(
                "live"
            )
            if new_rank > old_rank or (
                new_rank == old_rank
                and candidate.quality in {"incomplete", "unavailable"}
                and candidate.coverage_seconds > old_coverage
                and not trustworthy_live
            ):
                action, reason = "improve", "Recorder evidence improves quality or coverage"
            else:
                action, reason = "skip", "existing archive evidence is equal or stronger"
        decisions.append(
            ReconstructionDecision(
                start_utc=identity,
                action=action,
                reason=reason,
                existing_quality=None if current is None else str(current["quality"]),
                proposed_quality=candidate.quality,
                existing_coverage_seconds=(
                    None if current is None else float(current["coverage_seconds"])
                ),
                proposed_coverage_seconds=candidate.coverage_seconds,
                import_difference_kwh=(
                    None if current is None else candidate.import_kwh - float(current["import_kwh"])
                ),
                contractual_status=candidate.contractual_status,
                expected_fingerprint=archive_row_fingerprint(current),
            )
        )
    return tuple(decisions)


def audit_summary(decisions: Iterable[ReconstructionDecision]) -> dict[str, int]:
    """Return explicit dry-run totals without overlapping categories."""

    materialized = tuple(decisions)
    return {
        "candidate_count": len(materialized),
        "insert_count": sum(item.action == "insert" for item in materialized),
        "improve_count": sum(item.action == "improve" for item in materialized),
        "skip_count": sum(item.action == "skip" for item in materialized),
        "contractually_confirmed_count": sum(
            item.action != "skip" and item.contractual_status == "confirmed"
            for item in materialized
        ),
        "contractually_unconfirmed_count": sum(
            item.action != "skip" and item.contractual_status != "confirmed"
            for item in materialized
        ),
    }
