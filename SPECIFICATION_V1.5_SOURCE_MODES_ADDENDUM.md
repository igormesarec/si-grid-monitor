# SI Grid Monitor source-mode scope addendum (V0.9.5)

This approved addendum supersedes the earlier input-mode roadmap only. The
frozen `SPECIFICATION.md` remains unchanged.

SI Grid Monitor supports exactly four selectable Home Assistant input modes:

1. One signed live W/kW grid-power sensor with configurable polarity.
2. Separate nonnegative W/kW import and export power sensors.
3. One nonnegative W/kW import-only power sensor; export is unknown.
4. Cumulative Wh/kWh energy counters converted by integration-owned
   derived-power entities. The user explicitly chooses one of three behaviors:
   an import-only cumulative counter, one bidirectional net-energy counter, or
   separate cumulative import and optional export counters.

Former Mode E (aligned completed-quarter records) is not a selectable source
mode or active acceptance requirement. Existing archive rows, historical
reconstruction and reports are retained and are not invalidated by this scope
change.

All modes feed one normalization, calculation, tariff, forecasting and SQLite
archive engine. Internally positive means import and negative means export.
Contractual demand always integrates imported power independently; export never
offsets imported energy.

Counter-derived power is an interval-average estimate. A first reading creates
only a baseline. Negative deltas reset monotonic import/export counters, but are
valid direction changes for a bidirectional net counter. Duplicate timestamps
are idempotent only when their values match. Separate import/export counters
retain independent baselines, timestamps and update cadence; values are joined
only where both channels evidence the same time span.

A bidirectional net delta may hide import/export reversals between readings, so
it is not sufficient evidence for confirmed import-only contractual demand.
Reverse polarity is explicitly configurable and defaults to counter increase =
grid import. Genuine reverse flow and an unmarked counter reset cannot always be
distinguished from the numeric delta alone. Explicit `last_reset` changes and
implausibly large interval discontinuities are rejected conservatively and start
a new baseline; ordinary negative deltas remain valid reverse-flow evidence.

Existing V0.9 signed-power entries retain their config-entry IDs, entity unique
IDs, raw source identity and schema-6 archive namespace. A code upgrade alone
must not create a new configuration epoch.

Multiple entries share one sidebar panel but retain separate databases and
friendly names. Entry removal keeps its database by default. Permanent deletion
requires an entry-scoped confirmation that expires after 10 minutes, may create a SQLite backup, and may remove only the
selected entry-owned database plus its WAL/SHM sidecars after durable shutdown.

Historical export presentation distinguishes directly measured export,
bidirectional-net inferred export, and unknown export. Unknown export must never
be presented as a measured zero.

Unavailable or delayed readings remain explicit.
An interval that cannot be allocated across a fixed quarter from source evidence
must not create a confirmed contractual result. Instantaneous or sustained
forecasts are unavailable when the source cannot support them.
