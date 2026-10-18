# SI Grid Monitor — V1.3 Addendum

Status: V0.3 implementation addendum to the frozen MASTER PRODUCT SPECIFICATION
V1.1 and V1.2 implementation addendum. `SPECIFICATION.md` remains unchanged.

## Authoritative calendar coverage

The calendar accepts canonical UTC instants and classifies them in
`Europe/Ljubljana`. It never constructs quarter identity from an ambiguous local
timestamp. Higher season is November through February; lower season is March
through October. Saturdays, Sundays and statutory Slovenian work-free holidays
are nonworking days. A holiday name is retained even when it falls on a weekend.

Rule `SI-URO-2026` covers 1 January through 31 December 2026 and transcribes the
official URO 2026 hourly table. Rule `SI-URO-2027` starts 1 January 2027. Its
hourly table is the amended chapter 3 of Appendix 2, whose transitional clause
explicitly starts application on that date.

As checked on 18 October 2026, URO lists only “2026 and earlier” and “2027”. No
official 2028, 2029 or 2030 schedule is claimed. Those year modules are marked
provisional continuations of `SI-URO-2027`; without explicit user opt-in they
return `unverified` with no block. Provisional results remain visibly labeled and
are never described as legally confirmed.

Official references:

- https://www.uro.si/prenova-omre%C5%BEnine/%C4%8Dasovni-bloki/2026
- https://www.uro.si/prenova-omre%C5%BEnine/%C4%8Dasovni-bloki/2027
- https://www.uro.si/prenova-omre%C5%BEnine/novi-%C4%8Dasovni-bloki
- https://pisrs.si/pregledPredpisa?sop=2025-01-2723
- https://pisrs.si/pregledPredpisa?id=AKT_1266
- https://podatki.gov.si/dataset/seznam-praznikov-in-dela-prostih-dni-v-republiki-sloveniji

## Contracted targets and calculations

V0.3 stores five contracted-power settings, B1 through B5. A V0.2 upgrade copies
the effective single target into all five fields. Shared mode writes one value to
all five; per-block mode preserves independent values. Safety margin remains a
separate operational adjustment.

The current fixed quarter uses its classified block target for import-only
budget, utilization, instant/smoothed forecast, CAN ADD, MUST REDUCE,
unrecoverable and projected-exceedance calculations. Sustained forecasts call
the calendar for every future fixed quarter independently; they do not reuse the
current block's target. Export never offsets imported energy.

Contracted-power assignments have their own inclusive local-date validity and
provenance, independent from tariff rule versions. The backend accepts
non-overlapping periods so a later year can use different B1–B5 values without
rewriting history. No assignment is inferred beyond its stated validity. The
documented user-supplied 2026 acceptance fixture (recorded 17 October 2025) is
not a product default and does not alter V0.2-to-V0.3 migration semantics.

## Immutable archive provenance

SQLite schema 4 adds tariff calendar year, season, day type, rule verification
status and source URL to each completed quarter. Existing block, rule version,
target and utilization fields remain. Configuration epochs now retain all five
targets. A completed record receives the target and rule effective for that
quarter and is never silently rewritten after settings or rules change.

V0.2 epochs migrate their known common target into all five target columns.
Existing quarters with no calendar metadata may be classified once under the
applicable versioned rule; stored measurements and original targets are not
changed. Unknown configuration, incomplete measurement, or unavailable tariff
rules cannot produce a confirmed exceedance.

Tariff availability is not a prerequisite for physical metering or durability.
Signed/import/export measurements, quarter accumulation, completed-quarter
archive writes and checkpoints continue when the current tariff target is
unavailable. Only contractual projections and advice are unavailable.

Each completed row records the provisional-calendar policy that applied.
Provisional exceedances remain queryable estimates with an explicit reason but
are excluded from confirmed exceedance counts. Calendar migration never erases
historical `exceeded` or `excess_kw`; separate verification metadata records
whether the original result can be treated as confirmed. The last completed
quarter display values are restored from SQLite after restart with quality and
provenance intact.

## Backend inspection API

The pure calendar service exposes current/upcoming quarters, the next transition,
and daily, weekly, monthly and yearly structured views for 2026–2030. DST days
contain 23 or 25 real hourly rows with UTC offset and fold preserved. This is a
backend foundation for later dashboard work; V0.3 does not implement the six-tab
frontend.
