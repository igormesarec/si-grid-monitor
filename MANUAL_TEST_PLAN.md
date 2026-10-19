# SI Grid Monitor V0.4.1 - Real Home Assistant Test Plan

Use a disposable or backed-up Home Assistant instance. Never infer physical
connection capacity from CAN ADD values.

## Automatic sidebar dashboard acceptance

1. Install through HACS, restart, and add the integration.
2. Submit the displayed 120-second smoothing and 60-minute horizon without
   opening either dropdown; confirm there is no `expected str` error.
3. Enter the real 2026 fixture through native controls; JSON must not appear.
4. Confirm **SI Grid Monitor** appears automatically and opens all three views
   without Lovelace, YAML, or resource configuration.
5. Repeat after reload, restart, and HACS update; exactly one panel must remain.
6. Add a second entry and verify selection and archive isolation. Unload entries
   one at a time and verify the panel is removed only after the last entry.
7. Check desktop, tablet, mobile, light/dark themes, and reconnect behavior.
8. Confirm the local countdown creates no one-second Recorder states.
9. Confirm DST days show 92/100 quarters and 23/25 tariff hours.

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
7. Upgrade a V0.2 entry and confirm its old target remains identically in the
   legacy B1–B5 fields, but contractual sensors are unavailable because no
   validity dates were invented. Add an explicit dated assignment in Options,
   reload and verify current/next target sensors follow block transitions.
8. Run a sustained forecast across a block boundary and confirm each future
   quarter uses its own block target, especially when the next target is lower.
9. Configure the documented values in `REAL_WORLD_VALIDATION.md` (B1 3.50,
   B2 3.90, B3 4.10, B4/B5 4.20 kW) only in a suitable test entry. During 2026,
   verify the active target, utilization, forecasts, CAN ADD and MUST REDUCE at
   representative B1–B5 intervals and immediately across a block transition.
   Do not apply this user-specific assignment to another installation or year.

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
9. Inspect a new schema-5 row for tariff block, calendar year, season, day type,
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
15. With the documented 2026 fixture configured, inspect completed rows from
    each block. Confirm they retain the effective target and provenance, and an
    exceedance is confirmed only against that quarter's official block target.
16. Advance across 31 December 2026 with only the documented 2026 assignment.
    Confirm 2027 physical power and archive rows continue, while target,
    utilization, forecasts and advice are unavailable with an expired/missing
    assignment reason. Then add a separate 2027 assignment and reload.

## Lifecycle and observations to report

Test options reload, integration reload, Home Assistant restart, HACS update,
disable/enable, removal and clean reinstall. Record Home Assistant version,
database backend, source update cadence, logs, entity availability, archive row
counts and any mismatch with official meter quarters. This plan validates
software behavior only; distributor readings remain authoritative.

## PR #5 UI correction acceptance

1. During initial setup, inspect explanatory text underneath individual fields (sensor polarity, each B1–B5 input, contract dates, margin, smoothing, horizon); repeat in Options. Switch HA locale between English and Slovenian.
2. On TODAY, verify actual positive import bars, negative average export bars, distinct B1–B5 colors, and a contractual limit marker that changes at block boundaries. Missing intervals must not appear as measured zero.
3. Click a stored historical quarter. Verify its detailed SQLite summary appears on TODAY (not only OVERVIEW). Click a missing quarter and verify an honest missing/no-record message.
4. On TARIFF CALENDAR, click arbitrary hours and check block, limit, rule status/version, day type, holiday, UTC offset, and repeated 02:00 DST fold.
5. On OVERVIEW, verify next-lower-limit information separates 'outside sustained horizon' from available/incomplete horizon-wide forecast advice. A 0.10-kW target reduction must not imply 0.10 kW of load shedding without demand evidence.
6. Test same screens on small mobile width and dark theme; ensure no stale selection leaks across dates or meter entries.
7. Use a quarter with 0.75 kWh imported and 0.25 kWh exported. Confirm the chart shows +3.00 kW import above zero, -1.00 kW average export below zero and +4.20 kW target on the same Y-axis scale.
8. Keep TODAY open during a quarter boundary. Confirm the previous LIVE slot becomes its archived completed row after refresh and the new interval becomes LIVE; neither projected exceedance is added to confirmed exceedances.
9. Switch rapidly between two configured meters while TODAY and archive requests are in flight. Confirm the active-meter label changes, every prior selection clears and a delayed response cannot repopulate the new meter with old data.
10. On spring-forward, normal and autumn-fallback dates verify 92, 96 and 100 fixed-quarter slots. For the repeated local hour, verify the archive detail labels show distinct UTC offsets.
11. Compare the sum of B1-B5 valid counts, import/export energy and confirmed exceedances with the daily totals. Add incomplete, provisional, unknown-configuration and simulation rows in a disposable test archive and confirm none become confirmed contractual exceedances.
12. Disconnect/reconnect the Home Assistant frontend and reload the integration. Confirm there is one refresh timer, one sidebar item, automatic retry after a temporary WebSocket error, and no per-second Recorder writes from the countdown.

