"""Unverified 2028 continuation; usable only with explicit provisional opt-in."""

from datetime import date

from ._schedules import SCHEDULE_2027
from .models import RuleStatus, TariffRule

RULE = TariffRule(
    year=2028,
    effective_from=date(2028, 1, 1),
    effective_to=date(2028, 12, 31),
    version="SI-PROVISIONAL-2027-CONTINUATION-2028",
    status=RuleStatus.PROVISIONAL,
    source_url="https://www.uro.si/prenova-omre%C5%BEnine/novi-%C4%8Dasovni-bloki",
    legal_source_url="https://pisrs.si/pregledPredpisa?id=AKT_1266",
    hourly_blocks=SCHEDULE_2027,
    based_on_version="SI-URO-2027",
)
