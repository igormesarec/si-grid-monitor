# SI Grid Monitor V1.0.3 Localization Release-Candidate Manual Test Plan

## Installation and dashboard language

1. On desktop and Android, confirm **Language / Jezik** is the first setup step,
   with English selected by default and Slovenščina available.
2. Complete one English and one Slovenian installation. Confirm the choice sets
   the initial language of all eight dashboard pages, including Contracts.
3. Confirm native ConfigFlow/OptionsFlow chrome still follows the Home Assistant
   frontend locale; the integration preference does not change HA globally.
4. Test the header EN/SL control at 320, 360, 390, 430, 768 px and desktop in
   light/dark themes, larger text, keyboard, touch and screen-reader navigation.
5. Select Slovenian, switch meters and tabs, reload and reopen the dashboard;
   Slovenian must remain selected. Switch back to English and repeat.
6. Change **Preferred language** in Options and verify contracts, archive rows,
   source epochs, entry ID and entity unique IDs remain unchanged.
7. Upgrade entries with no language, `en`, and `sl`; verify English defaulting
   only for the first case and preservation for the other two.

Automated tests cover flow order, migration, Options preservation, WebSocket
metadata and browser-state behavior. Companion App rendering and native dialog
presentation still require real Home Assistant validation.

## V1.0.3 publishing and storage acceptance

1. Before upgrading, record Recorder and InfluxDB sizes plus state-change counts
   for both meters. Keep current temporary exclusions until validation completes.
2. Upgrade without removing entries. Confirm entity IDs, unique IDs, archive row
   counts, schema 7, contracts, audits and source epochs remain unchanged.
3. With **Storage Optimized**, run both meters for at least 24 hours through
   import, zero, export, quarter/tariff transitions, source stale/recovery and a
   safe simulated warning. Confirm internal quarter energy remains accurate while
   stable entities do not produce one-second Home Assistant history.
4. In Overview → **Data Publishing & Storage**, compare hour/day/week scopes for
   each meter and both combined. Confirm timer ticks remain near 60/minute,
   publishing evaluations can be higher when source reports arrive, routine
   publications are much lower, and critical transitions are prompt. During the
   first hour the annual estimate must say it is warming up; a truncated event
   window must be visibly flagged.
5. Switch to Automation Priority for one test meter. Verify the warning and
   increased event rate, then use Restore Recommended Defaults. Confirm no new
   contract audit/configuration epoch, no entity recreation and no archive change.
6. Configure a harmless numeric-state automation against a selected Custom fast
   entity. Verify its documented cadence. Confirm arbitrary thresholds on other
   coalesced values are not described as one-second fresh.
7. Inspect Recorder attributes and InfluxDB writes. Coverage/source-age timing
   details must not recreate a one-second stream. No SI Grid Monitor-specific
   exclusions should be required after independent validation.
8. Measure physical growth for the real 60-day Recorder and unlimited-retention
   InfluxDB installation. CI's real-entity workload projects about 510.5 MB/year
   for two meters, but its InfluxDB component is an unverified allowance—not a
   physical measurement. Follow the non-destructive commands in
   `docs/data-publishing-and-storage.md`; record event counts, filesystem growth,
   series cardinality and unrelated writers.
9. Only after success, remove temporary exclusions deliberately. Use the
   backup-first manual guide for old data; confirm V1.0.3 itself performs no
   purge, VACUUM, retention change or InfluxDB deletion.

## V1.0.3 mobile Contracts and calendar acceptance

1. At 320/360/390/430/768/1280 px, English/Slovenian and light/dark themes,
   verify separate contract status cards, readable timeline periods and no
   joined label/value text or whole-page overflow.
2. On phones confirm archived target evidence and audit events use readable
   cards. Expand technical details; full IDs/JSON must not force page overflow.
   On desktop confirm full tables and pagination remain available.
3. Select Sunday 25 October 2026. Confirm 25 hour tiles and two distinct 02:00
   entries with UTC+2/UTC+1. Select the second occurrence, scroll deliberately
   and refresh: the same-date position/selection remains. Change date: the
   timeline realigns to the selected/default hour.
4. Verify the spring DST day contains 23 hours/92 quarters and no fabricated
   archived target. `Not archived`, historical inference and current
   configuration must remain distinct.

## V1.0.1 native OptionsFlow hotfix

1. Configure two independent A/B/C meters with different friendly names and
   dated B1–B5 assignments. Test once on desktop and once in the Android
   Companion App.
2. Confirm the single **SI Grid Monitor** sidebar item still opens the dashboard,
   shows all eight tabs and switches between the two meters without mixed data.
