# SI Grid Monitor V0.3 — Real Home Assistant Test Plan

Use a disposable or backed-up Home Assistant instance. Never infer physical
connection capacity from CAN ADD values.

## Installation and upgrade

1. Install the PR branch manually under `custom_components/si_grid_monitor` and
   restart Home Assistant.
2. Upgrade an existing V0.1 config entry. Confirm it migrates without creating a
   duplicate entry and preserves source, polarity, target and margin.
3. Confirm all entities load, then reload and restart Home Assistant twice.
4. Confirm the `.storage/si_grid_monitor_<entry_id>.db` archive remains readable,
   does not duplicate quarters, and current-quarter recovery reports gaps rather
   than inventing downtime consumption.

## Source and calculations

1. Exercise a W source and a kW source. Verify positive import and negative
   export, then reverse polarity in options and verify a new source epoch.
2. Feed +6 kW / -8 kW / +6 kW for consecutive five-minute periods. Confirm
   1.000000 kWh import, 0.666667 kWh export and 4.000000 kW fixed-quarter demand.
3. Alternate import/export about every 30 seconds. Confirm export never reduces
   accumulated import demand and the rolling signed metric remains separate.
4. Stop updates for over 60 seconds. Confirm fresh-input advice becomes
   unavailable and quality/coverage identifies the gap.

## Forecasts and configuration

1. Verify 30/60/90/120/180-second smoothing choices, including 120 default.
2. Verify percentage displays have two decimals and internal archive values keep
   higher precision.
3. Test sustained horizons 15/30/60/120 minutes across midnight, spring-forward,
   autumn repeated time and exact `:00/:15/:30/:45` boundaries.
4. With -1.50 kW held export and a 4.80 kW target, confirm a 60-minute sustained
   addition near 6.30 kW while current-quarter CAN ADD may be much higher.
5. Apply a sudden +3 kW step. Confirm the instantaneous conservative scenario
   changes sustained advice immediately before the smoothed path catches up.
6. Confirm stale/incomplete history publishes a reason instead of a safe value.
7. Upgrade a V0.2 entry and confirm its old target appears identically in B1–B5.
   Switch to per-block mode, set five distinct values, reload and verify the
   current and next target sensors follow block transitions.
8. Run a sustained forecast across a block boundary and confirm each future
   quarter uses its own block target, especially when the next target is lower.

## Tariff calendar

1. Compare current block, season and day type with the official URO 2026/2027
   table and Moj Elektro for the same local interval. Distributor data remains
   authoritative; report any discrepancy with UTC time, offset and fold.
2. Check a normal weekday, Saturday, Sunday, weekday holiday and weekend holiday
   in both seasons. Verify the holiday name remains visible on weekends.
3. Check 31 December/1 January and the February/March and October/November season
   transitions. Check the 1 January 2027 rule-version change.
4. On DST spring-forward and autumn fallback, confirm 23/25 hourly calendar rows,
   no invented local hour and two distinct repeated 02:00 rows with different
   offsets/folds.
5. Keep provisional rules disabled and inspect 2028–2030: status must be
   unverified and the block unavailable. Enable provisional continuation and
   confirm every result is visibly labeled provisional, never official.

## Archive and recorder

1. Allow at least three completed quarters, including export and an exceedance.
   Inspect rows for UTC/local timestamps, fold/offset, import/export, coverage,
   provenance, targets and quality.
2. Purposely restart mid-quarter and verify checkpoint recovery and exactly-once
   quarter finalization.
3. Remove a test archive row, reload the integration and confirm detailed
   recorder history backfills it as `recorder_reconstructed` when coverage exists.
4. Confirm hourly recorder statistics are not used, gaps remain incomplete and a
   recorder reconstruction cannot replace a better live/aligned record.
5. Enable a temporary simulation threshold. Confirm live entities respond but
   genuine contractual archive/exceedance statistics retain the real target.
6. Change the contractual target and then source polarity during a test period.
   Confirm later backfill uses each setting only in its persisted effective epoch;
   a quarter crossed by either change is marked mixed/unknown and is not counted
   as an exceedance.
7. Reload immediately after a `:00/:15/:30/:45` boundary. Confirm the completed
   quarter and final checkpoint exist exactly once after reload, with no closed-
   database task exception in the log.
8. Create a missing-data quarter with some observed import. Confirm its partial
   energy remains inspectable but is excluded from valid contractual totals,
   demand maxima, averages and exceedance counts.
9. Inspect a new schema-4 row for tariff block, calendar year, season, day type,
   rule version/status/source and the effective immutable block target.
10. Upgrade a copy of a V0.2 database. Confirm each configuration epoch's common
    target migrated to B1–B5 and no measurement or existing target was rewritten.
11. Restart with no current live state and confirm last-completed demand restores
    from SQLite with its quality and provenance.
12. With provisional tariffs disabled, cross from 2027-12-31 into 2028 and test
    representative quarters in 2028–2030. Physical power, energy, archive rows
    and checkpoints must continue while contractual advice is unavailable.
13. Enable provisional tariffs and confirm advice includes provisional status
    and a reason. A provisional exceedance must not increase the confirmed count.
14. Toggle provisional policy and reload. Previously completed rows must retain
    their original policy and rule status.

## Lifecycle and observations to report

Test options reload, integration reload, Home Assistant restart, HACS update,
disable/enable, removal and clean reinstall. Record Home Assistant version,
database backend, source update cadence, logs, entity availability, archive row
counts and any mismatch with official meter quarters. This plan validates
software behavior only; distributor readings remain authoritative.
