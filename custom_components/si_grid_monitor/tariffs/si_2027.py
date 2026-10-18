"""Official Slovenian tariff rule effective 1 January 2027."""

from datetime import date

from ._schedules import SCHEDULE_2027
from .models import RuleStatus, TariffRule

RULE = TariffRule(
    year=2027,
    effective_from=date(2027, 1, 1),
    effective_to=date(2027, 12, 31),
    version="SI-URO-2027",
    status=RuleStatus.OFFICIAL,
    source_url="https://www.uro.si/prenova-omre%C5%BEnine/%C4%8Dasovni-bloki/2027",
    legal_source_url="https://pisrs.si/pregledPredpisa?sop=2025-01-2723",
    hourly_blocks=SCHEDULE_2027,
)
