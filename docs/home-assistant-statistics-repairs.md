# Home Assistant statistics repair warnings

## What the warning means

Home Assistant can report **The entity no longer has a state class** for an
SI Grid Monitor current-quarter energy entity after upgrading from V1.0.2 or
older. Those releases exposed current-quarter imported and exported energy as
`total` statistics. V1.0.3 corrected the live metadata: these values restart at
zero every fixed 15-minute quarter and are no longer advertised as lifetime
energy totals.

The warning describes retained Home Assistant Recorder statistics metadata. It
does **not**, by itself, mean that the live kWh value or SI Grid Monitor's
quarter calculation has failed.

Typical affected statistics IDs use the existing entity IDs, for example:

- `sensor.<meter>_current_quarter_imported_energy`
- `sensor.<meter>_current_quarter_exported_energy`

Names depend on the meter name and entity registry. Review every meter
separately. Do not rename or recreate entities to hide the warning.

## Three different histories

- **State history** is Recorder's sequence of Home Assistant entity states.
- **Long-term statistics** is Home Assistant's separate hourly statistical
  series for eligible sensors with a state class.
- **SI Grid Monitor archive** is the per-meter schema-7 SQLite archive of fixed
  15-minute records, targets, quality and provenance.

Deleting an obsolete Home Assistant statistics series does not delete the SI
Grid Monitor archive. Conversely, Recorder exclusion does not remove statistics
metadata that already exists.

## Why the live entity has no state class

The current-quarter kWh sensor is a bounded live progress value. It increases
inside one quarter and resets at the next canonical UTC quarter boundary. The
Storage Optimized publication profile coalesces state events and may not publish
the exact final value immediately before the reset. Marking that series
`total` or `total_increasing` could therefore lose energy from Home Assistant's
sum or misinterpret a reset. The exact completed-quarter value remains in the
SI Grid Monitor archive.

This release does not silently turn the current-quarter entities into lifetime
energy counters. A future lifetime-energy design would require new identities,
restart-safe accumulation and explicit incomplete-quarter rules.

## Backup before reviewing statistics

1. Create a complete Home Assistant backup.
2. Record the Home Assistant and SI Grid Monitor versions.
3. Record the affected entity/statistics IDs and their current states.
4. Record the SI Grid Monitor archive quarter count and database size.
5. Record a recent completed-quarter demand and the current contract assignment.

## Supported Home Assistant UI procedure

1. Open **Developer tools → Statistics** (called **Statistics** under developer
   tools in current Home Assistant releases).
2. Find the affected statistics ID and open its repair details.
3. Review whether the historical series is useful. Current-quarter totals from
   older releases are not equivalent to a verified lifetime consumption meter.
4. If you decide the obsolete statistics are not needed, use Home Assistant's
   own delete-statistics action for that exact ID and confirm the warning shown
   by Home Assistant.
5. Do not delete similarly named power statistics or another meter's series.

Statistics deletion is an administrator decision and can permanently remove
that Home Assistant statistics history. SI Grid Monitor never performs it
automatically and never updates Recorder's `statistics`,
`statistics_short_term` or `statistics_meta` tables directly.

If Recorder currently excludes SI Grid Monitor entities, keep the exclusion in
place while reviewing the old series. Temporarily re-enabling Recorder is not
required merely to delete obsolete metadata. If exclusions are later removed,
the current-quarter energy entities keep the same IDs but remain ineligible for
new long-term statistics because they have no state class. Power measurement
entities retain their existing measurement metadata.

## Verify after cleanup

Confirm all of the following:

1. The selected repair warning disappears.
2. The live current-quarter sensor still updates in `kWh`.
3. Its state class remains absent.
4. It resets at the next 15-minute boundary.
5. Today, Period, Blocks, Exceedances, History and Contracts still show archive
   data without depending on the removed Home Assistant statistics.
6. The schema-7 archive quarter count and recent records are unchanged.
7. Other meters and unrelated statistics remain intact.

If the warning returns, verify the integration/frontend version, restart Home
Assistant, refresh the browser, and confirm that no old copy of the integration
still declares `total`. Do not edit the Recorder database manually. Capture the
entity's current metadata and report it with the affected statistics ID.

## Official references

- [Home Assistant sensor state classes](https://developers.home-assistant.io/docs/core/entity/sensor/)
- [Home Assistant long-term statistics](https://www.home-assistant.io/docs/configuration/long-term-statistics/)
- [Home Assistant Developer tools: Statistics](https://www.home-assistant.io/docs/tools/dev-tools/)
