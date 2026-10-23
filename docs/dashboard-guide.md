# Dashboard guide — all seven tabs

The single SI Grid Monitor sidebar panel shows the **active meter** in a selector at the top. With multiple entries, always verify the displayed name before interpreting measurements. Each meter owns its settings and archive.

## Overview

The opening card covers the fixed quarter (e.g. 22:30–22:45) with a countdown. Its **IMPORT** and **EXPORT** readings represent live source power for Modes A/B/C, but Mode D can only derive **average power over past counter intervals**, not instantaneous load. A 0.000 kWh measurement is different from unknown.

The live power chart (red import, green export where known, blue smoothing, dashed forecast, target reference) and quarter-energy progression are two different graphs: kW is a rate, kWh is accumulated energy. Missing traces must not be read as measured zero. Mode D's V0.9.5 rendering is still being improved; [known limits](limitations-and-roadmap.md).

Other Overview fields:

| Field | Interpretation |
|---|---|
| Import average | So-far quarter imported kWh / elapsed hours; incomplete data limits confidence |
| Instant projected final quarter average | Extends latest supported power assumption to quarter end |
| Smoothed projected final average | Uses fully covered recent smoothing window |
| Utilization | Calculated quarter-average demand against operational target; interpretation depends on elapsed time and quality |
| Remaining budget | Quarter contracted kWh limit minus recorded imported kWh |
| Allowed remainder | Maximum *average* import power mathematically left this quarter |
| CAN ADD / MUST REDUCE | Estimated allowable extra/reduction to quarter end, **not physical connection capacity** |
| SUSTAINED CAN ADD / MUST REDUCE | Conservative forecast over the chosen future horizon, when available |
| Source measurement age | Seconds since source evidence timestamp |
| Quarter quality | Whether data coverage supports a confirmed result |

The **Next tariff transition** section lists block changes and the next lower target. A lower target outside the forecast horizon is information, not a current load-reduction command.

## Today

Explore the civil calendar day and its actual fixed quarters: **92, 96 or 100** on DST transitions, usually 96. Today's chart distinguishes live, completed, missing, incomplete and unavailable data. Tap/select a quarter to see its evidence and historic contracted target. Negative export display is separate from billing import.

## Period

Select hour/day/week/month/year/custom ranges. Adaptive bins show measured energy, demand, completeness and previous-period comparison when comparable. Missing periods must not be extrapolated as zero. A different aggregation interval is not a replacement for the fixed 15-minute contractual quarter.

## Blocks

Five-block B1–B5 comparison includes imported energy, average/maximum demand, historic targets and confirmed exceedances. Targets are taken from the dated **original quarter assignment**, not overwritten by today's settings. Selecting a block exposes high-demand intervals and their provenance. Chart reference lines and averages should be read with the legend.

## Exceedances

Shows confirmed import-demand exceedances per **completed** quarter, not arbitrary 45-minute events. If demand is above limit in three consecutive quarters, that is three exceeded quarters. Unconfirmed/incomplete measurements cannot prove compliance or non-compliance. Consult tariff provenance and source quality before comparing with utility records.

## History

Permanent SQLite explorer supports date, block, quality, source-epoch and exceedance filters, pagination and per-quarter details. **Completed intervals before monitoring** are counted separately from missing intervals after monitoring began. Source provenance strings may be long in V0.9.5 and are primarily diagnostics.

An archive stores **quarter summaries**, not precise historical instantaneous peaks or an original second-by-second graph. The administrator Recorder audit is a separate, controlled reconstruction process; review candidates before any approved write.

## Tariff Calendar

Displays tariff blocks, seasons, rule versions, holiday and DST classification. **Official/verified** and **provisional/unverified** must not be conflated. Future provisional continuation requires explicit opt-in. Contracted power is independently date-bound.

## Two vital distinctions

1. **Import-only billing**: grid export does not cancel imported energy previously used in a quarter.
2. **Quality versus value**: a numeric estimate can exist while the quarter remains incomplete or contractually unconfirmed.

Read [Calculations](calculations.md), [Forecasts](forecasts.md), and [Data quality](data-quality.md).