# Data publishing and storage

SI Grid Monitor calculates internally once per second where required for energy
integration, smoothing and forecasts. A separate centralized controller decides
when each existing Home Assistant entity publishes a new state. This preserves
calculation accuracy and entity IDs without creating a routine one-second
Recorder or InfluxDB stream.

## Why this changed

Older releases notified entity listeners on every runtime refresh. Coverage,
gap, source-age and timing attributes could change even when the main state did
not, producing distinct state and attribute rows. The integration-owned SQLite
quarter archive remained small; Home Assistant state events were the growth
source.

V1.0.3 gives every sensor and binary sensor an explicit class:

- **Critical:** unsafe activation and availability deterioration are immediate.
  `projected_exceedance` requires 30 continuously safe seconds before its
  public false clear, preventing threshold chatter without changing the engine.
- **Actionable:** CAN ADD, MUST REDUCE and related values. CAN ADD/MUST REDUCE
  activation/headroom loss use a configurable zero hysteresis. A configurable
  threshold publishes every materially worse MUST REDUCE increase or CAN ADD
  decrease on the next evaluation. Safety-improving clears and headroom gains,
  including nonzero improvements such as MUST REDUCE `3.000 → 2.000 kW`,
  require 30 seconds of continuous evidence. A nonzero improvement then still
  follows the configured actionable cadence; this avoids turning slow recovery
  into a 30-second heartbeat. This asymmetric delay is
  conservative: it cannot authorize more load from a transient improvement,
  while there is no five-minute veto on worsening risk.
- **Current measurement:** signed/import/export source power. Storage Optimized
  uses the routine 900-second maximum interval; Automation Priority uses 60
  seconds. Loss of availability or natural staleness is always immediate;
  recovery requires 30 seconds of continuously fresh evidence. The dashboard continues
  to use the internal current value, not a Recorder-paced mirror.
- **Quarter accumulation:** current-quarter imported energy. It publishes a
  meaningful first-minute value, then stays within a 180-second public-age
  bound under Storage Optimized, and resets immediately at the canonical
  quarter boundary. Exact completed results remain in the schema-7 archive.
  This within-quarter value resets and therefore deliberately has no Home
  Assistant lifetime-total state class. It is not a utility meter or a source
  for long-term accumulated-energy statistics.
- **Monitoring:** analytical power, energy and forecast values at meaningful
  changes or coarser intervals.
- **Configuration:** tariff, contract and source values only when changed.
- **Diagnostic/countdown:** reduced-frequency publication; detailed live
  diagnostics belong in the authenticated dashboard API.

Stable attributes remain public. Fast-changing diagnostics are removed from
unrelated entities, moved to the dashboard, or explicitly marked unrecorded.
Suppressing the HA event itself protects both Recorder and InfluxDB; display
rounding or `_unrecorded_attributes` alone would not.

## Profiles

**Storage Optimized** is the default and the only profile covered by the 1 GB
two-meter engineering benchmark. Critical/availability transitions remain
immediate. Routine states are coalesced and stable configuration states have no
heartbeat. The 180-second exception applies only to current-quarter imported
energy; redundant derived mirrors retain the routine cadence to keep the
two-meter storage plan bounded.

**Automation Priority** shortens normal publication intervals. Use it only when
an external automation needs fresher numeric state events; it can exceed the
storage target.

**Custom** exposes routine/actionable intervals, kW/kWh deadbands, actionable
large-change/hysteresis thresholds and selected fast entity keys. The preview
is an estimate, not a promise about the physical size of an external database.

Important distinction: the dashboard and completed-quarter archive use precise
internal results. A third-party Home Assistant numeric-state automation sees the
last published entity value. SI Grid Monitor publishes its own critical status
transitions promptly, but cannot promise immediate evaluation of an arbitrary
third-party threshold unless its relevant value is configured for that cadence.
The current-quarter imported-energy entity is a bounded live view, not the
immutable completed-quarter record.

## Complete entity policy matrix

Every public entity is assigned explicitly and the mapping is checked by an
exhaustive regression test. “Immediate” below means the next controller
evaluation (normally the next one-second runtime tick), not a claim about Home
Assistant scheduler latency.

