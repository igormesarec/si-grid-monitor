# Choosing a measurement source — Modes A, B, C and D

Start with what your **grid connection** can actually report. Modes are configuration choices, not accuracy grades.

| Mode | Required HA sensors | Can know export? | Real-time forecasting? | Main caution |
|---|---|---|---|---|
| **A — signed power** | 1 × W/kW signed grid power | Yes, sign indicates direction | Yes, with complete fresh data | Verify sign convention |
| **B — separate power** | Import W/kW + export W/kW | Yes | Yes, with synchronized valid inputs | Different timestamps and simultaneous positives |
| **C — import-only power** | 1 × nonnegative import W/kW | **No** | Yes, with fresh complete readings | Never treat unknown export as measured zero |
| **D — cumulative energy** | 1 or 2 × Wh/kWh counters | Depends on counter behavior | **Not instantaneous; sustained advice unsupported** | Differences describe past intervals, not current power |

**Recommended:** A when you have suitable signed grid power; B when real import/export power entities are available; C when only live import power exists; D when you have only cumulative energy totals.

## Mode A — one signed live power entity

Select the grid-signed sensor, unit W or kW. The SI Grid engine normalizes **positive import**, **negative export**. For SolarEdge installations that encode positive export and negative import, disable **Positive source values mean IMPORT**. This is an example, not a universal SolarEdge guarantee; verify your own sensor by switching on a known load.

A supports live charts, rolling 15-minute and smoothed estimates, current-quarter advice and sustained forecasts when all data and contractual targets are valid.

## Mode B — separate live import and export sensors

Both sources must be nonnegative W/kW readings of **the same grid connection**. The converter rejects conflicting positive simultaneous import and export and checks that source timestamps are reasonably aligned. Export at a different time never subtracts from import-only quarter energy. A stale or unavailable source prevents confident combined evidence.

## Mode C — one import-only power entity

Select a nonnegative grid-import sensor W/kW. Export is **unknown**, which is not the same as zero. The system can still integrate measured import and calculate supported **current-quarter and sustained CAN ADD/MUST REDUCE**, provided the meter remains fresh and the current quarter has complete coverage.

A freshly configured Mode C entry may show `current_quarter_energy_incomplete` for the remainder of a quarter that started before monitoring. It can recover automatically on the next fully covered quarter; 120 seconds of smoothing coverage alone do not replace a whole quarter of import-energy evidence. A real HA test has verified this recovery; not all hardware cadences have been tested.

## Mode D — energy counters

Mode D automatically calculates an **interval-average** power from cumulative-energy changes. Home Assistant Template or Derivative helpers are **not required**.

### D1. Import-only cumulative counter

One Wh/kWh entity with state class `total` or `total_increasing`. The number increases with imported grid energy and does not decrease when exporting. Export remains **unknown**.

### D2. Bidirectional cumulative *net* counter

One Wh/kWh entity whose value can **increase and decrease**. Choose whether increasing means **IMPORT** (default) or **EXPORT**. A negative delta is normally valid reverse flow, not automatically a counter reset.

**Fundamental limit:** Import and export can cancel between counter updates. An interval with zero net-energy change may contain nonzero import *and* export. Thus the app cannot confirm exact **import-only contractual demand** from net deltas alone. No configuration setting can recover that missing physical information.

### D3. Separate cumulative import and export counters

Use two distinct energy totals (optional export: import-only when absent). Independent updates are paired only where both channels provide evidence. Lost, misaligned or reset updates can lead to incomplete or unknown export intervals without necessarily invalidating properly evidenced import.

### Conversion and example

```text
Average power (kW) = energy change (kWh) / elapsed time (hours)
If the import counter changes by 0.050 kWh in 60 seconds:
0.050 / (60 / 3600) = 3.000 kW average over those 60 seconds.
```

That **does not** establish the power at the last second. The first reading only creates a baseline. The integration preserves counter direction and timestamps, deals conservatively with duplicates and explicit resets, and does not promote unsupported cross-quarter allocation into confirmed measurements.

**Known V0.9.5 field observation:** An implausible ~402 kW counter-derived spike appeared briefly on a new Mode D dashboard. Extremely short deltas and reporting resolution require investigation. Do not rely on an implausible derived value for a billing or safety decision. See [Troubleshooting](troubleshooting.md).

## How to verify a selected entity

Open Developer Tools → States and inspect ID, unit, current value, `state_class` and update cadence. Live W/kW is *power*; cumulative Wh/kWh is *energy*. Do not select house consumption or PV yield in place of grid import. For every mode, compare a measured 15-minute interval with trusted meter data when practical.

Continue to [Configuration](configuration.md).
