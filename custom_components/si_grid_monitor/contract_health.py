"""Pure contracted-power schedule health evaluation for local Slovenian dates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from .contracted_power import ContractedPowerPeriod, ContractedPowerSchedule


class ContractHealthLevel(StrEnum):
    OK = "ok"
    WARNING = "warning"
    URGENT = "urgent"
    ERROR = "error"


def contract_issue_id(entry_id: str) -> str:
    """Return the stable, per-config-entry Repairs identity."""

    return f"contract_assignment_{entry_id}"


@dataclass(frozen=True, slots=True)
class ContractHealth:
    level: ContractHealthLevel
    reason: str
    active: ContractedPowerPeriod | None
    successor: ContractedPowerPeriod | None
    days_remaining: int | None
    gap_start: date | None = None
    gap_end: date | None = None

    @property
    def needs_issue(self) -> bool:
        return self.level is not ContractHealthLevel.OK


def evaluate_contract_health(
    schedule: ContractedPowerSchedule,
    today: date,
) -> ContractHealth:
    """Evaluate availability/expiry without extending an assignment implicitly."""

    active = schedule.period_for(today)
    future = tuple(period for period in schedule.periods if period.effective_from > today)
    successor = future[0] if future else None
    if active is None:
        previous = tuple(period for period in schedule.periods if period.effective_to < today)
        gap_start = previous[-1].effective_to + timedelta(days=1) if previous else today
        gap_end = successor.effective_from - timedelta(days=1) if successor else None
        return ContractHealth(
            ContractHealthLevel.ERROR,
            "missing_current_assignment",
            None,
            successor,
            None,
            gap_start,
            gap_end,
        )

    days = (active.effective_to - today).days
    next_day = active.effective_to + timedelta(days=1)
    adjacent = successor is not None and successor.effective_from == next_day
    if adjacent:
        return ContractHealth(
            ContractHealthLevel.OK, "successor_configured", active, successor, days
        )
    if days <= 7:
        level = ContractHealthLevel.URGENT
    elif days <= 30:
        level = ContractHealthLevel.WARNING
    else:
        level = ContractHealthLevel.OK
    reason = "uncovered_expiry" if level is not ContractHealthLevel.OK else "active_assignment"
    gap_end = successor.effective_from - timedelta(days=1) if successor else None
    return ContractHealth(level, reason, active, successor, days, next_day, gap_end)
