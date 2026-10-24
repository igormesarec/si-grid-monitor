"""Versioned contracted-power periods independent of tariff rule versions."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import pairwise
from typing import Any

from .tariffs.models import TariffClassification


@dataclass(frozen=True, slots=True)
class ContractedPowerPeriod:
    """Five user-owned block targets valid for an inclusive local-date period."""

    effective_from: date
    effective_to: date
    block_targets_kw: tuple[float, float, float, float, float]
    provenance: str
    recorded_on: date | None = None

    def __post_init__(self) -> None:
        if self.effective_to < self.effective_from:
            raise ValueError("contracted-power period end precedes its start")
        if len(self.block_targets_kw) != 5:
            raise ValueError("exactly five contracted-power targets are required")
        if any(not math.isfinite(target) or target < 0 for target in self.block_targets_kw):
            raise ValueError("contracted-power targets must be finite and nonnegative")

    def target_for(self, tariff: TariffClassification) -> float | None:
        """Return the period target only when both date and block are known."""

        local_date = tariff.local_datetime.date()
        if (
            tariff.block is None
            or local_date < self.effective_from
            or local_date > self.effective_to
        ):
            return None
        return self.block_targets_kw[tariff.block - 1]


@dataclass(frozen=True, slots=True)
class ContractedPowerSchedule:
    """Non-overlapping contracted-power periods with auditable provenance."""

    periods: tuple[ContractedPowerPeriod, ...]

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.periods, key=lambda period: period.effective_from))
        for previous, current in pairwise(ordered):
            if current.effective_from <= previous.effective_to:
                raise ValueError("contracted-power periods must not overlap")
        object.__setattr__(self, "periods", ordered)

    def period_for(self, local_date: date) -> ContractedPowerPeriod | None:
        return next(
            (
                period
                for period in self.periods
                if period.effective_from <= local_date <= period.effective_to
            ),
            None,
        )

    def target_for(self, tariff: TariffClassification) -> float | None:
        period = self.period_for(tariff.local_datetime.date())
        return None if period is None else period.target_for(tariff)

    def gaps(self, start: date, end: date) -> tuple[tuple[date, date], ...]:
        """Return uncovered inclusive local-date ranges without inventing targets."""

        if end < start:
            raise ValueError("gap range end precedes its start")
        gaps: list[tuple[date, date]] = []
        cursor = start
        for period in self.periods:
            if period.effective_to < cursor:
                continue
            if period.effective_from > end:
                break
            if cursor < period.effective_from:
                gaps.append((cursor, min(end, period.effective_from - timedelta(days=1))))
            cursor = max(cursor, period.effective_to + timedelta(days=1))
            if cursor > end:
                break
        if cursor <= end:
            gaps.append((cursor, end))
        return tuple(gaps)

    def schedule_change(
        self,
        index: int,
        replacement: ContractedPowerPeriod,
    ) -> ContractedPowerSchedule:
        """Split one assignment around a replacement, committing one complete schedule.

        The replacement must be wholly contained in the selected assignment. This
        deliberately prevents a guided change from consuming another assignment.
        """

        try:
            existing = self.periods[index]
        except IndexError as err:
            raise ValueError("selected contracted-power assignment does not exist") from err
        if (
            replacement.effective_from < existing.effective_from
            or replacement.effective_to > existing.effective_to
        ):
            raise ValueError("scheduled change must stay within the selected assignment")
        periods = list(self.periods)
        segments: list[ContractedPowerPeriod] = []
        if existing.effective_from < replacement.effective_from:
            segments.append(
                ContractedPowerPeriod(
                    existing.effective_from,
                    replacement.effective_from - timedelta(days=1),
                    existing.block_targets_kw,
                    existing.provenance,
                    existing.recorded_on,
                )
            )
        segments.append(replacement)
        if replacement.effective_to < existing.effective_to:
            segments.append(
                ContractedPowerPeriod(
                    replacement.effective_to + timedelta(days=1),
                    existing.effective_to,
                    existing.block_targets_kw,
                    existing.provenance,
                    existing.recorded_on,
                )
            )
        periods[index : index + 1] = segments
        return ContractedPowerSchedule(tuple(periods))

    def conflict_for(
        self, candidate: ContractedPowerPeriod, *, exclude_index: int | None = None
    ) -> ContractedPowerPeriod | None:
        """Return the first inclusive-range conflict for a proposed assignment."""

        return next(
            (
                period
                for index, period in enumerate(self.periods)
                if index != exclude_index
                and candidate.effective_from <= period.effective_to
                and candidate.effective_to >= period.effective_from
            ),
            None,
        )

    def to_json(self) -> str:
        """Return the stable options/archive representation."""

        return json.dumps(
            [
                {
                    "effective_from": period.effective_from.isoformat(),
                    "effective_to": period.effective_to.isoformat(),
                    "block_targets_kw": list(period.block_targets_kw),
                    "provenance": period.provenance,
                    "recorded_on": (
                        period.recorded_on.isoformat() if period.recorded_on is not None else None
                    ),
                }
                for period in self.periods
            ],
            separators=(",", ":"),
            sort_keys=True,
        )


def contracted_power_schedule_from_json(value: object) -> ContractedPowerSchedule:
    """Parse and validate the user-visible multi-period JSON setting."""

    if value in (None, ""):
        return ContractedPowerSchedule(())
    try:
        raw: Any = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError as err:
        raise ValueError("contracted-power assignments must be valid JSON") from err
    if not isinstance(raw, list):
        raise ValueError("contracted-power assignments must be a JSON list")
    periods: list[ContractedPowerPeriod] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"contracted-power assignment {index} must be an object")
        try:
            targets = item["block_targets_kw"]
            if not isinstance(targets, list) or len(targets) != 5:
                raise ValueError("block_targets_kw must contain five values")
            recorded = item.get("recorded_on")
            periods.append(
                ContractedPowerPeriod(
                    effective_from=date.fromisoformat(str(item["effective_from"])),
                    effective_to=date.fromisoformat(str(item["effective_to"])),
                    block_targets_kw=tuple(float(target) for target in targets),
                    provenance=str(item.get("provenance") or "user_configured"),
                    recorded_on=(date.fromisoformat(str(recorded)) if recorded else None),
                )
            )
        except (KeyError, TypeError, ValueError) as err:
            raise ValueError(f"invalid contracted-power assignment {index}: {err}") from err
    return ContractedPowerSchedule(tuple(periods))
