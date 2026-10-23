# How SI Grid Monitor calculates demand and headroom

This explains the proposed V1.0 release-candidate behavior, not an official bill
calculation. Input measurement cadence and validity determine accuracy.

## Fixed time boundaries

A quarter always begins at **:00, :15, :30 or :45**, Europe/Ljubljana local time (UTC timestamps remain the unique archive keys). It does **not** start when an integration entry is added or an appliance switches on.

## Imported energy, not net grid exchange

For each supported interval, imported power is the nonnegative import component. When a signed instantaneous meter reports normalized signed grid power P(t):

- Import power = max(0, P(t))
- Export power = max(0, −P(t))

Their energies are accumulated separately. Export in another minute **never** cancels import in the same quarter.

Example: 5 minutes importing 6.000 kW, 5 minutes exporting 8.000 kW and 5 minutes importing 6.000 kW yields:

- Import = 6 × 10/60 = **1.000 kWh**
- Export = 8 × 5/60 = **0.667 kWh**
- Fixed-quarter import-demand average = 1.000 / 0.25 = **4.000 kW**

Do not compute 1.000 minus 0.667 to obtain the contracted demand.

## Contractual limit as quarter energy budget

**Quarter budget (kWh) = contracted target (kW) × 0.25 h.**

For B4 = **2.600 kW**, the limit is **0.650 kWh** for a complete 15-minute quarter. For B4 = **4.200 kW**, the limit is **1.050 kWh**.

**Measured fixed-quarter demand = imported quarter energy / 0.25 h**, when 900 seconds of valid evidence and the applicable contractual assignment permit a confirmed result.

## Remaining budget and allowed remainder

Let E be recorded imported energy, T the operational kW target, and R the seconds to the quarter boundary:

- Remaining energy = max(0, T × 0.25 − E) kWh (a negative pre-clamped value indicates unrecoverable excess).
- Allowed average remaining import ≈ remaining energy × 3600 / R kW for R > 0.

Example: B4 limit 2.600 kW, 0.100 kWh imported, 5 minutes remaining:
0.650 − 0.100 = 0.550 kWh remaining; 0.550 / (5/60) = **6.600 kW** mathematical remainder.

**6.600 kW is not an electrical safety clearance.** This number can become large late in a quarter and assumes earlier import measurements are trustworthy.

## Current-quarter forecasts

An **instantaneous** continuation uses the latest supported signed grid power. A **smoothed** continuation uses recent power with sufficient valid sample coverage. The model estimates final quarter import by appending future nonnegative import consumption; export cannot subtract previous import.

For a constant hypothetical load x, the model evaluates import after adding x to signed grid power and clamping at zero. Current-quarter CAN ADD finds the modelled additional load that fits within budget; MUST REDUCE estimates the necessary reduction to the end of the quarter. An already irrecoverable quarter cannot be made historically compliant by switching something off now.

Availability requires source and contract quality: incomplete input can suppress sustained advice even if a current-quarter numerical estimate exists.

## Sustained forecast

The chosen 15/30/60/120-minute horizon intersects **multiple** fixed quarters. The implementation tests two scenarios: (1) repeating the recent measured signed-power path and (2) holding the latest signed value. The more conservative CAN ADD / MUST REDUCE result is presented, applying each future quarter's independently classified block target.

It is a repeat/persistence estimate, **not** a weather, PV-production, tariff-price, EV charging or heat-pump-cycle prediction.

## Sampling, staleness and gaps

Live power is integrated piecewise-constant while fresh, **up to 60 seconds**
from its timestamp. Beyond this the remainder becomes a gap, rather than an
invented zero or indefinite power hold. The usual smoothing window is 120
seconds and must have full valid coverage for a supported smoothed prediction.

A new setup or restart mid-quarter can make that quarter incomplete. A fully observed later quarter can restore sustained forecasting in A/B/C. The archive records incomplete and missing separately.

## Historical counter-derived records

V0.9.5/V0.9.6 experimented with counter-delta averages. V1.0 does not accept
cumulative-energy counters as active sources. Existing rows keep their
`counter_derived` or incomplete quality and must not be silently converted to
confirmed live-power measurements. This historical provenance is separate from
the A/B/C calculation path described above.

## Precision

Use internal numeric values for calculations; a display rounded to `0.000 kWh`
is not evidence of physically zero energy. V1.0 presents kW/kWh with three
decimals while calculations and archive storage retain full precision.

Continue to [Forecasts](forecasts.md), [Data quality](data-quality.md), [Tariffs](tariffs.md).
