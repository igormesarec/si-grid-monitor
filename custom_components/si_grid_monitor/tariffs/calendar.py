"""DST-safe Slovenian tariff classification and inspection API."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .holidays import holiday_name
from .models import DayType, RuleStatus, Season, TariffClassification, TariffRule
from .si_2026 import RULE as RULE_2026
from .si_2027 import RULE as RULE_2027
from .si_2028 import RULE as RULE_2028
from .si_2029 import RULE as RULE_2029
from .si_2030 import RULE as RULE_2030

LJUBLJANA = ZoneInfo("Europe/Ljubljana")
RULES: dict[int, TariffRule] = {
    rule.year: rule for rule in (RULE_2026, RULE_2027, RULE_2028, RULE_2029, RULE_2030)
}


class SlovenianTariffCalendar:
    """Classify canonical UTC instants without ambiguous local-time construction."""

    def __init__(self, *, allow_provisional: bool = False) -> None:
        self.allow_provisional = allow_provisional

    def classify(self, timestamp: datetime) -> TariffClassification:
        """Classify using the configured official/provisional policy."""

        return self._classify(timestamp, apply_policy=True)

    def classify_rule(self, timestamp: datetime) -> TariffClassification:
        """Return intrinsic rule metadata without applying a current user policy.

        This is used only to annotate legacy rows that never recorded a policy.
        The result must not be treated as proof that provisional use was enabled.
        """

        return self._classify(timestamp, apply_policy=False)

    def _classify(self, timestamp: datetime, *, apply_policy: bool) -> TariffClassification:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("tariff timestamps must be timezone-aware")
        utc = timestamp.astimezone(UTC)
        local = utc.astimezone(LJUBLJANA)
        season = Season.HIGHER if local.month in {11, 12, 1, 2} else Season.LOWER
        holiday = holiday_name(local.date())
        day_type = DayType.NONWORKING if local.weekday() >= 5 or holiday else DayType.WORKING
        rule = RULES.get(local.year)
        status = RuleStatus.OUT_OF_RANGE
        block: int | None = None
        version: str | None = None
        source: str | None = None
        if rule is not None:
            version = rule.version
            source = rule.source_url
            if (
                apply_policy
                and rule.status == RuleStatus.PROVISIONAL
                and not self.allow_provisional
            ):
                status = RuleStatus.UNVERIFIED
            else:
                status = rule.status
                block = rule.hourly_blocks[(season, day_type)][local.hour]
        return TariffClassification(
            timestamp_utc=utc,
            local_datetime=local,
            block=block,
            season=season,
            day_type=day_type,
            holiday_name=holiday,
            calendar_year=local.year,
            rule_version=version,
            rule_status=status,
            source_url=source,
            utc_offset_seconds=int(local.utcoffset().total_seconds()),
            fold=local.fold,
        )

    def next_transition(self, timestamp: datetime) -> TariffClassification | None:
        """Return the first later quarter whose block or rule status changes."""

        current = self.classify(timestamp)
        cursor = _next_quarter(timestamp.astimezone(UTC))
        for _ in range(8 * 24 * 4):
            candidate = self.classify(cursor)
            if (candidate.block, candidate.rule_status) != (
                current.block,
                current.rule_status,
            ):
                return candidate
            cursor += timedelta(minutes=15)
        return None

    def upcoming_quarters(
        self, timestamp: datetime, *, count: int = 8
    ) -> tuple[TariffClassification, ...]:
        start = _quarter_start(timestamp.astimezone(UTC))
        return tuple(self.classify(start + timedelta(minutes=15 * i)) for i in range(count))

    def daily_view(self, value: date) -> tuple[dict[str, object], ...]:
        """Return every real local hour; DST days therefore contain 23 or 25 rows."""

        start = datetime.combine(value, time.min, LJUBLJANA).astimezone(UTC)
        end = datetime.combine(value + timedelta(days=1), time.min, LJUBLJANA).astimezone(UTC)
        rows: list[dict[str, object]] = []
        cursor = start
        while cursor < end:
            item = self.classify(cursor)
            rows.append(_as_dict(item))
            cursor += timedelta(hours=1)
        return tuple(rows)

    def weekly_view(self, start_date: date) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "date": start_date + timedelta(days=offset),
                "hours": self.daily_view(start_date + timedelta(days=offset)),
            }
            for offset in range(7)
        )

    def monthly_view(self, year: int, month: int) -> tuple[dict[str, object], ...]:
        cursor = date(year, month, 1)
        rows: list[dict[str, object]] = []
        while cursor.month == month:
            hours = self.daily_view(cursor)
            rows.append({"date": cursor, "blocks": tuple(row["block"] for row in hours)})
            cursor += timedelta(days=1)
        return tuple(rows)

    def yearly_view(self, year: int) -> tuple[dict[str, object], ...]:
        return tuple(
            {"month": month, "days": self.monthly_view(year, month)} for month in range(1, 13)
        )

    def rule_status_report(self, today: date) -> dict[str, object]:
        """Describe installed rule metadata without activating remote content."""

        official = [rule for rule in RULES.values() if rule.status == RuleStatus.OFFICIAL]
        coverage_end = max((rule.effective_to for rule in official), default=None)
        current = RULES.get(today.year)
        if current is None:
            state = RuleStatus.OUT_OF_RANGE.value
        elif current.status == RuleStatus.PROVISIONAL and not self.allow_provisional:
            state = RuleStatus.UNVERIFIED.value
        else:
            state = current.status.value
        days_until_expiry = None if coverage_end is None else (coverage_end - today).days
        return {
            "current_year": today.year,
            "current_rule_version": None if current is None else current.version,
            "current_status": state,
            "official_coverage_end": coverage_end,
            "days_until_official_expiry": days_until_expiry,
            "update_recommended": coverage_end is None or days_until_expiry <= 90,
            "offline": True,
            "remote_rules_activated": False,
            "years": [
                {
                    "year": rule.year,
                    "version": rule.version,
                    "status": rule.status.value,
                    "effective_from": rule.effective_from,
                    "effective_to": rule.effective_to,
                    "source_url": rule.source_url,
                    "legal_source_url": rule.legal_source_url,
                    "based_on_version": rule.based_on_version,
                    "enabled": (
                        rule.status == RuleStatus.OFFICIAL
                        or (rule.status == RuleStatus.PROVISIONAL and self.allow_provisional)
                    ),
                }
                for rule in sorted(RULES.values(), key=lambda item: item.year)
            ],
        }


def _as_dict(value: TariffClassification) -> dict[str, object]:
    return {
        "start_utc": value.timestamp_utc,
        "local_datetime": value.local_datetime,
        "block": value.block,
        "season": value.season.value,
        "day_type": value.day_type.value,
        "holiday_name": value.holiday_name,
        "rule_version": value.rule_version,
        "rule_status": value.rule_status.value,
        "source_url": value.source_url,
        "utc_offset_seconds": value.utc_offset_seconds,
        "fold": value.fold,
    }


def _quarter_start(value: datetime) -> datetime:
    return value.replace(minute=(value.minute // 15) * 15, second=0, microsecond=0)


def _next_quarter(value: datetime) -> datetime:
    return _quarter_start(value) + timedelta(minutes=15)