## V0.4.1 hotfix acceptance

1. With at least eight schema-5 quarter rows, open Previous quarter and TODAY.
   Confirm both load and Home Assistant logs contain no `IndexError: No item
   with that key` from `dashboard.py`.
2. Test a genuinely empty day and confirm it is shown as empty/missing. Then
   temporarily make the archive unavailable and confirm a useful error with a
   Retry button appears instead of “No archived summary exists” or perpetual
   “Loading day…”. Restore access and retry.
3. Open Tariff Calendar for 18 October 2026 in English and Slovenian. Confirm
   the heading contains Sunday / nedelja. Scroll to 22:00, select it, and verify
   the scroll position and highlight stay in place while details update.
4. Repeat calendar selection on the 23-hour spring-forward and 25-hour
   autumn-fallback days. Verify repeated hours remain distinguishable by offset
   and fold and arrow-key navigation preserves focus.
5. On Overview, verify the live chart uses the same kW scale for import, export,
   smoothing and target with visible 1 kW support lines. Verify the separate
   energy-progress chart accumulates only imported kWh; export never lowers it.
6. Enable the temporary simulation threshold in setup/Options and verify the
   real dated B1–B5 schedule and confirmed archive statistics remain unchanged.
7. Upgrade from V0.4.0 and confirm the SQLite file still reports schema 5, all
   prior rows/configuration epochs remain byte-for-byte semantically unchanged,
   existing entity unique IDs remain stable and no historical recalculation is
   triggered.
8. During a quarter with complete 120-second coverage, confirm the solid blue
   historical-smoothed line stops at the forecast anchor and the dashed blue
   future assumption continues to the exact quarter boundary. Confirm the
   separately labeled projected final quarter average is not plotted as an
   instantaneous power value. Repeat with 15-, 30- and 55-second source update
   intervals and confirm the solid line reaches the same backend anchor.
9. Create a sensor gap longer than the stale limit and restart HA mid-quarter.
   Confirm measured power paths remain broken across the gap. The energy chart
   must show the authoritative current imported-kWh point and explain why its
   preceding trajectory is unavailable instead of distributing prior energy.
10. Configure 3.50 kW contracted power, a 0.20 kW safety margin and a 2.50 kW
    simulation threshold. Confirm both charts separately identify 3.50 kW as
    the distributor limit, 3.30 kW as its safety reference, 2.50 kW as the
    simulation threshold and 2.30 kW as the target actually used by the engine.
11. With 0.30 kWh imported and a 2.80 kW smoothed final-demand forecast, verify
    the dashed energy projection begins at exactly 0.30 kWh and ends at 0.70
    kWh. It must never fall when the source exports.
12. Enable simulation and confirm its purple threshold is explicitly labeled
    SIMULATION and never replaces or masquerades as a confirmed distributor
    line. Disable the assignment/provisional rule and confirm no contractual
    line is invented.
13. Repeat on narrow mobile, tablet and desktop layouts in light/dark themes;
    axes, kW/kWh units, time endpoints, wrapping legends and forecast lines must
    remain readable, reference labels must not overlap and the 1 kW
    positive/negative grid must remain symmetric.
14. Inject or capture a diagnostic forecast whose projected final energy is
    lower than imported energy already accumulated. Confirm neither chart nor
    metric presents that projection; an explanatory unavailable reason appears.
15. Exercise normal updates, a stale gap, sufficient recovery coverage, a fixed
    quarter rollover and a mid-quarter restart. Confirm no smoothing line bridges
    unsupported time and a new quarter starts from its own backend total.
16. In Android Home Assistant, test exact content widths of 320, 360, 390 and
    768 pixels. Each live chart must scroll horizontally inside its own card at
    narrow widths; SVG text and strokes must retain readable size and the whole
    dashboard must not acquire a horizontal scrollbar.
17. Select quarters around the 25 October 2026 rollback. Confirm the two local
    02:xx intervals show different `GMT+2` and `GMT+1` labels (or CEST/CET),
    including at chart endpoints.
18. During the first 120 seconds after a quarter rollover, verify that inherited
    backend smoothing is shown as an outlined forecast anchor and dashed future
    assumption when the current-quarter trace cannot support a solid smoothing
    trajectory. The UI must not connect that anchor to unsupported history.
19. Scroll the live power and cumulative energy charts to different horizontal
    positions. Leave keyboard focus on each chart in turn and wait through at
    least two automatic 10-second refreshes. Confirm both positions remain
    independent and the focused chart remains focused without page jumping.
20. Immediately after rollover, while the live trace is empty, horizontally
    scroll the cumulative energy chart and wait for refresh. Confirm it remains
    styled and scrollable. Switching meters must reset both chart positions;
    ordinary refreshes within the same meter and quarter must not.
