# Installation, upgrade and first validation

## Installation language

The first integration step is **Language / Jezik**. Choose English (default) or
Slovenščina. This preference initializes SI Grid Monitor's own dashboard and
reports. The accessible EN/SL control in the shared dashboard header can create
a browser-specific override that persists across navigation and reloads.

Home Assistant's native setup and OptionsFlow dialog chrome still follows the
Home Assistant user's frontend locale. Choosing Slovenščina here does not
change Home Assistant's global language.

## Prerequisites

- Working **Home Assistant** installation with an existing compatible sensor.
- HACS installed and accessible (a custom repository may be required; the project is not assumed to be in HACS's default catalogue).
- Ability to restart Home Assistant and create a full backup.
- For contractual advice: real B1–B5 limits and their validity dates from your electricity distributor.

The integration calculates locally. It does not require user-provided cloud
credentials, an additional database server, manually pasted Lovelace YAML or
JavaScript resource registration.

## Install through HACS

1. Open **HACS → Custom repositories** (the menu location may vary by HACS version).
2. Add `https://github.com/igormesarec/si-grid-monitor`, category **Integration**.
3. Find **SI Grid Monitor** in HACS and choose **Download/Install**.
4. **Restart Home Assistant**.
5. Navigate to **Settings → Devices & services → Add integration**, search **SI Grid Monitor**.
6. Complete the [source and contract setup](configuration.md).
7. Open **SI Grid Monitor** from the left sidebar: the panel registers automatically.

**No project website is required for running the integration.** Documentation-site build work is separate from Home Assistant deployment.

## Install into a test instance manually

For a disposable test system only, copy the repository's `custom_components/si_grid_monitor` directory into your HA configuration's `custom_components` folder, restart HA, then add the integration. Prefer HACS for ordinary users.

## Updating an existing installation

**Before upgrading**: use Home Assistant's backup system and preserve a copy of the integration-owned SQLite database and associated journal files if doing manual filesystem operations. Do not remove/re-add an existing meter just to update the code: that creates a new configuration entry and can break its archive namespace continuity.

1. Back up.
2. Update SI Grid Monitor from HACS.
3. Restart HA and refresh the browser or Android Companion frontend to clear versioned JS cache.
4. Check existing meter name, source entity, polarity, original contracted limits, today/history and source age.
5. Verify that historical completed quarters and source epochs remain intact.
6. Allow a full new 15-minute quarter to complete and inspect coverage.

The V1.0 release candidate preserves Mode A/B/C entry IDs, entity identities and
schema-6 archives in automated tests, but that does not establish acceptance on
your Home Assistant installation. Test with a backup.

## V0.9.6 → V1.0 release-candidate migration

V1.0.2 contract management is the current merged application. V1.0.3 localization
remains a draft release candidate until it passes real Home Assistant acceptance.
Use a copied/test Home Assistant instance until the release candidate is accepted.

V1.0.3 also defaults to **Storage Optimized** entity publishing. No SI Grid
Monitor-specific Recorder or InfluxDB YAML exclusions are required for a normal
new installation. If an older installation already uses temporary exclusions,
leave them in place until the optimized event rate is validated; then follow the
[manual cleanup and exclusion-removal guide](manual-storage-cleanup.md). Updating
does not purge existing historical database rows.

### Backup first

1. Create a full Home Assistant backup.
2. Record every SI Grid Monitor entry ID, friendly name, entity unique IDs,
   source mode, source entity, polarity and B1–B5 assignments.
3. Preserve `.storage/si_grid_monitor_<entry_id>.db` and its associated WAL/SHM
   files using a consistent stopped-HA or supported backup procedure.
4. Record archive row counts, oldest/newest quarter, source epochs and current
   checkpoint information where available.

### Existing Mode A/B/C entries

Upgrade through HACS, restart Home Assistant and confirm the same entry, entities
and archive reopen. Check sign/direction, target assignment, current checkpoint,
history totals and the next completed quarter. Do not remove and recreate the
entry as an upgrade step.

### Legacy experimental Mode D entries

V1.0 detects `source_mode=cumulative_energy` before constructing a runtime. It:

1. disables the old Mode D measurement runtime;
2. preserves the configuration, schema-6 database, completed rows, checkpoint
   and source/configuration epochs;
3. displays an unsupported Mode D notice in Home Assistant;
4. does not interpret Wh/kWh values as W/kW;
5. does not silently reclassify historical counter-derived rows.

Use the entry's **Reconfigure** action to select Mode A, B or C and a valid live
W/kW source. Successful reconfiguration retains the same config-entry ID and
SQLite namespace. The config-entry unique ID is rebound to the accepted live
source, and subsequent measurements start a new source epoch, separate from the
legacy Mode D history.

If another SI Grid Monitor entry already owns the selected canonical source,
reconfiguration is rejected as a duplicate. Nothing is merged. Select a genuinely
different grid sensor, or decide which existing entry should own that source;
do not delete archives merely to bypass the guard.

If in-place reconfiguration is unsuitable, keep the old database and create a
separate supported meter. A newly created entry has a new archive namespace and
does not automatically attach the old database.

## Multiple meters

You can add more than one SI Grid Monitor configuration entry. They share **one** sidebar panel with a remembered active-meter selector, but use **separate** source settings and SQLite namespaces. A second entry does not reuse your first entry's dated power assignments. See [Multiple meters](multiple-meters.md).

## Rollback warning

Restoring an earlier integration version may not understand newly written metadata or newer settings. Make a copy of the complete Home Assistant configuration **before** the upgrade, and test restoration on a copy when possible. Do not delete an existing integration entry as a rollback shortcut.

## Uninstall / archive deletion

Native removal **retains the archive by default**, including a disabled legacy
Mode D archive. Explicit permanent deletion is possible using an entry-specific
Options confirmation, valid for 10 minutes, with optional SQLite backup before
actual removal. It should not be used casually and is never required for an
upgrade. See [History and archives](history-and-archive.md).

## Documentation and security

Only download from the correct repository: [igormesarec/si-grid-monitor](https://github.com/igormesarec/si-grid-monitor). Never include Home Assistant tokens, IP addresses, personal meter identifiers, or database files in public bug reports. For bug reports share only necessary redacted screenshots, version, sensor type, cadence and logs.
