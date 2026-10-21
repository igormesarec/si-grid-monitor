# SI Grid Monitor source-mode scope addendum (V0.9.5)

This approved addendum supersedes the earlier input-mode roadmap only. The
frozen `SPECIFICATION.md` remains unchanged.

SI Grid Monitor supports exactly four selectable Home Assistant input modes:

1. One signed live W/kW grid-power sensor with configurable polarity.
2. Separate nonnegative W/kW import and export power sensors.
3. One nonnegative W/kW import-only power sensor; export is unknown.
4. A cumulative imported-energy counter and optional cumulative exported-energy
   counter in Wh/kWh, converted by integration-owned derived-power entities.

Former Mode E (aligned completed-quarter records) is not a selectable source
mode or active acceptance requirement. Existing archive rows, historical
reconstruction and reports are retained and are not invalidated by this scope
change.

All modes feed one normalization, calculation, tariff, forecasting and SQLite
archive engine. Internally positive means import and negative means export.
Contractual demand always integrates imported power independently; export never
offsets imported energy.

Counter-derived power is an interval-average estimate. A first reading creates
only a baseline. Negative deltas/reset events create a fresh baseline, duplicate
timestamps are ignored, and unavailable or delayed readings remain explicit.
An interval that cannot be allocated across a fixed quarter from source evidence
must not create a confirmed contractual result. Instantaneous or sustained
forecasts are unavailable when the source cannot support them.