3. In **Settings > Devices & services > SI Grid Monitor**, open **Configure** for
   each meter. It must open the native SI Grid Monitor settings menu, not the
   sidebar dashboard.
4. Confirm that menu contains **Calculation and meter settings**, **Manage
   contracted-power assignments**, **Add contracted-power assignment**, and
   **Archive retention or permanent deletion**.
5. Open **Manage contracted-power assignments**, edit an existing assignment
   from `2026-01-01…2026-12-31` to end on `2026-06-30`, then add another dated
   assignment from `2026-07-01…2026-12-31`. Confirm overlapping periods are
   rejected and the two valid periods remain editable after reload.
6. Complete quarters recorded before the edit must retain their original
   contracted limits, measurements, tariff provenance and source epoch. New
   quarters must use only the assignment effective for their local date.
7. Reload each meter and restart Home Assistant. Confirm Configure still opens
   OptionsFlow and the shared dashboard remains available without duplicate
   sidebar entries.

These Android and desktop checks require a real Home Assistant installation;
automated tests validate registration arguments and OptionsFlow behavior but do
not claim Companion App acceptance.

## V1.0 mandatory acceptance

1. Back up `.storage/si_grid_monitor_*.db` and record config-entry IDs, entity
   unique IDs, archive row counts, source epochs, checkpoints and B1–B5 targets
   before upgrading a copied V0.9.6 installation.
2. Upgrade a Mode A meter. Confirm the same entry/entities/archive load, signed
   polarity is unchanged, import is positive and export is negative.
3. Upgrade Mode B. Stagger import/export sensor reports, make one unavailable,
   then recover it. Confirm no export is subtracted from imported quarter energy
   and uncertain samples create gaps instead of fabricated evidence.
4. Upgrade Mode C. Confirm export remains **Unknown**, current/sustained advice
   recovers after sufficient fresh coverage, and no solar/export surplus is
   invented.
5. Upgrade a legacy Mode D entry. Confirm it does not load a measurement runtime,
   exposes no derived-power entities or counter charts, and shows the bilingual
   notice that its archive is preserved. Verify another A/B/C entry still loads.
6. Use **Reconfigure** on the copied Mode D entry and select a W/kW Mode A, B or
   C source. Confirm the entry ID/database filename remain unchanged, old rows
   retain counter-derived provenance and new data begins a distinct source epoch.
   Confirm the config-entry unique ID now identifies the new live source. Attempt
   the same source already owned by another meter and confirm reconfiguration is
   rejected without changing either entry or archive.
7. Check all eight tabs on desktop and Android. Distinguish valid, incomplete,
   unavailable, missing after monitoring began, pre-monitoring, live and upcoming
   intervals. Pre-monitoring must not increase missing counts.
8. Confirm all displayed kW/kWh measurements use three decimals, percentages use
   their percentage format, counts remain integers and unknown values do not
   appear as `0.000`.
9. Test 23-, 24- and 25-hour Europe/Ljubljana days, dated target transitions,
   provisional tariff disabled/enabled, simulation isolation and confirmed
   exceedance eligibility.
10. Test multiple meters, sticky selector persistence/fallback, reload, restart,
    HACS update and WebSocket recovery without cross-meter data.
11. Remove a copied entry without arming deletion and confirm its archive remains.
    Test permanent deletion only on a disposable meter with fresh exact
    confirmation and backup; no other database may change.
12. With a disabled legacy Mode D entry, run reload, restart, a failed setup retry
    and normal removal. Confirm no missing-runtime exception occurs, another A/B/C
    meter remains active, and the Mode D schema-6 database, checkpoint, epochs and
    rows remain unchanged after default removal.

Passing CI does not replace these tests. Do not tag or publish stable V1.0 until
the real Home Assistant and Android checks above are recorded.

---

## Historical V0.9.6 experimental Mode D plan (not active V1.0 functionality)

## V0.9.6 Mode D live-measurement hotfix acceptance

1. Update an existing V0.9.5 installation through HACS without removing its
   config entry. Restart Home Assistant and refresh/reopen the Companion App.
   Confirm manifest and versioned dashboard assets report `0.9.6`; schema 6,
   archive row counts, entry IDs and entity unique IDs remain unchanged.
2. Configure the counter used in the reported Android case. Record its energy
   resolution and update cadence. Confirm a first reading establishes a baseline
   and does not create a power value or energy.
3. Send rapid unchanged reports, then one quantized energy step inside the
   default 30-second minimum window. Confirm the UI says it is accumulating
   counter evidence and never displays a trusted 402.06 kW-style spike. After a
   later report reaches 30 seconds, verify the derived value is labelled
   **interval average**, has the correct start/end timestamps, and preserves the
   exact counter delta in quarter energy.
