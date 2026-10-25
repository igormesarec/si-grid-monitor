# Developer architecture (V1.0 release candidate)

The repository's source code and unit tests are the authoritative implementation reference. This document describes modules and invariants; it is not a commitment that every possible edge case has been validated on live hardware.

## Processing pipeline

~~~text
HA state changes / state reports  +  runtime clock
      |
      v
runtime.py → adapters.py
(A/B/C source mode, polarity, W/kW, timestamps)
      |
      v
engine.py / sustained.py
(fixed-quarter import and export energy, coverage,
 smoothing, projections and eligible forecast horizons)
      |
      +--> tariff rules + date-bound contracted assignments
      |
      +--> HA sensor entities (sensor.py)
      |       publishing.py (per-entity policy, change detection,
      |       deadbands and bounded diagnostics)
      |
      +--> authenticated dashboard websocket
      |       dashboard.js / dashboard-model.mjs / i18n
      |
      +--> integration-owned SQLite schema-7 archive (schema-6 quarter data preserved)
              checkpoints, source epochs, historical reports
~~~

## Component responsibilities

| Area | Responsibility |
|---|---|
| `config_flow.py` | Guided A/B/C setup and reconfiguration, duplicate-source validation, dated limits, archive removal confirmation |
| `runtime.py` | HA lifecycle, source listeners, snapshot publication, archival tasks and recoverable shutdown |
| `adapters.py` | Pure sign/unit normalization for W/kW and source-mode semantics |
| `engine.py` | Fixed quarters, time-weighted input, quality, checkpoints and import energy |
| `sustained.py` | Conservative forward evaluation of constant extra load over intersecting quarters |
| `sensor.py` | Home Assistant entity exposure and availability rules |
| `publishing.py` | Separates one-second calculation from HA publication, owns explicit entity policies and bounded event diagnostics |
| `archive.py`, `history.py` | SQLite storage, migration, quality, provenance and paginated HISTORY |
| `frontend/dashboard.js`, `dashboard-model.mjs` | Eight-tab interface, charts, measured-vs-unknown semantics and bilingual reporting |

Inspect exact file names when extending functionality; this overview intentionally omits some helper modules.

## Core invariants

1. A normalized positive signed W/kW reading is **import**. Negative is export.
2. Confirmed 15-minute contractual demand is derived from **imported** energy, not import minus export.
3. Gaps, startup, restart and stale samples are not populated with invented zeros.
4. The archive preserves original source, quality, tariff and contracted-power provenance.
5. Different meter entries have separate IDs, settings, databases and historic queries.
6. A canonical live source cannot be claimed by two entries during setup or reconfiguration.
7. Legacy counter-derived rows are preserved but never promoted to active V1.0 evidence.
8. Simulated and provisional thresholds never create confirmed contractual exceedance statistics.
9. Publishing policy can reduce HA state-event frequency but cannot change the
   engine snapshot, quarter archive, tariff result or contract audit.

## Publication boundary

`runtime.py` still calculates once per second. After each calculation the one
central controller reads registered entity states. Availability and genuine
critical value transitions publish immediately; configuration states publish
only on change; analytical/actionable states use their configured interval and
deadband. Stable attributes cannot create heartbeat events. Entity platforms
register callbacks with this controller and release them on unload; there is no
timer per entity.

Frequently changing coverage, gap, source-age and forecast-timing diagnostics
are kept out of unrelated public attribute payloads or marked with Home
Assistant's `_unrecorded_attributes`. Event suppression remains the primary
protection because InfluxDB also consumes HA state changes.

## Restart and checkpoints

Completed quarters are stored durably; the in-progress quarter can be restored
from checkpoint if it matches the same source identity and quarter. Unknown
downtime remains a gap. Mode A identity compatibility is preserved. A legacy
Mode D → A/B/C migration keeps the archive namespace but begins a distinct
source epoch.

## Time and DST

Persist UTC quarter keys; use Europe/Ljubljana local calendar classification for tariff rules and display. Distinguish the repeated fall-back hour by UTC identity. Avoid making assumptions that all local days have 96 quarters.

## Source-specific constraints

- A/B/C sample state freshness is currently capped at 60 seconds.
- Mode B input channels retain independent timestamps and are combined only
  when their evidence is valid.
- Mode C export capability is unknown by design.
- Counter conversion code is not an active V1.0 pipeline; only minimal legacy
  recognition/provenance compatibility remains.

See [Testing](testing-and-validation.md), [Limitations](limitations-and-roadmap.md) and the unchanged root `SPECIFICATION.md` plus versioned addenda.
