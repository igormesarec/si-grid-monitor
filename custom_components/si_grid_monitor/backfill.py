"""Recorder-history reconstruction helpers.

The Home Assistant runtime supplies detailed timestamped states. This module is
pure Python so live and backfill paths share the same quarter integration rules.
It never reconstructs quarters from hourly long-term statistics.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from .engine import CompletedQuarter, FixedQuarterEngine, PowerSample


def reconstruct_quarters(
    samples: Iterable[PowerSample],
    *,
    end_utc: datetime,
    source_id: str,
    stale_after_seconds: float,
) -> tuple[CompletedQuarter, ...]:
    """Reconstruct aligned quarters from detailed ordered samples.

    Gaps beyond ``stale_after_seconds`` remain missing and make a quarter
    incomplete. Import and export are integrated separately by the live engine.
    Re-running this function is safe when records are stored with archive
    idempotence.
    """

    engine = FixedQuarterEngine(stale_after_seconds=stale_after_seconds, source_id=source_id)
    for sample in sorted(samples, key=lambda item: item.timestamp_utc):
        engine.ingest(sample)
    if engine.last_sample is not None:
        engine.advance(end_utc)
    return tuple(engine.completed)
