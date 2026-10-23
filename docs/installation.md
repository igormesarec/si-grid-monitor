# Installation, upgrade and first validation

## Prerequisites

- Working **Home Assistant** installation with an existing compatible sensor.
- HACS installed and accessible (a custom repository may be required; the project is not assumed to be in HACS's default catalogue).
- Ability to restart Home Assistant and create a full backup.
- For contractual advice: real B1–B5 limits and their validity dates from your electricity distributor.

The integration calculates locally. It does not require user-provided cloud credentials, an additional database server, manually pasted Lovelace YAML, or a manually created derivative helper for Mode D.

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

V0.9.5 preserves legacy Mode A entry IDs and source identity in code, but a successful automated test is not a guarantee that your specific installation has been accepted. Test with a backup.

## Multiple meters

You can add more than one SI Grid Monitor configuration entry. They share **one** sidebar panel with a remembered active-meter selector, but use **separate** source settings and SQLite namespaces. A second entry does not reuse your first entry's dated power assignments. See [Multiple meters](multiple-meters.md).

## Rollback warning

Restoring an earlier integration version may not understand newly written metadata or newer settings. Make a copy of the complete Home Assistant configuration **before** the upgrade, and test restoration on a copy when possible. Do not delete an existing integration entry as a rollback shortcut.

## Uninstall / archive deletion

Native removal **retains the archive by default**. Explicit permanent deletion is possible using an entry-specific Options confirmation, valid for 10 minutes, with optional SQLite backup before actual removal. It should not be used casually. See [History and archives](history-and-archive.md).

## Documentation and security

Only download from the correct repository: [igormesarec/si-grid-monitor](https://github.com/igormesarec/si-grid-monitor). Never include Home Assistant tokens, IP addresses, personal meter identifiers, or database files in public bug reports. For bug reports share only necessary redacted screenshots, version, sensor type, cadence and logs.
