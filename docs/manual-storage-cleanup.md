# Manual cleanup of data created by older releases

V1.0.3 prevents future uncontrolled SI Grid Monitor entity-event growth. It does
**not** delete old Home Assistant Recorder rows, InfluxDB series, backups or
integration quarter archives. Cleanup is a separate administrator operation.

## Before doing anything

1. Install the optimized release, restart Home Assistant and confirm both meters,
   all eight tabs, contracts and quarter archives work.
2. Keep any temporary SI Grid Monitor Recorder/InfluxDB exclusions in place while
   validating **Data Publishing & Storage** for at least a representative day.
3. Create and verify a complete Home Assistant backup. Back up InfluxDB using its
   documented tooling. Preserve the per-entry `si_grid_monitor_*.db` files.
4. Record database sizes, retention settings and the exact SI Grid Monitor entity
   IDs. Never test cleanup against the only copy of production data.

## Recorder

Use supported Home Assistant Recorder purge/entity-purge services for the exact
entities and the Home Assistant version in use. Purging rows and reclaiming
physical file space are different operations; do not run an unscheduled manual
`VACUUM` against a live Home Assistant database. SI Grid Monitor cannot validate
or reverse these administrator actions.

## InfluxDB

Follow the documentation for the installed InfluxDB major version. Retention,
series deletion, shard management and index conversion are database-admin tasks.
Do not mix instructions for `inmem` and `tsi1` indexes or delete shard files by
hand. SI Grid Monitor never requests credentials and does not modify these
settings.

## Removing temporary exclusions

After the optimized profile is independently validated, remove only the
temporary SI Grid Monitor exclusion entries, restart/reload as required by Home
Assistant, and monitor event rate and disk allocation. Keep the exclusions if
Automation Priority or a Custom fast policy produces an unacceptable rate.
Removing an exclusion does not restore previously deleted history.

The integration-owned quarter archive is valuable contractual evidence and is
unrelated to Recorder/InfluxDB cleanup. Do not delete it to reduce those stores.