4. Set a realistic meter-specific plausibility ceiling. On a disposable copied
   counter, introduce a larger discontinuity above that ceiling. Confirm it is
   rejected, visibly diagnosed, cannot create a confirmed exceedance, and leaves
   the affected coverage incomplete. The next valid baseline/interval must
   recover without repeating or redistributing the rejected delta.
5. Verify the Overview power chart draws accepted counter intervals as separate
   horizontal evidenced segments and leaves gaps visible. It must not connect
   them into an instantaneous trace. Confirm the cumulative-energy chart ends at
   the engine's authoritative imported kWh and never decreases during export.
6. Confirm Mode D shows instantaneous power, instant projection, smoothed
   projection and sustained advice as unsupported—not stale. Pause counter
   reports beyond the observation timeout and verify the separate counter-report
   availability diagnostic becomes unavailable without inventing a sample.
7. Test an import-only `total_increasing` counter and a bidirectional net `total`
   counter in both directions. Confirm the wizard rejects `total_increasing` for
   bidirectional net behavior and explains the configured import direction and
   reset ambiguity.
8. Repeat baseline, fast reports, zero changes, reset, unavailable/recovery,
   restart and quarter-boundary tests in English and Slovenian on Android and
   desktop. Verify Modes A/B/C are unchanged and two meter archives remain
   isolated.
9. Open Options for a Mode A meter and confirm counter minimum-observation and
   plausibility fields are absent. Open Options for Mode D, change both fields,
   reload the integration, and confirm Overview diagnostics and converter
   behavior use the saved values.
10. Confirm dashboard and Home Assistant kW/kWh sensor values display three
    decimal places while percentages retain two decimals, counts remain whole,
    adaptive graph ticks remain readable and unavailable values show `Unknown`
    or unavailable—not `0.000`.
11. With a counter reporting every 30 seconds at timestamps not aligned to
    `:00/:15/:30/:45`, run through several boundaries. Compare total counter
    delta with archived plus current-quarter energy (they must reconcile), and
    confirm every boundary-straddled quarter is incomplete rather than a
    confirmed contractual interval.
12. On TODAY at Android widths, confirm initial selection is the live quarter.
    Select an older quarter, wait through multiple 10-second refreshes, and
    confirm it remains selected. Tap **Current / Live** and confirm immediate
    return to the current interval without horizontal page overflow.

## V0.9.5 four-source-mode acceptance

1. Start a clean setup in English and Slovenian. Confirm the wizard recommends
   signed live grid power when a suitable W/kW sensor exists, explains the three
   alternatives, rejects incompatible units/state classes, previews normalized
   direction and identifies interval-derived counter power. Submit untouched
   defaults once in each language.
2. Upgrade an existing signed SolarEdge entry. Confirm its entry ID, entity unique
   IDs, polarity, schema-6 row count and historical source epochs are unchanged.
3. Create a separate-power entry with nonnegative W/kW import and export sensors.
   Exercise asynchronous updates, unavailable states and an intentionally
   conflicting simultaneous reading; invalid input must not create energy.
4. Create an import-only entry. Confirm import demand works while export power,
   exported quarter energy and export-dependent surplus claims are unavailable.
5. Create counter mode with a Wh or kWh imported-energy total and choose
   **Import-only cumulative counter**. Confirm the derived import-power entity
   appears without YAML/helper setup and export stays unknown. Reload and restart
   twice; no duplicate entity may appear.
6. Create a copied/test **bidirectional net-energy counter**. Verify the default
   increase = import polarity, reverse it, and exercise both positive and negative
   deltas. Confirm neither direction is treated as a reset, while the dashboard
   clearly marks contractual import evidence unconfirmed because reversals may be
   hidden between readings.
7. Choose **Separate cumulative import/export counters** in another entry. Update
   import then export, reverse the order, and use different reporting intervals.
   Confirm each delta is processed once, no export delta is lost, and only shared
   evidenced spans are combined. Then omit the export counter and confirm export
   remains unknown.
8. Reset a copied/test monotonic counter, pause updates across a quarter boundary, restore
   it, and temporarily make it unavailable. Confirm a new baseline, incomplete
   quality where allocation is unsupported, and no false confirmed exceedance.
9. Rename/remove a test source, reload, restore it and reload again. Confirm clear
   unavailable diagnostics, safe recovery and no deletion of unrelated helpers.
10. Repeat with two meters and confirm generated entity IDs and archive namespaces
   stay isolated.
