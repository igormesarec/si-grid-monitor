# Data quality — measured, estimated, incomplete and unknown

This is as important as the energy value. **A number on the screen is not by itself evidence of a confirmed contractual quarter.**

| Term | Meaning |
|---|---|
| Measured / aligned | Supported observations for the interval; source accuracy still depends on the hardware |
| Reconstructed | Integrated from supported timestamped power readings, not certified billing-meter exact |
| Counter-derived | Based on difference of cumulative energy totals across an observed time interval |
| Incomplete | Part of required quarter evidence missing, ambiguous, or deliberately contractually unconfirmed |
| Unavailable | The requisite source/target evidence cannot support a value |
| Missing | Expected **completed monitored** quarter has no archived row |
| Pre-monitoring | Interval before this meter's monitoring epoch; not a missing data failure |
| Confirmed exceedance | Complete eligible quarter, genuine dated official target and sufficient import evidence |
| Unconfirmed | Observation or contract rule cannot establish a legally definitive exceedance status |
| Unknown export | Not measured; do not show as measured 0.000 kWh |
| Inferred net export | Directional implication from net counter differences; not directly separate import/export totals |
| Mixed known/unknown export | Export was measured for some portions of a quarter but not all |
| Provisional | Derived from an opt-in unverified future tariff rule and excluded from confirmed statistics |
| Simulation | Based on hypothetical user threshold, not original contractual limits |

## Evidence versus gaps

A new meter added in the middle of a fixed quarter has no readings for the preceding minutes. HA restarts and >60-second power-source staleness can also leave gaps. The archive must not fill unknown portions with zero power merely to make the quarter look complete.

A **full 120-second smoothing window** is not the same as **complete quarter import-energy coverage**. Sustained advice requires both supported recent history and enough quarter evidence.

## Import-only meters

Mode C knows imported power but not exported power. That is enough to calculate import-only demand with suitable live input, not enough to claim exported energy was measured.

## Net cumulative counters

One signed net cumulative counter may conceal both import and export occurring between two samples. For example, 0.100 kWh import followed by 0.100 kWh export can produce a zero net change. Therefore net-derived contractual import-only demand is **not confirmed**, even if timestamps are valid.

## Reconstructed and historical values

The SQLite archive retains completed quarter summaries, stored rule and target provenance, source epochs, coverage, and quality. It does not preserve a certified second-by-second peak or let the UI reconstruct missing details.

On 2026-10-22, real testing of a new Mode D meter showed two incomplete quarters with partial positive-net observations. This is correct caution, not proof of no exceedance.

See [History and archive](history-and-archive.md) and [Forecasts](forecasts.md).