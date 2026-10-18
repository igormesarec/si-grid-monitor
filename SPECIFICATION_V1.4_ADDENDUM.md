# SI Grid Monitor - V1.4 Addendum

Status: V0.4 implementation addendum to the frozen MASTER PRODUCT SPECIFICATION
V1.1 and earlier implementation addenda. `SPECIFICATION.md` remains unchanged.

## Guided configuration

V0.4 replaces the interim JSON editor with a six-step Home Assistant config
flow: source design, signed meter and polarity, inclusive contract validity and
provenance, shared or individual B1-B5 values, calculation settings, and review.
Select-selector defaults use the same string type as submitted values, so the
120-second smoothing and 60-minute sustained horizon can be accepted without
reselection. Only signed live power is implemented; planned modes cannot be saved.

`ContractedPowerSchedule` remains the sole runtime authority. Options can add,
edit and remove non-overlapping dated assignments using native date and number
controls. JSON is only the internal stable representation. A V0.3 upgrade
preserves the schedule, entry identity, entity unique IDs, configuration epochs
and schema-5 archive without inventing dates.

## Automatic authenticated panel

After the first config entry loads, the integration registers one custom panel
at `/si-grid-monitor` through Home Assistant's supported `panel_custom` API.
Bundled assets use the asynchronous static-path API and versioned URL. No
Lovelace dashboard, YAML, card resource or manual JavaScript registration is
required. Registration is idempotent, multiple entries share an isolated entry
selector, and the panel is removed only when the last entry unloads. Unrelated
dashboards are never modified.

The panel uses the authenticated Home Assistant WebSocket connection. Bounded
commands provide live state/samples, one archived quarter, one local day's
92/96/100 quarters and aggregates, tariff hours, upcoming transitions and archive
status. SQLite work runs in the executor; no public consumption endpoint exists.

## Views and truthfulness

OVERVIEW separates current signed/import/export power, import-only contractual
demand, energy, forecasts, current-quarter advice and sustained advice. The
one-second countdown is browser-local. The measured trace preserves gaps and the
target is explicitly a 15-minute-average reference. Archived summaries state
when detailed traces are unavailable.

TODAY represents every real aligned quarter, labels missing records rather than
inventing zeroes, and shows all five tariff-block rows. TARIFF CALENDAR uses the
backend 2026-2030 rules and preserves UTC offset/fold; JavaScript does not
duplicate Slovenian tariff logic. Official, provisional, unverified and missing
target states remain distinct.

Upcoming planning returns three block changes and searches a bounded 31-day
horizon for the next official transition with a lower configured target. Block
numbers are never treated as target ordering. Existing per-quarter sustained
forecasting remains the source of load advice.

## Required real Home Assistant validation

Repository tests validate calculations, persistence, frontend syntax and
registration contracts. Final acceptance still requires a clean HACS install,
desktop/mobile and theme review, restart/reload/update exercises, and Recorder
history verification in real Home Assistant. SQLite schema 5 stores quarter
summaries; no historical intra-quarter curve is fabricated when samples are absent.