11. Give both entries long, distinct friendly names. On every dashboard tab verify
   the active friendly name and selector remain readable and reachable while
   scrolling on Android and desktop without covering content.
12. Select the second meter, reload/reopen the dashboard and confirm it is restored
    where browser storage is allowed. Remove or unload it and confirm the panel
    selects another available meter with a visible notice.
13. Switch meters with requests pending on OVERVIEW, TODAY, PERIOD, BLOCKS,
    EXCEEDANCES, HISTORY and TARIFF CALENDAR. No chart, statistic, detail or archive
    row from the previous entry may appear. Confirm there is still one shared
    SI Grid Monitor sidebar item.
14. Remove a disposable meter without changing its archive-removal Option. Confirm
    the entry disappears but its exact schema-6 database remains. Re-create a
    separate entry and confirm it does not silently attach the preserved archive.
15. For another disposable meter, choose permanent deletion in Options, request a
    backup, enter the exact `DELETE <friendly name>` confirmation, then remove the
    entry. Confirm pending writes finish, its database/WAL/SHM files disappear,
    the backup reopens, and every other meter/database remains unchanged. Repeat a
    restart, reload and HACS update without removal; none may delete an archive.
16. Arm deletion on a disposable meter, wait more than 10 minutes, and then use
    native Home Assistant removal. Confirm the expired authorization retains the
    database. Reconfigure and reconfirm before deliberately deleting it.
17. In HISTORY compare a signed-power quarter, a bidirectional-net counter quarter,
    and an import-only quarter. Confirm export is labelled directly measured,
    inferred from net, and unknown respectively; unknown must not appear as 0 kWh.
18. On a copied net counter, verify an ordinary negative delta remains reverse
    flow, an explicit `last_reset` change is rejected, and an implausibly large
    discontinuity becomes unavailable until a fresh baseline is established.
19. With separate cumulative counters, hold import updates active while making
    export unavailable for part of one quarter, then recover export. Confirm the
    quarter keeps valid imported energy and contractual import demand, labels the
    observed export subtotal as partial with unknown intervals, and the following
    fully evidenced zero-export quarter is labelled measured zero. Repeat across
    an integration reload during the partially known quarter.

## V0.8 HISTORY, reconstruction and platform acceptance

1. Back up Home Assistant. Record the pre-update schema-5 row count, database
   size, oldest/newest quarter, config-entry ID and entity unique IDs.
2. Update through HACS, restart, and hard-refresh desktop and Android WebViews.
   Confirm versioned `0.9.6` dashboard modules load and no entry reconfiguration
   is requested. Verify schema 6 and the exact same historical quarter count.
3. Open HISTORY and test day/week/month/year/custom ranges, B1–B5, quality and
   exceedance filters, sorting and pagination. A valid measured zero must remain
   distinct from a missing quarter. Follow a row into exact-quarter details.
4. Inspect 29 March and 25 October 2026. Confirm 92/100 quarters and distinguish
   both repeated 02:00 hours by UTC identity/offset/fold.
5. On a copy of the production system, choose a small range with known detailed
   Recorder states and run Audit only. Confirm no archive row or row count changes.
   Verify dates before the first known source/sign epoch are reported uncertain.
6. Review candidates, deliberately confirm reconstruction, and verify a backup
   metadata entry exists before changed rows. Re-run the audit: equal/stronger
   rows must be skipped. Interrupt one test job and verify restart leaves a valid
   database, preserved backup and retryable audit.
7. Simulate Recorder unavailable, SQLite locked/read-only and full storage on a
   disposable instance. Live monitoring must continue where safe; errors must be
   explicit and no trusted row may be downgraded.
8. Change Home Assistant between English and Slovenian while HISTORY has filters
   and a selected meter. Text should change without losing selection or showing
   data from another meter. Review every tab, warning, error, legend and control.
9. Verify Tariff Calendar reports 2026/2027 official and 2028–2030 provisional.
   With provisional policy disabled, future contractual advice stays unavailable;
   enabling it must still label results provisional, never confirmed.
10. Build the Pages preview artifact and inspect mobile/desktop navigation and
    links. Do not enable repository Pages deployment without owner approval.

The Recorder audit uses detailed timestamped states only. It must never claim
that long-term hourly statistics can reconstruct import/export quarters.

## V0.8.2 HISTORY missing-interval acceptance

1. Open HISTORY for today during a quarter. Confirm **Missing completed
   intervals** excludes the current interval and all later intervals;
   **Future / uncompleted intervals** shows them separately.
2. Repeat immediately before and after a `:00`, `:15`, `:30` or `:45`
   boundary. Only the interval whose end boundary has passed may become an
   expected completed interval.
