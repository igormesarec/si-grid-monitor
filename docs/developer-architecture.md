# Developer architecture (V0.9.5)

The repository's source code and unit tests are the authoritative implementation reference. This document describes modules and invariants; it is not a commitment that every possible edge case has been validated on live hardware.

## Processing pipeline

~~~text
HA state changes / state reports  +  runtime clock
      |
      v
runtime.py → adapters.py / sources.py
(source mode, polarity, W/kW/Wh/kWh, timestamps)
      |
      v
engine.py / sustained.py
(fixed-quarter import and export energy, coverage,
 smoothing, projections and eligible forecast horizons)
      |
      +--> tariff rules + date-bound contracted assignments
      |
      +--> HA sensor entities (sensor.py)
      |
      +--> authenticated dashboard websocket
      |       dashboard.js / dashboard-model.mjs / i18n
      |
      +--> integration-owned SQLite schema-6 quarter archive
              checkpoints, source epochs, historical reports
~~~

## Component responsibilities

| Area | Responsibility |
|---|---|
| `config_flow.py` | Guided setup and Options, unit/source validation, dated limits, archive removal confirmation |
| `runtime.py` | HA lifecycle, source listeners, snapshot publication, archival tasks and recoverable shutdown |
| `adapters.py` | Pure sign/unit normalization for W/kW and source-mode semantics |
| `sources.py` | Cumulative-counter baselines, interval deltas, reset and export-evidence provenance |
| `engine.py` | Fixed quarters, time-weighted input, quality, checkpoints and import energy |
| `sustained.py` | Conservative forward evaluation of constant extra load over intersecting quarters |
| `sensor.py` | Home Assistant entity exposure and availability rules |
| `archive.py`, `history.py` | SQLite storage, migration, quality, provenance and paginated HISTORY |
| `frontend/dashboard.js`, `dashboard-model.mjs` | Seven-tab interface, charts, measured-vs-unknown semantics |

Inspect exact file names when extending functionality; this overview intentionally omits some helper modules.

## Core invariants

1. A normalized positive signed W/kW reading is **import**. Negative is export.
2. Confirmed 15-minute contractual demand is derived from **imported** energy, not import minus export.
3. Gaps, startup, restart and stale samples are not populated with invented zeros.
4. A bidirectional net-energy counter is not evidence of exact separate import/export when both directions occurred within an interval.
5. The archive preserves original source, quality, tariff and contracted-power provenance.
6. Different meter entries have separate IDs, settings, databases and historic queries.
7. Mode D interval-average-derived kW is *not* instantaneous power.
8. Simulated and provisional thresholds never create confirmed contractual exceedance statistics.

## Restart and checkpoints

Completed quarters are stored durably; the in-progress quarter can be restored from checkpoint if it matches the same source identity and quarter. Unknown downtime remains a gap. Legacy Mode A identity compatibility was specifically addressed in V0.9.5.

## Time and DST

Persist UTC quarter keys; use Europe/Ljubljana local calendar classification for tariff rules and display. Distinguish the repeated fall-back hour by UTC identity. Avoid making assumptions that all local days have 96 quarters.

## Source-specific constraints

- A/B/C sample state freshness is currently capped at 60 seconds.
- Counter interval deltas have different evidence semantics and independent source timestamps.
- Mode D derivative plausibility needs additional field hardening; do not relax contractual confirmation because a numeric value exists.

See [Testing](testing-and-validation.md), [Limitations](limitations-and-roadmap.md) and the unchanged root `SPECIFICATION.md` plus versioned addenda.