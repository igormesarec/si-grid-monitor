"""Shared tariff calendar models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class Season(StrEnum):
    HIGHER = "higher"
    LOWER = "lower"


class DayType(StrEnum):
    WORKING = "working"
    NONWORKING = "nonworking"


class RuleStatus(StrEnum):
    OFFICIAL = "official"
    PROVISIONAL = "provisional"
    UNVERIFIED = "unverified"
    OUT_OF_RANGE = "out_of_range"


ScheduleKey = tuple[Season, DayType]


@dataclass(frozen=True, slots=True)
class TariffRule:
    year: int
    effective_from: date
    effective_to: date
    version: str
    status: RuleStatus
    source_url: str
    legal_source_url: str
    hourly_blocks: dict[ScheduleKey, tuple[int, ...]]
    based_on_version: str | None = None


@dataclass(frozen=True, slots=True)
class TariffClassification:
    timestamp_utc: datetime
    local_datetime: datetime
    block: int | None
    season: Season
    day_type: DayType
    holiday_name: str | None
    calendar_year: int
    rule_version: str | None
    rule_status: RuleStatus
    source_url: str | None
    utc_offset_seconds: int
    fold: int

    @property
    def verified(self) -> bool:
        return self.rule_status == RuleStatus.OFFICIAL
