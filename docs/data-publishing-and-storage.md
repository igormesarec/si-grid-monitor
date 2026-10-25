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

- **Critical:** immediate genuine state/availability transitions.
- **Actionable:** CAN ADD, MUST REDUCE and related values; immediate zero/action
  transitions, otherwise controlled by interval and deadband.
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

**Custom** exposes routine/actionable intervals, kW/kWh deadbands and selected
fast entity keys. The preview is an estimate, not a promise about the physical
size of an external database.

Important distinction: the dashboard and completed-quarter archive use precise
internal results. A third-party Home Assistant numeric-state automation sees the
last published entity value. SI Grid Monitor publishes its own critical status
transitions promptly, but cannot promise immediate evaluation of an arbitrary
third-party threshold unless its relevant value is configured for that cadence.

## Dashboard diagnostics

Overview includes **Data Publishing & Storage** for the selected meter or all
meters. It reports calculation cycles, HA publications, suppressions, critical
events, top entity keys, payload estimates and annual budget use for the last
hour/day/week. Counters are bounded in memory and reset when the runtime restarts;
they do not scan Recorder and do not create another high-frequency history.

The projected sizes distinguish Recorder-like, InfluxDB and internal archive
components. They are engineering estimates, not measured sizes of the user's
databases. Warnings at 80% and 100% refer to the 1,000,000,000-byte annual budget.

## Reproducible benchmark

`tests/test_publishing_storage_benchmark.py` runs 86,400 deterministic
one-second cycles for each of two meters with 48 registered entities per meter.
The workload includes varying import, zero and export periods, rapid changes,
stale/recovery and critical transitions. The resulting measured publication
pattern is replayed into a representative seven-day SQLite database containing
state, attribute, index and 1,344 quarter-archive records.

Measured development result:

| Component | Annualized two-meter estimate |
|---|---:|
| Recorder-like SQLite allocation | about 251.8 MB |
| Conservative InfluxDB write/series allowance | about 399.1 MB |
| Combined projection | **about 650.9 MB/year** |
| Acceptance budget | 1,000 MB/year |

The SQLite part uses actual allocated pages (4,829,184 bytes for the seven-day
fixture, 54,684 state rows). InfluxDB is conservatively estimated at 140 bytes
per emitted state event because a real InfluxDB server is not part of CI. A real
60-day Recorder plus unlimited-retention InfluxDB installation must still be
measured during Home Assistant acceptance. Database engines, indexes,
compression and unrelated integrations can change physical size.

## Normal installation and exclusions

Storage Optimized is designed to work without SI Grid Monitor-specific
`recorder.exclude`, `influxdb.exclude`, custom YAML throttling or credentials.
The integration never edits `configuration.yaml`, Recorder settings or InfluxDB
retention. If temporary exclusions were added to protect an older installation,
keep them until V1.0.3 has run long enough to verify event rate, then remove them
deliberately and monitor both databases. Old data is not removed automatically.

SI Grid Monitor remains monitoring/decision-support software, not a certified
meter or electrical protection device.
