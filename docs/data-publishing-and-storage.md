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
  activation and clearing use a configurable zero hysteresis. A configurable
  threshold publishes every materially worse MUST REDUCE increase or CAN ADD
  decrease on the next evaluation. Safe improvements can be coalesced; there is
  no five-minute veto on worsening risk.
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
heartbeat.

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
| Spring DST (23 h) | 329.2 MB | 232.6 MB | 80.0 MB | **641.8 MB/year** |
| Normal (24 h) | 312.5 MB | 232.6 MB | 80.0 MB | **625.0 MB/year** |
| Autumn DST (25 h) | 337.3 MB | 234.1 MB | 80.0 MB | **651.4 MB/year** |

The SQLite part uses allocated pages in the synthetic databases: 864,256 bytes
and 4,363 rows, 856,064 bytes and 4,551 rows, and 962,560 bytes and 4,773 rows.
This is closer to Recorder than the earlier simplified table, but it remains a
test model rather than a physical Home Assistant Recorder measurement.

| Real entity | Uncontrolled ceiling per meter | Published per meter |
|---|---:|---:|
| Sustained CAN ADD | 87,600 | 108 |
| Sustained MUST REDUCE | 87,600 | 108 |
| Current interval import average | 87,600 | 96 |
| Current-quarter imported energy | 87,600 | 96 |

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