3. Select a fully past day with a known archive gap. Confirm the absent
   completed interval is missing, while archived incomplete and unavailable
   records appear in their own metrics and are not counted as missing.
4. Select a future day. It must report zero completed expected and zero missing
   intervals; all local-day slots are future/uncompleted.
5. Inspect 29 March and 25 October 2026. Confirm totals of 92 and 100 local
   quarters respectively, with missing calculated only among completed slots.
6. Apply tariff, quality, exceedance or source-epoch filters. Confirm the
   range-wide completeness metrics remain visibly separate from the filtered
   row count, and missing remains unclassified when a row-only filter is active.

These steps require the actual Home Assistant clock, timezone and live archive;
automated tests cover the same boundary calculations with deterministic times.

## V0.8.1 Android and narrow-screen HISTORY acceptance

Automated Playwright layout tests now measure the real rendered axis/bar origin,
width, tick/grid positions, proportional bar length and unclipped partial status
at 320/360/390/430/768/1280 px in light/dark themes. They also exercise desktop
chart scrolling, mobile keyboard card expansion and enlarged text. These run
against fixtures in a desktop browser; Android Companion App acceptance remains
pending. Run locally with `npm install`, `npx playwright install chromium` and
`npm run test:layout`.

1. In the Android Companion App, test HISTORY at effective widths 320, 360, 390
   and 430 px; also test a 768 px tablet and desktop. Repeat with light/dark
   themes, browser zoom and enlarged accessibility text.
2. Confirm the product heading and active meter stack vertically on phones and
   that a long meter/entity title wraps without collision or whole-page
   horizontal scrolling.
3. Confirm date, block, quality, exceedance and source-epoch filters form a
   single readable column on phones. Every label must remain beside its control;
   Apply and the newest-first notice must not overlap another field.
4. Select B1-B5 individually. Verify the demand chart fits the card without a
   mandatory 760 px viewport, preserves the red valid-demand bar, gold historical
   target, practical 1 kW grid, newest-first order and explicit partial states.
   A genuine peak must appear only for a row that actually archives peak evidence.
5. Select All blocks. Verify a paginated chronological record list is visible
   with B1-B5 chips. On phones, expand cards and verify timestamp, block, demand,
   target, exceedance, import/export, quality/coverage, source epoch and tariff
   rule without repeated horizontal scrolling.
6. Exercise touch selection, keyboard focus, vertical scrolling and pagination.
   Confirm the exact UTC quarter opens and no archived values, epochs or targets
   change. These visual checks require a real Home Assistant/Android instance;
   the automated suite validates markup, breakpoints, chart semantics and order.
7. For All blocks, confirm the default date order is newest first, then select
   date, energy, demand, utilization and quality in both directions. Chart/list
   and card/table rows must follow the same server page. Select B1-B5 and confirm
   those reports remain newest first even after an alternative All-block sort.
8. Inspect a partial quarter with enlarged text. Its complete observation/status
   sentence must wrap beside the bar and remain readable. The bar must not plot
   partial imported energy as valid quarter demand. Compare several kW ticks
   with their vertical grid lines before and after desktop chart scrolling.

Use a disposable or backed-up Home Assistant instance. Never infer physical
connection capacity from CAN ADD values.

## V0.6 PERIOD, BLOCKS and EXCEEDANCES acceptance

Use the existing `sensor.solaredge_m1_ac_power` entry. Before updating, record
the schema-5 archive path, row count, oldest/newest quarter and current entity
IDs. After updating through HACS, restart Home Assistant and refresh the browser
or Android WebView so the `0.6.0` dashboard assets replace V0.4.2.

1. Confirm OVERVIEW, TODAY and TARIFF CALENDAR retain their V0.4.2 behavior and
   that the existing SQLite row count never decreases.
2. Open PERIOD and exercise Hour, Day, ISO Week, Month, Year and a Custom range.
   Verify Previous/Next/current controls and B1-B5 filtering stay selected over
   automatic refreshes. Older unrecorded dates must say unavailable/missing,
   never show zero consumption.
3. For a completed day, reconcile PERIOD totals, valid/incomplete/missing counts,
   maximum quarter demand and confirmed exceedances with TODAY. Repeat across the
   29 March 2026 spring transition (92 quarters) and 25 October 2026 rollback
   (100 quarters); repeated times must remain distinguishable by UTC offset.
4. Drill Year → Month → Day → quarter. Confirm the quarter detail retains its
   original target, block, source/configuration epoch, rule version, quality and
   provenance and does not invent a detailed trace.
