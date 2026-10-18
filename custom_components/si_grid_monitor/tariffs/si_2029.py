"""Unverified 2029 continuation; usable only with explicit provisional opt-in."""

from datetime import date

from ._schedules import SCHEDULE_2027
from .models import RuleStatus, TariffRule

RULE = TariffRule(
    year=2029,
    effective_from=date(2029, 1, 1),
    effective_to=date(2029, 12, 31),
    version="SI-PROVISIONAL-2027-CONTINUATION-2029",
    status=RuleStatus.PROVISIONAL,
    source_url="https://www.uro.si/prenova-omre%C5%BEnine/novi-%C4%8Dasovni-bloki",
    legal_source_url="https://pisrs.si/pregledPredpisa?id=AKT_1266",
    hourly_blocks=SCHEDULE_2027,
    based_on_version="SI-URO-2027",
)
