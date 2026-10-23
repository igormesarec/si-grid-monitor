# Multiple independent grid meters

You may add multiple SI Grid Monitor configuration entries, such as Main Grid, Garage and Workshop. All entries share one **SI Grid Monitor** sidebar item with a friendly-name selector. The last selected meter is remembered locally when supported.

## Add a second meter

Settings → Devices & services → Add integration → SI Grid Monitor. Choose **its own** source mode, entity, sign convention and **dated contracted-power assignment**. A second meter never inherits the first one's power limits, archive or data quality.

The project stores per-entry history in separate SQLite namespaces and uses per-entry Home Assistant entity IDs. Switching the dashboard clears entry-specific requests to avoid mixing responses from the previous meter.

## Two entries on the same physical grid connection

Two entries observing the same physical connection do **not** create two
electricity contracts. V1.0 rejects a duplicate canonical source during setup or
legacy reconfiguration. Use genuinely separate sources/meters, or decide which
entry owns the source; never merge archives or delete history to bypass the guard.

## What to verify

- Each meter name and active selector.
- Correct raw sensor IDs and units.
- Unique entity IDs for each entry.
- Separate archive rows, quarters, simulation settings and tariff assignments.
- Switching on Android and desktop doesn't show stale data from another meter.
- Removing one entry doesn't affect another entry.
- Default removal retains its database.

## Limitations

The automatic selector and multi-entry configuration are implemented but still
require release-candidate acceptance on real Home Assistant and Android. If you
see another meter's tariff or source values after switching, capture a redacted
screenshot and report it.

See [Installation](installation.md), [Configuration](configuration.md), [History](history-and-archive.md).