5. Open BLOCKS and confirm B1-B5 are always present. Reconcile their summed valid
   energy and quarter counts with PERIOD. Where assignments changed, verify the
   stored historical target list/range rather than today's target is shown.
6. Select each block and inspect its peak timestamp and high-demand quarters;
   follow the Exceedances action and confirm the period and block filter persist.
7. On EXCEEDANCES, test date/demand/excess/excess-percentage sorting, both
   directions and pagination. Every confirmed exceeded 15-minute quarter must be
   one row. In a controlled fixture, three consecutive exceeded quarters must be
   three rows and 45 minutes, not one event.
8. Verify simulation, provisional, incomplete and unknown-contract rows never
   enter confirmed exceedance counts. A zero-result page must warn that missing
   or incomplete intervals are not proof of no exceedance.
9. Switch between two meters while requests are in flight. Confirm no totals,
   filters, quarter detail or delayed response crosses archive namespaces.
10. Check desktop and Android widths in light/dark themes: horizontally scrollable
    navigation and dense charts/tables must not overflow the whole panel; keyboard
    focus and chart scroll should remain stable over refreshes.
11. Compare two fully measured equal-length periods and confirm changes are
    shown with both coverage summaries. Then choose a period whose predecessor
    has missing/incomplete quarters and confirm comparison is unavailable rather
    than extrapolated. Repeat across February/March and a 23/25-hour DST day;
    unequal quarter counts must be explicitly non-comparable.
12. Activate monthly, daily, hourly and quarter bins. Confirm drill-down follows
    the displayed resolution. On the October rollback, the repeated 02:00 hours
    must open distinct UTC intervals. A missing bin must say no measured value is
    available, while a valid 0.00 kWh bin is identified as measured zero.
13. On a PERIOD chart containing alternating missing and measured bins, verify
    left-to-right order remains chronological across local midnight. On the
    October rollback, repeat with either or both 02:00 folds measured and confirm
    CEST precedes CET without chart reordering.

These steps require a real Home Assistant/browser installation and are not
claimed complete by repository automation.

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

## V0.4.2 real-world dashboard acceptance

Use `sensor.solaredge_m1_ac_power`. Update through HACS, restart Home Assistant,
then refresh the browser or fully reopen the Android companion app. Do not
delete the integration entry or its SQLite file.

1. With continuous coverage, confirm the solid red imported-energy curve ends
   exactly at Used so far. After an early or restart gap followed by fresh data,
   confirm only the supported recent red suffix appears. Stale data must show a
   point and explanation, never a line across the gap.
2. Confirm the cumulative projection and legend swatch are identically dashed
   purple. Check all reference patterns in light/dark themes; coincident
   distributor and operational values must use one combined reference.
3. During import only, confirm the live power axis starts at 0 kW and no green
   zero-export trace appears. Genuine export must expand the axis below zero;
   import above contract must expand upward without clipping.
4. With a 3.90 kW target, confirm the quarter-energy reference is `0.975 kWh`.
5. Confirm Current-quarter forecast status is distinct from Sustained forecast
   quality, and stale or insufficient history has a readable reason/source age.
6. On Today, exercise Previous/Next, dropdown, broad SVG slots, touch and
   keyboard. Archived rows must load SQLite details; live stays live; upcoming
   says Not measured yet; missing never becomes zero.
7. Verify 92, 96 and 100 choices on spring-DST, normal and autumn-DST days.
   Repeated 02:xx intervals must differ by GMT offset (CET/CEST).
8. Scroll Today and Tariff Calendar to a late item and wait through multiple
   10-second refreshes. Selection, scroll and keyboard focus must remain stable.
9. Confirm valid completed energy, separately observed incomplete energy, live
   energy, valid-demand average and contributing counts remain separate.
10. Confirm the electrical-capacity warning remains prominent near CAN ADD.
11. Restart/reload and verify schema-5 rows, configuration epochs, entity IDs
    and dated contracts survived unchanged.

Automated model/DOM tests cover state transitions and geometry. Android theme
rendering and live SolarEdge cadence still require the real-instance checks.

## V0.8 archive-safety and localization acceptance

1. Before upgrading a copy of a schema-5 archive, stop Home Assistant and keep
   the database plus its `-wal` and `-shm` files together. Start V0.8 and verify
   schema 6 is reported while quarter rows, source epochs, checkpoints, dated
   targets, tariff versions and provenance remain unchanged.
