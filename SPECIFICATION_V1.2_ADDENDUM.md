# SI Grid Monitor — V1.2 Addendum

Status: V0.2 implementation addendum to the frozen MASTER PRODUCT SPECIFICATION
V1.1 in `SPECIFICATION.md`. The V1.1 file remains authoritative and unchanged.
Where this addendum adds V0.2 behavior, it does not weaken any V1.1 requirement.

## Import-only invariant

The main fixed-quarter contractual calculation uses imported grid energy only.
After source polarity normalization, positive is import and negative is export.
For every live, forecast, archived or reconstructed segment:

`import_power = max(0, signed_grid_power)`

`export_power = max(0, -signed_grid_power)`

Export never offsets import from another segment. The signed rolling 15-minute
average remains a separate non-contractual energy-flow metric. Smoothed billing
forecasts average the time-weighted import path, not a clamped signed average.

Acceptance case: +6 kW for five minutes, -8 kW for five minutes and +6 kW for
five minutes produces 1.000000 kWh import, 0.666667 kWh export, +0.333333 kWh
signed net energy, 4.000000 kW import demand and +1.333333 kW signed average.
At 4.60 kW the contractual utilization is displayed as 86.96% and is not an
exceedance.

## V0.2 live configuration and persistence

- Forecast smoothing choices are 30, 60, 90, 120 and 180 seconds; default 120.
- Utilization percentages display exactly two decimal places while calculations
  and stored records retain full precision.
- Source entity, polarity, target, safety margin and supported calculation
  options are editable through reconfiguration. A change creates a source epoch;
  old history retains its provenance.
- Completed fixed quarters are stored in an integration-owned SQLite archive,
  namespaced per config entry, with Forever default retention, schema migration,
  WAL, indexes, idempotent writes and bounded checkpointing.
- Detailed recorder states may reconstruct missing quarters. Hourly statistics
  are not treated as quarter data. Missing coverage is not fabricated, and a
  lower-quality reconstruction cannot overwrite a better record.
- Temporary simulation targets do not contaminate genuine contractual history.

## Sustained load forecasting

V0.2 adds a continuous-load forecast distinct from current-quarter advice:

- `sensor.si_grid_sustained_can_add_power`
- `sensor.si_grid_sustained_must_reduce_power`
- `sensor.si_grid_sustained_forecast_quality`

The selectable horizon is 15, 30, 60 (default), or 120 minutes beginning now.
The calculation evaluates the current-quarter remainder and every future fixed
quarter intersecting the horizon. A partially intersected future quarter is
evaluated in full; the proposed addition/reduction applies only for its scheduled
duration. Current imported energy already accumulated is preserved. Future
quarters begin with fresh energy budgets.

For addition A and reduction R, each signed segment is transformed before
integration:

`adjusted_import_for_addition = max(0, signed_grid_power + A)`

`adjusted_import_for_reduction = max(0, signed_grid_power - R)`

The configured recent time-weighted signed path is repeated as a persistence
scenario. The latest valid instantaneous signed measurement is separately held
constant as a conservative scenario. SUSTAINED CAN ADD is the smaller admissible
addition; SUSTAINED MUST REDUCE is the larger required reduction. A monotonic
binary search uses 0.000001 kW tolerance. The API accepts a target per quarter so
V0.3 can supply block targets without rewriting the engine; V0.2 supplies the
common configured operational target and invents no tariff blocks.

If recent coverage is incomplete or the source is stale, no unsupported safe
value is published. If the current quarter is already unrecoverable, no reduction
is described as restoring it; reduction can only prevent further import and make
recoverable future quarters comply.

All sustained advice is an imported-energy-budget estimate, not guaranteed
breaker, phase, wiring, connection or inverter capacity. It assumes recent
behavior persists and is not a solar-generation or weather forecast.

## Deferred scope

Official Slovenian dated/versioned five-block rules, holiday calendars,
block-specific automatic targets, the six professional dashboard tabs, alerts,
public archive query/export UI, predictive PV/weather forecasting and full HACS
listing/release validation remain later milestones as described in V1.1.