| Class | Entities | Storage Optimized behavior |
|---|---|---|
| Critical | `projected_exceedance`, `unrecoverable_interval`, `input_stale`, `sustained_forecast_quality`, `data_quality` | Danger/availability/quality transitions immediate; projected-exceedance safe clear after 30 continuously safe seconds |
| Actionable | `quarter_budget_remaining_kwh`, `allowed_import_until_end_kw`, `forecast_instant_kw`, `forecast_smoothed_kw`, `forecast_utilization_pct`, `forecast_instant_utilization_pct`, `current_utilization_pct`, `can_add_power`, `must_reduce_power`, `sustained_can_add_power`, `sustained_must_reduce_power` | Stale/unknown input makes these unavailable immediately; worsening advice is immediate when material; safety improvements need 30 seconds and remain cadence-coalesced; otherwise 900 seconds |
| Current measurement | `current_power`, `import_power`, `export_power` | Meaningful change at 900 seconds; availability immediate |
| Quarter accumulation | `quarter_import_kwh_so_far` | First-minute update, then at most 180 seconds old, immediate quarter reset |
| Monitoring | `net_power_15m_rolling`, `import_power_15m_rolling`, `smoothed_signed_power`, `smoothed_import_power`, `current_interval_import_average`, `current_interval_signed_average`, `quarter_export_kwh_so_far` | Meaningful change/attribute update at 900 seconds; observed values keep their quality rather than becoming fabricated zero during a gap |
| Configuration/event | `source_mode`, both last-completed demand values, `target_kw`, current/next tariff and season/day metadata, all B1–B5 targets, `operational_target_kw` | Change only; no heartbeat |
| Diagnostic/countdown | `time_to_next_tariff_block`, `interval_elapsed_seconds`, `interval_remaining_seconds` | At least 900 seconds under the default |

Automation Priority changes normal/current/quarter cadence to 60 seconds and
actionable cadence to 15 seconds. Custom uses the configured intervals and
optional fast-entity list. Critical transitions and availability are not
delayed by profile selection.

## Dashboard diagnostics

Overview includes **Data Publishing & Storage** with selected-meter detail and
a separate combined installation estimate for all configured meters. It reports
actual one-second timer ticks separately from publishing
evaluations (which also occur after source reports), HA publications,
suppressions, critical events, top entity keys, payload estimates and annual
budget use for the last hour/day/week. Counters are bounded in memory and reset
when the runtime restarts. Annual estimates remain unavailable during the first
hour, and the panel warns if its 50,000-event history truncated the selected
window. When the bounded event buffer truncates, annual values become unknown
instead of annualizing incomplete evidence. Diagnostics do not scan Recorder or
create HA diagnostic entities.

Diagnostics also expose processing-failure count, last successful publication
time, currently faulted entity keys and the effective interval for current, quarter, actionable and monitoring
classes. Reader, state serialization, policy, callback and diagnostic
bookkeeping work is isolated per entity. Repeated failures are logged at most
once per entity per five minutes. A failed authoritative entity reader triggers
a bounded attempt to publish that entity unavailable, while healthy entities
continue. Failed fallback writes retry no more often than every 30 seconds and
recovered entities require stable evidence without duplicating an already
emitted state. If Home Assistant's state-write path itself remains broken, the
integration cannot make any fallback state durable; logs and diagnostics expose
that residual failure for operator action.

The projected sizes distinguish Recorder-like, InfluxDB and internal archive
components. They are engineering estimates, not measured sizes of the user's
databases. Warnings at 80% and 100% refer to the 1,000,000,000-byte annual budget.

## Reproducible benchmark

`tests/test_publishing_real_entities.py` runs complete 82,800-, 86,400-, and
90,000-second Europe/Ljubljana days for two meters using the real `SENSORS`, `BINARY_SENSORS`,
native values, availability and extra-state attributes. It includes a burst of
two source reports per second, import, near-zero PV reversals, quarter/tariff
and contract boundaries, stale/recovery, and the UTC-offset/fold transition.
Every controller also receives the real one-second timer evaluation. Published
states are written to a Recorder-like SQLite schema with shared attributes,
standard HA attributes, metadata/timestamp/context fields and three indexes;
attributes declared unrecorded by the actual entities are excluded as intended.

Measured development results:

| Day | Recorder-like | Unverified Influx allowance | Archive allowance | Combined planning result |
|---|---:|---:|---:|---:|
| Spring DST (23 h) | 408.7 MB | 297.1 MB | 80.0 MB | **785.8 MB/year** |
| Normal (24 h) | 397.7 MB | 296.4 MB | 80.0 MB | **774.1 MB/year** |
| Autumn DST (25 h) | 411.9 MB | 297.3 MB | 80.0 MB | **789.2 MB/year** |

The SQLite part uses allocated pages in the synthetic databases: 1,073,152 bytes
and 5,572 rows, 1,089,536 bytes and 5,800 rows, and 1,175,552 bytes and 6,060 rows.
This is closer to Recorder than the earlier simplified table, but it remains a
test model rather than a physical Home Assistant Recorder measurement.

| Real entity | Uncontrolled ceiling per meter | Published per meter |
|---|---:|---:|
| Sustained CAN ADD | 87,600 | 108 |
| Sustained MUST REDUCE | 87,600 | 108 |
| Current interval import average | 87,600 | 96 |
| Current-quarter imported energy | 87,600 | 576 |

The focused 3,600-second, 1 Hz actionable stress test runs all four advice
entities on two meters while alternating between `0.000` and `0.051 kW`:

| Entity | Events per meter/hour | First adverse latency | Stable improvement latency |
|---|---:|---:|---:|
| MUST REDUCE | 2 (initial + hazard) | 1 second | 30 seconds |
| Sustained MUST REDUCE | 2 (initial + hazard) | 1 second | 30 seconds |
| CAN ADD | 1 (initial conservative zero) | next evaluation for headroom loss | 30 seconds |
| Sustained CAN ADD | 1 (initial conservative zero) | next evaluation for headroom loss | 30 seconds |

The event counts are actual callback counts from the deterministic test, not a
claim about physical database bytes. A separate regression proves a second
danger during a pending safe clear publishes immediately.

A separate 3,600-second two-meter availability-flap stress alternates the
source between valid and unavailable every second. CAN ADD and projected
exceedance each emit only the initial state plus the first fail-closed
unavailable transition per meter; input stale emits only its initial safe state
plus the first stale assertion. Recovery is not published until 30 uninterrupted
healthy seconds, so source loss remains prompt without recording each unsafe
one-second recovery flap.

The uncontrolled column is the evaluation ceiling, not a physical measurement
of an older release. The optimized column is asserted from emitted rows in the
Recorder-like SQLite benchmark. InfluxDB is **not physically
verified**: 140 bytes per emitted state event is only a planning allowance. A
real InfluxDB 1.x server is not part of CI, so the project does not claim that
physical Recorder plus InfluxDB allocation is proven below 1 GB/year.

## Non-destructive 24-hour physical measurement

On a backed-up test Home Assistant installation, note the exact start/end UTC
times and record the Recorder and InfluxDB sizes before and after 24 hours.
For Home Assistant OS, use the Terminal/SSH add-on and adjust paths to the
installation; these commands only read metadata:

```sh
date -u
du -b /config/home-assistant_v2.db /config/.storage/si_grid_monitor_*.db
sqlite3 -readonly /config/home-assistant_v2.db \
  "SELECT COUNT(*) FROM states WHERE last_updated_ts >= strftime('%s','now','-24 hours') AND metadata_id IN (SELECT metadata_id FROM states_meta WHERE entity_id LIKE '%si_grid_monitor%');"
```

For an isolated InfluxDB 1.x test instance, record the database directory size
with `du -b` and run the read-only query `SHOW SERIES CARDINALITY` through the
Influx CLI before and after the same window. Do not run `DROP`, retention-policy
changes, purge, `VACUUM`, or deletion commands. Report filesystem allocation,
series cardinality, SI Grid Monitor state-event counts, storage profile and any
other integrations writing to the same databases.

## Normal installation and exclusions

Storage Optimized is designed to work without SI Grid Monitor-specific
`recorder.exclude`, `influxdb.exclude`, custom YAML throttling or credentials.
The integration never edits `configuration.yaml`, Recorder settings or InfluxDB
retention. If temporary exclusions were added to protect an older installation,
keep them until V1.0.3 has run long enough to verify event rate, then remove them
deliberately and monitor both databases. Old data is not removed automatically.

SI Grid Monitor remains monitoring/decision-support software, not a certified
meter or electrical protection device.