2. To recognize a database touched by the earlier development migration, check
   `PRAGMA user_version`. Version 5 accompanied by one or more of
   `reconstruction_jobs`, `quarter_revisions` or `archive_backups` is a partial
   development migration. Preserve a copy and restart with the corrected build;
   it completes expected table shapes idempotently. If Home Assistant reports
   an incompatible partial-V6 table, do not delete `quarters`, `source_epochs`
   or `checkpoints`; restore the preserved database or request a reviewed repair.
3. On a disposable archive, interrupt startup during migration (locked/full
   storage is sufficient) and verify startup fails without changing the schema
   version or historical rows. Restore storage and verify the next startup
   completes normally.
4. Run Recorder AUDIT ONLY, then allow a live quarter update before pressing
   Apply. Verify the stale candidate is rejected, the newer live evidence stays
   intact, and no revision row claims a change occurred.
5. Interrupt reconstruction while a revision is being recorded. Verify that
   the matching quarter remains at its original quality/coverage and no orphan
   revision exists. Earlier successfully committed quarters may remain applied;
   each quarter is intentionally its own atomic unit and the job reports partial
   failure.
6. In HISTORY, apply block, quality, exceedance and source-configuration-epoch
   filters. Verify the header labels totals as the overall selected date range,
   while the table/pagination count is explicitly the filtered result. Missing
   intervals must not acquire a block, quality or source epoch.
7. Switch Home Assistant between English and Slovenian on every dashboard page.
   Verify navigation, parameterized pagination, Recorder audit/reconstruction
   messages, warnings, dialogs, accessibility labels and connection errors
   switch language without changing the active meter, date, quarter or filter.
8. Create dated contracted-power assignments for 2026 and 2027 with different
   B1-B5 values. Audit a 2027 Recorder quarter, then change the applicable 2027
   assignment before Apply. Verify the stale plan is rejected. Repeat without
   changing the assignment and verify the exact target for that quarter's block
   and local date is retained; a target from another block or 2026 must not pass.
9. In HISTORY, verify the four exceedance choices independently: All, Confirmed
   Yes, Confirmed No and Unconfirmed. Confirmed No must not include SQL NULL
   rows, and Unconfirmed must not present those rows as known non-exceedances.
10. Select each of B1-B5 over a populated date range. Verify the chronological
    chart and detailed table show the same bounded page newest-to-oldest, use
    original historical targets, and open the exact UTC quarter. The peak-power
    column must say that no peak is archived unless genuine evidence exists; it
    must never copy the 15-minute average into the peak column.
11. On BLOCKS, confirm the demand chart uses 1 kW vertical references at normal
    household ranges and the energy chart uses readable adaptive kWh references.
    Verify red maximum and light-blue average legends match their series.
12. On PERIOD, check Day labels as Ljubljana `HH:mm`, longer views as appropriate
    local dates, and the 25 October 2026 rollback. The two 02:00 labels must show
    distinct GMT offsets. Verify energy and demand have separate visual legends,
    a one-quarter demand bin draws one red bar, and aggregated bins draw red
    maximum plus light-blue average with the gold historical-limit reference.
13. In a HISTORY block report, compare four quarters: a valid measured zero, an
    incomplete row with partial imported energy, an unavailable measurement,
    and a missing archive row. Only the valid zero may show a contractual-demand
    bar/value (`0.00 kW`). Confirm the adjacent label, table value, tooltip or
    screen-reader description uses the same state and never exposes a stored
    partial value as confirmed demand.
14. Request the same populated B1-B5 report after previously selecting demand,
    energy, quality, ascending, and descending sorts. Confirm every block report
    remains newest UTC quarter first across page boundaries and that the chart
    and table have identical row order.
15. In BLOCKS, confirm maximum demand is red, average demand is light blue and
    historical targets are gold dashed. B1-B5 identity chips may retain their
    block colors, but those colors must not replace or contradict measurement
    series colors. Check both light and dark themes.
16. On a long HISTORY report, verify the bars begin at the zero tick, vertical
    reference lines align with their axis numbers, and chart/table remain inside
    the panel. Repeat at Android widths (320, 360 and 390 px), at 768 px, in light
    and dark themes, and with browser/text scaling enabled. Check that labels do
    not overlap and horizontal/vertical scrolling remains usable.
17. Visit all eight tabs in English and Slovenian. Check metric descriptions,
    warnings, errors, chart legends, table headings, pagination, controls and
    accessibility labels. Units and stored technical values (quality/provenance
    codes, entity IDs and UTC identities) must remain unchanged.

## V0.9 clean Home Assistant beta gate

The authoritative beta classification, safe-upgrade and rollback instructions
are in `V0.9_BETA_ACCEPTANCE.md`. Complete its clean-HA procedure on a disposable
instance before recommending a beta release. Preserve evidence for:

