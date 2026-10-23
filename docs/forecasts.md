# Forecasts and load advice

SI Grid Monitor offers **current-quarter** and, for suitable live-power sources, **sustained** billing-budget projections. The terms are meaningful only with adequate measurement coverage and confirmed contractual targets.

## Current-quarter fields

| Field | Meaning |
|---|---|
| Instant projected final average (kW) | Current-quarter demand forecast if the latest signed power persists to quarter end |
| Smoothed projected final average (kW) | Assumes recent, fully evidenced smoothed power persists |
| Remaining budget (kWh) | Operational target's allowed quarter energy minus imported energy observed so far |
| Allowed remainder (kW) | Average possible import during the remaining quarter from remaining budget |
| CAN ADD THIS QUARTER | Modelled extra constant load until this quarter ends |
| MUST REDUCE THIS QUARTER | Modelled continuing load reduction required until quarter end |

A current-quarter number is **not** automatically a supported long-horizon recommendation. A high allowed-remainder number near the end of a quarter can be mathematically valid while exceeding physical connection capacity.

## Sustained fields

The **15, 30, 60 or 120-minute horizon** checks every intersected fixed quarter; it is not simply the current 15-minute allowance multiplied by four. For Mode A/B/C it compares a repeated recent-power-path scenario against a constant-latest-power scenario and uses the restrictive output. Additional load during export is applied to signed power before nonnegative import is calculated.

## Quality gates and examples

- **Smoothing window incomplete:** fewer than the configured (default 120)
  seconds are valid in the recent window.
- **Source measurement stale:** the last supported live-source timestamp is
  older than the 60-second freshness threshold.
- **Current-quarter energy incomplete:** part of the quarter lacks valid
  imported-energy evidence; a complete recent smoothing window does not repair
  that earlier gap.
- **No valid measurement:** no usable latest live reading exists.
- **Reduction cannot recover the limiting quarter:** the quarter already
  contains too much imported energy to become compliant retrospectively.

**Real Mode C example:** after adding a new import-only meter shortly before 23:00, sustained CAN ADD was unavailable for the startup-affected quarter; after a new quarter began and coverage was sufficient, it returned automatically. This is intended coverage gating, not lack of Mode C capability.

## Supported sources

Forecasts use live-power Modes A/B/C only. Mode C remains conservative because
export is unknown. Legacy Mode D entries are disabled in V1.0 and do not expose
counter-derived instantaneous or sustained forecasts.

## What forecasts do not do

They do not predict when the heat pump starts, the next EV charging event, PV irradiance or grid-operator demand. They do not ensure phase balance, breaker ratings, cable current or safe simultaneous equipment use. For automated load control, employ separate physical protection and validated logic.

See [Calculations](calculations.md) and [Troubleshooting](troubleshooting.md).
