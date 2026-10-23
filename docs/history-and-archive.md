# History, archive, checkpointing and recovery

SI Grid Monitor stores completed 15-minute quarter **summaries** in an
integration-owned SQLite schema-6 database. Archive namespaces are specific to
the configuration entry, and retained data survives ordinary Home Assistant
Recorder purges.

## What it stores

- Quarter start/end timestamps and local-context classification.
- Import/export totals when evidenced, demand averages, quality and coverage.
- Dated targets, source/configuration epochs, tariff-rule metadata and provenance.
- Eligible/confirmed exceedance results and unconfirmed statuses.
- Runtime checkpoints needed to restore an in-progress quarter without fabricating downtime measurements.

**Not stored:** a guaranteed instantaneous historic peak or fully detailed continuous source trace. The HISTORY charts must not invent such detail from 15-minute summary values.

## Missing versus pre-monitoring

If a new meter begins at 22:22, earlier completed quarters are **before monitoring**, not missing monitored records. A completed monitored quarter with a missing row is different from a stored incomplete or unavailable quarter. This distinction matters for coverage percentages and reporting integrity.

## Source and target changes

Source/sign and dated contract changes have stored epochs/provenance. A change that makes an interval ambiguous must not manufacture a confirmed exceedance. Past rows retain the values and rule status known when recorded.

Reconfiguring a legacy Mode D entry to A/B/C keeps the config-entry ID and
archive namespace but starts a new source epoch. Historical counter-derived
quality, targets and provenance are preserved; V1.0 does not relabel those rows
as confirmed live-power measurements.

## Home Assistant Recorder audit

An administrator-controlled HISTORY audit can inspect available detailed Recorder readings and propose bounded reconstruction. Review what would change, the original provenance and quality, and backup first. Do not use Recorder statistics as a substitute for missing timestamped measurements. A proposal is not permission to silently overwrite a better archive row.

## Safe removal

**Ordinary native HA integration-entry removal retains the archive by default.** To permanently delete a specific meter's database, the user must explicitly authorize that entry in Options, type the exact confirmation and perform the matching removal within **10 minutes**. The deletion may include an optional consistent backup. The implementation closes the database before removing the entry-owned SQLite file and its WAL/SHM sidecars.

Permanent deletion is irreversible without a valid backup. Never test deletion on your only live database.

## Backup and recovery precautions

1. Take a complete Home Assistant backup, preferably while databases are quiescent.
2. Preserve the original configuration entry ID and its backup; a new installation entry gets a **different archive namespace**.
3. If performing manual file restore, **stop HA**, keep untouched copies and restore only the database associated with the original entry.
4. Do not rename one meter's database to another meter's ID without a controlled migration and testing; no automatic archived-database reattachment is currently promised.
5. Validate historical count, oldest/newest quarters, coverage and original tariff targets after any restore.

The documentation cannot substitute for a tested restore procedure on your specific HA version.

## Retention

The exposed retention choice is **forever**. This is useful for long-term
reports but requires disk monitoring and independent backups. "Forever" does
not mean immune to filesystem failure, deliberate deletion or lost HA backups.

See [Multiple meters](multiple-meters.md), [Dashboard guide](dashboard-guide.md), [Testing](testing-and-validation.md).
