"""Official Slovenian tariff rule for 2026."""

from datetime import date

from ._schedules import SCHEDULE_2026
from .models import RuleStatus, TariffRule

RULE = TariffRule(
    year=2026,
    effective_from=date(2026, 1, 1),
    effective_to=date(2026, 12, 31),
    version="SI-URO-2026",
    status=RuleStatus.OFFICIAL,
    source_url="https://www.uro.si/prenova-omre%C5%BEnine/%C4%8Dasovni-bloki/2026",
    legal_source_url="https://pisrs.si/pregledPredpisa?id=AKT_1266",
    hourly_blocks=SCHEDULE_2026,
)
