# Choosing a V1.0 measurement source — Modes A, B and C

Start with what the **grid connection** actually reports. V1.0 accepts live
power in W or kW. Source modes describe evidence and direction; they are not
accuracy grades.

| Mode | Required HA sensors | Export evidence | Forecasting | Main caution |
|---|---|---|---|---|
| **A — signed power** | 1 × signed grid W/kW | Measured by sign | Supported with fresh complete data | Verify polarity |
| **B — separate power** | Nonnegative import W/kW + export W/kW | Measured separately | Supported when inputs are valid and aligned | Timestamps and simultaneous positives |
| **C — import-only power** | 1 × nonnegative import W/kW | **Unknown** | Supported conservatively | Unknown export is not measured zero |

Choose A when a suitable signed grid-power entity exists, B when the grid meter
provides separate live import/export entities, and C when only live import power
is available. Do not select house consumption, PV production or a cumulative
Wh/kWh total in place of grid power.

## Mode A — one signed live-power entity

Select a grid sensor reporting W or kW. Internally SI Grid Monitor normalizes
**positive = import** and **negative = export**. Configure whether the raw
source's positive value means import. Some SolarEdge installations use the
opposite sign, but this is not universal—verify your actual entity by observing
a known household load.

Mode A supports import/export charts, rolling signed power, fixed-quarter
import-only demand, current-quarter forecasts and sustained advice when the
measurement and contractual quality gates pass.

## Mode B — separate live import and export entities

Select two nonnegative W/kW sources representing the **same physical grid
connection**. The adapter preserves separate import and export evidence and
normalizes signed grid power as import minus export for flow displays.

The inputs have independent timestamps. Stale, unavailable, misaligned or
contradictory simultaneous positive readings are handled conservatively rather
than paired into false evidence. Export never subtracts from imported energy in
the contractual quarter calculation.

## Mode C — one import-only live-power entity

Select a nonnegative grid-import W/kW source. Export is **unknown**, not zero.
The system can still integrate import-only demand and calculate current-quarter
and sustained advice, but it never grants additional headroom based on an
unmeasured export surplus.

A new Mode C entry started mid-quarter may report incomplete current-quarter
energy. It can recover on the next fully observed quarter after sufficient fresh
smoothing coverage. A full 120-second smoothing window does not reconstruct
earlier missing quarter energy.

## Validation performed by setup

The wizard checks that selected entities exist, have supported W/kW units and
contain usable numeric states. Modes B/C reject negative source values. Mode B
also checks contradictory inputs. The preview shows normalized direction and
export capability; verify it against a known load before relying on results.

## Legacy Mode D upgrade behavior

Mode D cumulative-energy input was experimental in V0.9.5/V0.9.6. It is not a
selectable or active V1.0 mode. Existing entries are disabled before runtime
construction, their archives remain intact, and Home Assistant displays an
unsupported-mode notice. Explicit reconfiguration to A/B/C preserves the entry
and archive namespace while creating a new source epoch. A source already owned
by another entry is rejected rather than merged.

## Future functionality

Cumulative energy-counter support, including import-only counters,
bidirectional net-energy counters and separate import/export counters, is
reserved for future development. It requires additional research into
measurement intervals, quarter-boundary alignment, counter resets, quantization
and contractual demand accuracy. No implementation date is committed.

Historical counter-derived records remain visible with their original quality
and provenance. That preservation does not make cumulative counters an active
V1.0 configuration option.

Continue to [Configuration](configuration.md) and
[Getting started](getting-started.md).
