# Data quality — measured, estimated, incomplete and unknown

This is as important as the energy value. **A number on the screen is not by itself evidence of a confirmed contractual quarter.**

| Term | Meaning |
|---|---|
| Measured / aligned | Supported observations for the interval; source accuracy still depends on the hardware |
| Reconstructed | Integrated from supported timestamped power readings, not certified billing-meter exact |
| Counter-derived | Historical V0.9.5/V0.9.6 evidence based on cumulative-energy differences; not an active V1.0 source |
| Incomplete | Part of required quarter evidence missing, ambiguous, or deliberately contractually unconfirmed |
| Unavailable | The requisite source/target evidence cannot support a value |
| Missing | Expected **completed monitored** quarter has no archived row |
| Pre-monitoring | Interval before this meter's monitoring epoch; not a missing data failure |
| Confirmed exceedance | Complete eligible quarter, genuine dated official target and sufficient import evidence |
| Unconfirmed | Observation or contract rule cannot establish a legally definitive exceedance status |
| Unknown export | Not measured; do not show as measured 0.000 kWh |
| Inferred net export | Historical net-counter implication; not directly measured separate export |
| Mixed known/unknown export | Historical export evidence existed for only part of a quarter |
| Provisional | Derived from an opt-in unverified future tariff rule and excluded from confirmed statistics |
| Simulation | Based on hypothetical user threshold, not original contractual limits |

## Evidence versus gaps

A new meter added in the middle of a fixed quarter has no readings for the preceding minutes. HA restarts and >60-second power-source staleness can also leave gaps. The archive must not fill unknown portions with zero power merely to make the quarter look complete.

A **full 120-second smoothing window** is not the same as **complete quarter import-energy coverage**. Sustained advice requires both supported recent history and enough quarter evidence.

## Import-only meters

Mode C knows imported power but not exported power. That is enough to calculate import-only demand with suitable live input, not enough to claim exported energy was measured.

## Historical cumulative-counter provenance

Mode D is not supported in V1.0, but its archived V0.9.5/V0.9.6 rows remain.
A signed net cumulative counter could conceal import and export between samples;
therefore those rows are not silently promoted to confirmed import-only demand.
Unknown historical export remains unknown, never measured zero.

## Reconstructed and historical values

The SQLite archive retains completed quarter summaries, stored rule and target provenance, source epochs, coverage, and quality. It does not preserve a certified second-by-second peak or let the UI reconstruct missing details.

Historical Mode D rows can remain incomplete or counter-derived after upgrade.
Preserving that quality is correct caution, not proof of no exceedance.

See [History and archive](history-and-archive.md) and [Forecasts](forecasts.md).
