# Multiple independent grid meters

You may add multiple SI Grid Monitor configuration entries, such as Main Grid, Garage and Workshop. All entries share one **SI Grid Monitor** sidebar item with a friendly-name selector. The last selected meter is remembered locally when supported.

## Add a second meter

Settings → Devices & services → Add integration → SI Grid Monitor. Choose **its own** source mode, entity, sign convention and **dated contracted-power assignment**. A second meter never inherits the first one's power limits, archive or data quality.

The project stores per-entry history in separate SQLite namespaces and uses per-entry Home Assistant entity IDs. Switching the dashboard clears entry-specific requests to avoid mixing responses from the previous meter.

## Two entries on the same physical grid connection

You can test different source modes against the same grid connection, but this does **not** give you two independent electricity contracts. Configure matching **real** contracted limits where appropriate, or clearly mark a scenario as simulation. Comparing two modes is useful to learn sensor behavior but does not make a net-energy counter equal to a utility-import meter.

## What to verify

- Each meter name and active selector.
- Correct raw sensor IDs and units.
- Unique entity IDs for each entry.
- Separate archive rows, quarters, simulation settings and tariff assignments.
- Switching on Android and desktop doesn't show stale data from another meter.
- Removing one entry doesn't affect another entry.
- Default removal retains its database.

## Limitations

The automatic selector and multi-entry configuration are implemented in V0.9.5 but still warrant full real-world cross-meter acceptance. If you see another meter's tariff or source values after switching, capture a redacted screenshot and report it.

See [Installation](installation.md), [Configuration](configuration.md), [History](history-and-archive.md).