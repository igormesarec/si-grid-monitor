"""Official Slovenian work-free holidays for calendar years 2026-2030."""

from __future__ import annotations

from datetime import date

SOURCE_URL = (
    "https://podatki.gov.si/dataset/seznam-praznikov-in-dela-prostih-dni-v-republiki-sloveniji"
)

_FIXED = {
    (1, 1): "New Year",
    (1, 2): "New Year",
    (2, 8): "Prešeren Day",
    (4, 27): "Day of Uprising Against Occupation",
    (5, 1): "Labour Day",
    (5, 2): "Labour Day",
    (6, 25): "Statehood Day",
    (8, 15): "Assumption Day",
    (10, 31): "Reformation Day",
    (11, 1): "All Saints' Day",
    (12, 25): "Christmas Day",
    (12, 26): "Independence and Unity Day",
}

_MOVABLE = {
    2026: {(4, 5): "Easter Sunday", (4, 6): "Easter Monday", (5, 24): "Whit Sunday"},
    2027: {(3, 28): "Easter Sunday", (3, 29): "Easter Monday", (5, 16): "Whit Sunday"},
    2028: {(4, 16): "Easter Sunday", (4, 17): "Easter Monday", (6, 4): "Whit Sunday"},
    2029: {(4, 1): "Easter Sunday", (4, 2): "Easter Monday", (5, 20): "Whit Sunday"},
    2030: {(4, 21): "Easter Sunday", (4, 22): "Easter Monday", (6, 9): "Whit Sunday"},
}


def holiday_name(value: date) -> str | None:
    """Return the official work-free holiday name, including weekend holidays."""

    if not 2026 <= value.year <= 2030:
        return None
    return _MOVABLE[value.year].get((value.month, value.day)) or _FIXED.get(
        (value.month, value.day)
    )
