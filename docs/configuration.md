# Setup fields and options — explained

A meter's configuration is **independent of other SI Grid Monitor meters**. Replacing the source or changing contracted-power assignments can affect future interpretation; historic records have stored provenance and must not be silently recalculated.

## Setup wizard

| Field | What to enter | Why it matters |
|---|---|---|
| Friendly meter name | e.g. Main Grid, Workshop | Visible in the shared dashboard selector and Devices & services |
| Source mode | A/B/C | Determines direction and export capability; [comparison](source-modes.md) |
| Source entity/entities | Real HA `sensor.*` identifiers | Must measure the intended grid connection |
| Positive means import | On or off based on actual sensor behavior | Normalizes sign; wrong polarity reverses import and export |
| Contract validity start/end | Actual inclusive local dates | Prevents silently applying an old contract to a new year |
| B1–B5 target entry | Five kW values or shared value | Limits are **average imported power per fixed quarter**, not breaker rating |
| Provenance / record date | Name/source of distributor assignment, optional issue date | Supports reproducible historic interpretations |

**Check official limit assignments carefully.** Adding a new test meter does not copy B1–B5 limits from another meter. Use a *simulation* threshold for experiments, not fictitious contracted limits represented as real ones.

## Calculation settings

| Option | Default / V1.0 choices | Explanation |
|---|---|---|
| Safety margin | 0.000 kW | Reduces *operational advice* threshold beneath the confirmed contract limit; doesn't change the contract stored in history |
| Forecast smoothing | **120 seconds**, choose 30/60/90/120/180 | Requires enough fresh data in that *rolling* window; different from a complete 15-minute quarter |
| Sustained forecast horizon | **60 minutes**, choose 15/30/60/120 | Tests holding an additional continuous load across relevant future quarters |
| Archive retention | **Forever** | Completed quarter summaries persist in integration-owned SQLite independently from normal Recorder purges |
| Provisional tariffs 2028–2030 | **Off** | Optional planning continuation of the 2027 pattern; never equivalent to official future rules |
| Temporary simulation | **Off** | Enables what-if threshold calculations; simulated results do not become confirmed contractual statistics |
| Simulation threshold | A chosen kW value | Inactive while simulation is off; does not overwrite dated distributor assignments |

A screen may still display a simulation threshold field even when simulation is off; that stored number is **not active** unless enabled.

### Smoothing versus sustained horizon

- **120-second smoothing**: determines the recent import-power estimate for forecasts.
- **60-minute sustained horizon**: how long a hypothetical additional constant load is assessed against each intersected 15-minute tariff quarter.
- **60-second staleness**: a live power reading held beyond this limit no longer justifies assumed coverage.

### Dated contracted-power assignments

2026 and 2027 have their own rule versions; assigned **contracted-power values** must also carry their true effective dates. Options provide an editor for multiple non-overlapping assignments. Do not extrapolate a 2026 assignment into 2027 without a real new record. The illustrative test values `[3.500, 3.900, 4.100, 4.200, 4.200] kW` are **not default values** or a claim about your installation.

### Changing or migrating a source

A sensor, polarity or target change can create a new source/configuration epoch.
Historical rows preserve their original context, and ambiguous transition
quarters cannot create a confirmed exceedance.

For a legacy V0.9.6 Mode D entry, **Reconfigure** explicitly selects A/B/C and
validates the replacement W/kW source. The same entry ID and SQLite namespace
remain, while the config-entry unique ID changes to the accepted source identity
and new measurements use a new epoch. If another entry already owns that source,
the flow rejects it instead of merging entries or archives.

### Archive removal

Default ordinary entry removal **keeps** the SQLite archive. Explicit permanent
deletion requires a separate entry-scoped confirmation valid for ten minutes;
optionally create a backup first. Removing or deleting an entry is not required
to migrate a legacy source. See [History and archives](history-and-archive.md).

## Verifying every setting

After submission, on Overview check: active meter name, source age, import/export direction, B1–B5 block and target, simulation status, measurement coverage and the first completed quarter. See [Getting started](getting-started.md) and [Troubleshooting](troubleshooting.md).
