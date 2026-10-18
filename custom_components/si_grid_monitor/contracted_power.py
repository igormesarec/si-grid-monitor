"""Versioned contracted-power periods independent of tariff rule versions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from itertools import pairwise

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