1. Fresh HACS installation and the complete Mode A setup wizard.
2. V0.8-to-V0.9 upgrade with unchanged entry IDs, entity unique IDs, SQLite row
   counts, source epochs, dated targets and tariff provenance.
3. Two simultaneous meters, repeated reloads/restarts and a restart immediately
   after a fixed-quarter boundary.
4. HACS code removal and reinstall with the external archive retained. Do not
   treat this as a factory reset; V0.9 has no destructive reset workflow.
5. WebSocket disconnect/recovery, a temporary SQLite lock/read-only failure and
   Recorder unavailability without fabricated measurements or lost quarters.
6. All eight dashboard pages in English and Slovenian at Android, tablet and
   desktop sizes, light/dark themes, keyboard and touch.
7. Live import/export, measured zero, stale/unavailable/recovery, 92/96/100-slot
   days and three consecutive exceeded quarters as three separate records.
8. During setup or reload, interrupt/cancel platform loading. Test a failure after
   the sensor platform loads and after the binary-sensor platform loads. Confirm
   there are no orphan entities, callbacks, listeners, runtime registry entries
   or stale `runtime_data`; retry without deleting the entry and confirm it loads.
9. Inject one listener-unsubscribe failure during reload on a disposable instance.
   Confirm logs retain the cleanup error while pending quarter writes, checkpoint
   saving and SQLite close still complete, and the preserved archive reopens.
10. Cancel unload separately while archive tasks are draining, while a checkpoint
    is being saved and while SQLite is closing. Cancellation must return to HA
    within the documented grace bound. If cleanup is still active, confirm the
    runtime remains registered; retry unload, reopen the schema-6 archive and
    compare quarter identities/counts to prove no committed row was lost or
    duplicated.
11. Immediately request setup/reload again while the prior same-entry shutdown is
    deliberately held open. Confirm setup defers with a clear diagnostic for no
    longer than the documented bound, does not replace `runtime_data` or create a
    second SQLite owner, then succeeds after cleanup completes. Repeat with two
    meters and confirm one entry's shutdown never blocks or replaces the other.

Automated tests do not satisfy this gate. Record the HA version, HACS version,
browser/app version, integration commit, source update cadence and database
before/after counts with the results.
# V1.0.2 contract-management acceptance

1. Back up `.storage/si_grid_monitor_<entry-id>.db`, upgrade from V1.0.1 and
   confirm schema 7 opens with every old quarter/epoch/checkpoint unchanged.
2. On Android 320/360/390/430 px and desktop, open all eight tabs; verify the
   Contracts timeline, tables, scrolling, meter selector, keyboard/touch access,
   light/dark themes and larger text.
3. From a 2026 full-year fixture, Schedule change on 25 October and confirm the
   preview/result is `01-01..10-24` plus `10-25..12-31`. Test a July-September
   change produces three segments. Confirm B1-B5 values use three decimals.
4. Leave Record date empty, save, reload and confirm it remains empty. Repeat
   with a valid date.
5. Confirm overlap errors identify the conflicting range. Create an intentional
   gap and verify the Contracts warning and one Repairs issue; fill it and verify
   automatic clearing. Test 30-day, 7-day and first-uncovered-day behavior.
6. With no current assignment, verify Modes A/B/C still measure and archive while
   contractual forecasts/exceedance confirmation remain unavailable.
7. Select 25 October 2026 in Tariff Calendar. Verify both 02:00 hours have unique
   UTC identities and show separate As recorded and Current configuration values.
8. Configure two meters and verify contract API/timeline/audit/Repairs isolation.
9. Confirm management links open Devices & services for SI Grid Monitor and the
   selected meter can be configured; non-admin viewers cannot modify contracts.
10. Confirm `SPECIFICATION.md` and archived quarter rows are byte/field unchanged.
11. Open the same meter's OptionsFlow in two sessions. Create previews in both,
    save the second session, then confirm the first. The first must report a stale
    preview, save nothing and create no misleading audit event.
12. Create more than 200 audit events in a disposable archive and verify Previous
    and Next expose every bounded page. Confirm historical configuration snapshots,
    archived-quarter evidence and user-edit events remain separate.
13. On a past Calendar date test an archived target, an archived null target, an
    incomplete quarter and a missing quarter. Only the exact non-null archived
    target may be labelled As recorded; epoch inference and current configuration
    must remain separate. Repeat across both 02:00 hours on 25 October 2026.
14. On Android and desktop confirm Contracts shows one **Open integration
    settings** action, names the selected meter, and does not imply three distinct
    actions when all navigation leads to the same supported settings page.
