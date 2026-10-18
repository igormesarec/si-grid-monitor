# SI Grid Monitor V0.2 — Real Home Assistant Test Plan

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

## Lifecycle and observations to report

Test options reload, integration reload, Home Assistant restart, HACS update,
disable/enable, removal and clean reinstall. Record Home Assistant version,
database backend, source update cadence, logs, entity availability, archive row
counts and any mismatch with official meter quarters. This plan validates
software behavior only; distributor readings remain authoritative.
