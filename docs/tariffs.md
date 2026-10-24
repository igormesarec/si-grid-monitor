# Slovenian tariff calendar and contracted-power assignments

SI Grid Monitor classifies local fixed 15-minute intervals into **B1–B5** tariff blocks using bundled rule tables, seasons, workday/non-workday classification and Slovenian holidays.

## Two separate datasets

1. **Tariff schedule**: tells the software which block is active at a local time.
2. **Your contracted-power assignment**: tells it what kW import-demand limit applies to that block on an **inclusive date range**.

The tariff rule alone never supplies your household's individual B1–B5 contracted-power numbers. The same project can track multiple meters with different contracts.

## Season and rules

The bundled model considers a **higher season (November–February)** and **lower season (March–October)**, as well as weekdays, work-free days and Slovenian public holidays. The repository documents rule versions for **2026** and **2027** and a changed 2027 schedule effective 1 January 2027. Confirm up-to-date legal applicability with the official regulator rather than relying on the project to silently fetch rule changes.

For **2028–2030**, continuation of the 2027 pattern is explicitly **provisional** and opt-in. Without opting in, unverified future blocks/limits are not claimed as confirmed. Measurement and archive functions may continue even when contractual forecasts are unavailable.

## Daylight saving time

All archived quarters use unique UTC start timestamps but are displayed in **Europe/Ljubljana** civil time. A typical day has **96** quarters. Spring DST change yields **92**; autumn repeat yields **100**. Repeated local clock hours must remain distinct and not overwrite each other.

## Contract validity and provenance

A dated assignment contains the five kW limits, start/end dates, a provenance description, and optionally the date recorded/issued. Options can add/edit/remove nonoverlapping ranges. Historical quarters preserve their own applicable limit and tariff provenance; updating a limit today is not permission to rewrite historical evidence.

Example **fixture only**: B1 3.500, B2 3.900, B3 4.100, B4 4.200, B5 4.200 kW. These numbers are **not** a general rule or default. If your new test meter shows B4 = 2.600 kW while another on the same grid connection shows 4.200 kW, verify the selected contract assignment.

## Where to verify policy

- Slovenian Energy Agency / Agencija za energijo (official regulator): https://www.agen-rs.si/
- Electricity market and network charging rules: consult current official publications and your electricity distributor's actual contracted-power notice.

This manual describes bundled code behavior, **not a legal ruling**, and intentionally does not claim unverified tariff years as official.

See [Configuration](configuration.md) and [Calculations](calculations.md).
# Contract target interpretations

Tariff rules determine the active B1-B5 block; a dated contract assignment
supplies that block's kW target. These remain independent.

For historical dates the calendar exposes two values:

- **As recorded** uses only the exact target stored with an archived quarter.
  If that row stored a null target, it remains **unknown**; the current schedule
  or an epoch must not silently fill it.
- **Historical configuration inference**, when separately shown, comes from a
  configuration snapshot effective at that time. It is useful context but is
  not archived-quarter evidence and is never promoted to a confirmed target.
- **Current configuration** applies the schedule configured now.

A retroactive assignment is not proof of what the integration knew earlier.
Historical calendar cells therefore use the as-recorded value or show it as
unavailable; they do not substitute the current configured target. Unknown
contract targets remain unknown while block/rule classification remains visible.
Repeated Ljubljana 02:00 hours on the autumn DST transition retain distinct UTC
identities while sharing the same local-date assignment.
