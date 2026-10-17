# SI Grid Monitor
## MASTER PRODUCT SPECIFICATION V1.1

**Status:** V1 requirements baseline, audit-corrected 17 October 2026. This is the authoritative development document for the planned integration. Feature implementation is phased; do not confuse the specification with an existing working release.

**Project:** A meter-independent Home Assistant custom integration and professional, responsive dashboard for Slovenian grid consumption, export, aligned 15-minute grid-power demand, projected demand, household load headroom, tariff blocks, over-limit analysis and permanent 15-minute history.

**Delivery:** One GitHub repository, HACS-compatible Home Assistant integration, frontend components and energy-dashboard-style views, reliable historical archive, automated tests, user documentation, HACS project presentation and GitHub Pages website.

**Terminology:** The signed **grid connection** power is positive for electricity *imported* from the grid, negative for electricity *exported* to the grid. A negative reading is **not** total PV production; a positive reading is **not** necessarily total household consumption. All examples must use this convention, regardless of original meter polarity.

### 1. Scope, defaults and non-goals

- Home Assistant custom integration installed from HACS, configured fully using the UI; no hand-written YAML or additional database integration required. No vendor lock-in, no internet requirement during normal monitoring.
- Designed for Slovenian 15-minute network demand periods and tariff time blocks 1 through 5. Historical tariff rules must be tied to their effective dates.
- **Defaults:** archive retention **Forever**; safety margin **0.00 kW**; forecast smoothing **30 seconds**; source and sign mode selected by user; example power target **4.80 kW** only if explicitly confirmed; targets can be shared across all blocks or edited separately.
- **Core views:** OVERVIEW | TODAY | PERIOD | BLOCKS | EXCEEDANCES | HISTORY. Settings remain in HA integration configuration. Show each tariff block in Today even when inactive that day.
- Exactly three successive over-limit quarters count as **three separate exceeded intervals**, never a combined single 45-minute exceedance.
- No CSV or Moj Elektro data import for V1. Initial backfill may inspect available Home Assistant history only. Do not describe meter-derived reconstructions as exact supplier-billing data without justification.
- Do not automatically control loads in V1. Expose HA entities and optional alerts so people can build their own automations. Do not claim that exceeding configured limits necessarily incurs a particular charge.
- No collection or transmission of household energy readings outside the local HA instance. Version/tariff-data checks are optional network operations and must not upload measurements.

### 2. Configurable source and capability detection

The setup flow must support the following modes and clearly state their resulting capabilities:

| Source mode | Required user mapping | Available features / limitations |
|---|---|---|
| A. One signed live grid-power entity | Select entity; W or kW; indicate whether positive means import or export | Full signed live view, rolling mean, quarter-hour integration, forecasts and load advice subject to sample quality |
| B. Separate live import/export power entities | Select import and export; units, both nonnegative | Full live view and import-only accounting; validate conflicting simultaneous values |
| C. Live import-only power entity | Select nonnegative import power; W/kW | Import demand/limits, conservative advice; **unknown export is not assumed to be zero solar production or known surplus** |
| D. Cumulative imported energy, optional exported energy | Choose each cumulative counter, Wh or kWh, total/total_increasing semantics | Accurate counter-derived energy where updates/time alignment permit; live instantaneous power and immediate forecasts may be unavailable or delayed |
| E. Already aligned completed 15-minute demand or energy | Select sensor, unit, confirm it represents completed fixed quarters; confirm timestamp convention | Import/archive/reporting only for supported aligned intervals; cannot infer live instant forecasts or net surplus |

- Support multiple distinct configuration entries/meters without mixing their archives (at least plan isolation; V1 must avoid accidental data overlap).
- Show live sample and a comprehension check: e.g. source `-2400 W`, selected 'negative means import' => normalized **+2.400 kW import**. Provide 'reverse sign' correction.
- Internally normalize all supported sources. Do not assume SolarEdge entity names. Validate units, update frequency, sensor class and timestamp, counter resets/rollover, entity changes, HA restarts, stale/unavailable/non-numeric readings.
- Track and expose source freshness and input mode. Fail safely: if necessary data is unavailable, mark dependent results unavailable rather than writing fake zeroes or fabricating forecasts.
- Do not use the instantaneous signed power mean alone to estimate *imported* energy if export/import reversals occur inside an aggregation window. Imported and exported energy must be accounted for separately.

### 3. Configuration and effective target history

- **Shared target mode:** one numeric kW value applied to B1, B2, B3, B4, B5, editable later.
- **Per-block mode:** five independently editable numeric kW targets, with clear labels and active-block highlighting. Input validation (nonnegative, sensible maximum, decimal precision) and optional use of actual contracted values.
- Optional **safety margin**, nonnegative kW, **default 0.00 kW**. Contracted target and operational target must be visually and semantically separate. Operational target = `max(0, contracted_target - safety_margin)`.
- Smoothing presets 30 seconds (default), 60 seconds and custom 5-120 seconds. Both instant and smoothed forecast sensors always available where live source supports them.
- Config flow and options flow allow changing source, polarity, targets, margin, smoothing and archive retention. Changes need a recorded effective timestamp. Historical completed quarters retain the target, block and rule version used then; editing current settings must not silently rewrite history.
- If source type changes, show a clear warning and use a distinct provenance marker instead of blending incompatible historical calculations.

### 4. Slovenian calendar, tariff rules and updates

- Determine season, applicable Slovenian workday/non-workday rules and block for each interval using **official, dated regulation**, including changes between 2026 and 2027. Five blocks exist across a calendar year; only a subset (at most three different blocks under published 2027 rules) appears on an individual day.
- Model legally applicable days off, not only Saturdays and Sundays. Verify national work-free holidays and exceptions against official sources.
- Store rules as schema-validated, versioned data (e.g. `tariffs/si_rules.json`), each with effective date range, source citation URL, approval/version stamp and test fixtures. Preserve older versions and assign quarters using the rules applicable at their timestamp. Never silently apply next year's unverified rules.
- **Update workflow:** include tariff rules in GitHub releases, HACS detects newer integration versions, a visible HA update/diagnostic informs the user when new data is available or calendar coverage is approaching expiry. If feasible add a separate online tariff-metadata check, with secure verification and user consent. No automatic web-scraping of legal rules into production without review. After an approved update, historical interpretations continue using their original version.
- Without current official rules, show a visible **calendar unknown/outdated** state and avoid presenting an unsupported block as certain. Offline operation uses last verified covered dates.
- Tariff **time blocks** and **contractual grid prices/bill penalties** are separate. V1 reports interval exceedances and energy, not an invented € fee. Dates and timezone must use Europe/Ljubljana with UTC timestamps and DST disambiguation.

### 5. Exact versus rolling periods, sampling and signs

**Two different 15-minute concepts must always exist:**

1. **Signed rolling last-15-minute average** of normalized grid power, for lifestyle/solar-surplus awareness. `+` = average import, `-` = average export. Also provide an import-only rolling mean if supported. It continuously slides with time.
2. **Fixed, aligned quarter-hour billing-style import average** for `HH:00-HH:15`, `HH:15-HH:30`, `HH:30-HH:45`, `HH:45-HH+1:00`, using **imported energy only**. This is the basis for tariff-target utilization and exceedance reporting. Also save signed net and exported energy separately to visualize surplus and lifestyle patterns.

- For time-varying normalized signed power `p(t)` in kW, imported energy for each valid quarter is `integral(max(p(t),0) dt)`; exported energy `integral(max(-p(t),0) dt)`. Net export never cancels imported energy for billing-demand purposes.
- `completed_quarter_import_demand_kw = import_kwh * 4`; `completed_quarter_signed_net_kw = (import_kwh - export_kwh) * 4` for a 15-minute interval.
- Input sensor updates might be irregular. Time-integrate known successive samples with an explicitly documented method (prefer a piecewise-constant sampled representation or justified counter delta). Record sample cadence and gaps; this is **sample-reconstructed**, not necessarily supplier-meter-exact. The 1-second screen refresh does not mean the meter produces a new measurement every second.
- Use source timestamps where reliable, avoid counting time when no supported signal exists, split transitions exactly at each quarter boundary and never assume a gap is a 0 W import. At a boundary finalize the previous interval and begin a new one exactly once.
- For cumulative counters, use validated deltas/interval boundaries, detect reset, rolls and stale updates. If precise distribution of a delta inside a quarter cannot be established, flag estimated/incomplete instead of reporting exact 15-minute peaks.
- Initial backfill: reconstruct available detailed HA state history with the same explicit sampling assumptions, mark provenance `ha_reconstructed`. If genuine aligned quarter data was already recorded, import it from that HA entity with its verified timestamps. Five-minute aggregated signed net means do **not** generally permit exact import/export recovery if signs changed; hourly means/min/max **cannot** reconstruct individual quarters. No CSV import.
- Completed quarter archive supports `quality = measured_aligned | counter_derived | reconstructed | incomplete | unavailable`, source identity, freshness/coverage and missing-data segments.

### 6. Current interval engine and unambiguous formulas

At time `now` in interval `[start,end)`, let:

- `T = 0.25 h`; `r = (end-now)` in hours (must be >0 for remaining-period advice).
- `L = active contractual target kW`, `M = safety margin kW`, `L_op = max(0,L-M)`.
- `E = imported energy already accumulated in *this fixed interval* kWh`, unaffected by historical export.
- `p = latest normalized instantaneous signed grid power kW`; `p_sm = time-weighted 30-second (default) signed power kW`, buffer may cross a quarter boundary.
- `E_budget = L_op*T`; `E_remaining = E_budget-E`; `P_allowed = max(0, E_remaining/r)` if r>0.

**Display / derived outputs:**

- Elapsed-quarter import average = `E / elapsed_hours` (when elapsed >0); current utilization `% = 100 * (E / elapsed_hours) / L` if L>0; distinguish **so-far utilization** from **projected end utilization**.
- **Instant final demand forecast** = `(E + r*max(0,p))/T` kW; **smoothed final demand forecast** = `(E + r*max(0,p_sm))/T` kW. Their forecast utilization uses contracted `L`; additionally show operational threshold if M>0.
- **Allowed average import for the remainder** = `P_allowed`; it is the permitted **import power averaged over remaining time**, not automatically additional load.
- **CAN ADD** = `max(0, P_allowed-p)` kW for a continuous, unchanged additional load from now to interval end while `E_remaining >= 0`, using *instant signed power* so known export surplus is included. Set `0` in unrecoverable mode. Optional smoothed advisory can be separately provided, but do not silently use smoothed readings in the primary CAN ADD number. This is a mathematical threshold, **not a promise of physical or contractual instantaneous current capacity**; represent uncertainty clearly.
- **MUST REDUCE** = `max(0, p-P_allowed)` kW of steady power reduction **now**, conditional on other loads staying constant. When E already exceeds E_budget, recovery is mathematically impossible; expose `unrecoverable_this_interval = true` and show MUST REDUCE as the power reduction needed to stop additional *import* (at least `max(0,p)`), explicitly labeled 'cannot restore target'. Do not claim reducing loads can reverse already imported energy.
- Zero remaining time: roll to next interval atomically, never divide by zero. At the first second of new interval compute projections using carryover smoothing buffer but reset `E` and elapsed time to the new fixed quarter only.
- **Forecast refresh:** update on each new input sample; recompute timer/projection graph about every second while displaying latest sampled p. Signal becomes stale when source update age exceeds a configurable/derived threshold, with warnings and unavailable outputs as appropriate.
- A high instantaneous service/import limit is a **separate constraint** not guaranteed by a 15-minute budget. The app must warn that CAN ADD is *budget headroom*, not hardware safe load headroom (breaker, phases, inverter export cap etc.). Do not encourage exceeding electrical connection/phase limits.
- If only import power (without signed export) is measured, do not invent hidden solar headroom; show a conservative/advisory reading or unavailable if it cannot be justified.
- Examples must be unit-tested: `L=4.8`, `E=0.70 kWh` at 10:10, `r=5/60 h`, `p=3 kW` => `P_allowed=6 kW`; forecast final `3.8 kW`, CAN ADD `3.0 kW`, MUST REDUCE `0`. If p=-2 kW and E unchanged, budget-only CAN ADD `8 kW` (subject to physical constraints).

### 7. Home Assistant entities, update cadence and availability

Expose normalized, distinct entities (actual HA-generated entity IDs can receive suffixes; unique IDs must be stable):

- `sensor.si_grid_current_power` signed +import / -export; `..._import_power`, `..._export_power`.
- `..._net_power_15m_rolling` **signed time-weighted rolling average**; `..._import_power_15m_rolling` import-only rolling average.
- `..._current_interval_import_average`, `..._current_interval_signed_average`, `..._last_completed_15m_import_demand`, `..._last_completed_15m_signed_average`.
- `..._target_kw`, `..._operational_target_kw`, `..._current_block`, `..._season`, `..._time_to_next_block`, `..._interval_elapsed_seconds`, `..._interval_remaining_seconds`.
- `..._quarter_import_kwh_so_far`, `..._quarter_export_kwh_so_far`, `..._quarter_budget_remaining_kwh`, `..._allowed_import_until_end_kw`.
- `..._forecast_instant_kw`, `..._forecast_smoothed_kw`, `..._forecast_utilization_pct`, `..._current_utilization_pct`.
- First-class `sensor.si_grid_can_add_power`, `sensor.si_grid_must_reduce_power`, optional separately labeled estimated safe advisory after M.
- `binary_sensor.si_grid_projected_exceedance`, `..._unrecoverable_interval`, optional input stale/quality warning, plus a quality/status sensor.
- Provide period summaries in a query API, not a new HA sensor per quarter-hour. Expose suitable HA recorder long-term stats via valid `state_class` and optional extra statistics while keeping detailed exact quarters in the dedicated archive.
- UI display timer refresh ~1 sec, calculations sample-triggered plus wall-clock boundary, HA entity updates should be throttled where sensible to avoid 1-second recorder bloat. Correct kW/W, kWh/Wh semantics; configure measurements' units and device/state classes legally, and use `unavailable` for unsupported features.

### 8. Archive, persistence, history and backups

- Dedicated SQLite DB using Python stdlib; **no separate user-installed database / HA plugin**. Never put it inside the HACS-managed `custom_components` folder or a large `.storage` JSON file. Use HA configuration path e.g. `.storage/si_grid_monitor_archive.db` or a dedicated config subfolder with documented backups; final path must be compatible with HA backups and managed separately from the recorder.
- Normal 24-hour day: 96 rows; DST transition days: 92 or 100 aligned quarters as appropriate. Store canonical start/end UTC times, local offset and original local representation so repeated 02:00 is unambiguous. B-tree indexes by UTC time and tariff block; archive namespace per configured metering point.
- Each completed quarter stores import/export kWh, signed average, imported 15-minute kW, optional observed raw peak, block, rule version, contracted target, safety margin/operational target, utilization, exceeded flag, amount over kW and %, completeness, source/provenance, quality code and timestamps.
- **Forever default** retention. Optional reduced retention requires explicit user action; never purge simply because HA recorder purges.
- Power loss/HA restart **mid-quarter:** persist durable incremental state/checkpoint and last measurement timestamp with bounded frequency; recover from checkpoint and available recorder history if possible, otherwise mark affected interval incomplete. Implement atomic/idempotent finalization, deduplicate replays/backfill, and use transactions to prevent duplicate rows.
- Disk I/O including SQLite must be done without blocking HA event loop, serialize DB operations correctly, handle migrations, busy locks, disk-full/read-only/corrupt DB conditions gracefully. Prefer SQLite's safe backup API / controlled checkpointing and documented HA backup inclusion, particularly if WAL is used.
- New versions migrate schema without wiping data; preserve archive on HACS updates, code uninstall or accidental HA configuration removal. The integration should detect prior archived data when readded, require confirmation for re-association if ambiguous. Factory reset is **separate and intentionally destructive**, requires warning/confirmation, can remove owned dashboard and per-integration data, and does not delete unrelated HA entities.
- Period coverage query must distinguish `valid`, `estimated`, `incomplete` and `missing` quarters. Exceedance count denominator comprises only complete/valid quarters unless the report clearly states otherwise. Never treat missing intervals as measured zero.
- Initial install can attempt safe recorder backfill of available raw HA source data (typically default 10 days) and any already recorded aligned quarter readings. Never claim exact records older than available evidence. HA hourly long-term stats alone cannot reconstruct fixed 15-minute data.

### 9. Over-limit / exceedance analysis

- Each **individual completed valid fixed quarter** with import demand **strictly greater** than the agreed applicable target (document floating point tolerance) counts one exceedance. Never group consecutive quarters into one event in summary or detail.
- Persist block/target as-of time and exact date/time for every exceedance, kW over, % over and optional excess energy above budget (`max(0, actual_kw-target_kw)*0.25 kWh`). Do not confuse this accounting measure with official billed excessive-power charges.
- Selected period reports: total valid quarters, missing/incomplete count, exceeded quarter count, % exceeded, duration = count*15 minutes (not a grouped event), peak import, greatest excess kW and %, timestamp, block-by-block counts/rates and import/export/averages.
- EXCEEDANCES detail: sortable, filterable individual rows date, start/end time, block, target, actual, excess, excess%, data quality; click to see exact quarter and previous/next quarter. Include zero-exceedance state.
- Expose summary/dashboard filters for Hour / Day / Week / Month / Year / Custom date range, all five blocks or one block.

### 10. Professional dashboard / UX, with graphical first card

Navigation: **OVERVIEW | TODAY | PERIOD | BLOCKS | EXCEEDANCES | HISTORY**. All pages responsive/mobile-friendly and work in HA native interface; styled coherently with Energy dashboard without claiming to copy the built-in dashboard source or identity.

- **OVERVIEW:** FIRST and visually largest card must be the live, graphical, fixed-quarter progress indicator with 00/15/30/45 boundary, countdown updating every second, color/labels according to state, signed current grid import/export, current quarter import average, active contracted target and margin, so-far utilization, instant/smoothed end forecasts (30 s primary), end forecast %, imported/budget kWh, allowed average through interval end, CAN ADD and MUST REDUCE. Show data freshness and exceptions; visually distinguish import (positive) and export (negative). Under it show today cards and a net-power chart centered on zero.
- **TODAY:** all 96 quarters (92/100 on DST) on a graph with positive import and negative export, aligned imported quarter demand, changing target and colored tariff blocks. A fixed 5-row table for B1-B5 even if absent (`Not active today`). For present blocks show start/stop spans, target, maximum quarter, mean, imported and exported kWh, exceedance count and percent; partial current interval excluded from completed-quarter statistics.
- **PERIOD:** Energy-dashboard-like selector with **Hour, Day, Week, Month, Year, Custom**; prev/next navigation and date picker; maxima, minima (signed), mean net, import/export, count, % over, applicable target. Adaptive chart binning with **maximum quarter demand** preserved in daily/monthly/yearly summaries (never replace peak with monthly mean). Drill from year to month to day to exact quarter.
- **BLOCKS:** always show B1-B5 summary for selected period; distinct actual mean/maximum demand, contractual target, kWh imported/exported, number of valid quarters and over-limit count / %, with details per block. Show inactive/not occurring periods explicitly.
- **EXCEEDANCES:** aggregate by block plus all exceeded quarters individually; sortable table with timestamps and difference, jump to precise quarter detail, no 45-minute grouping.
- **HISTORY:** professional archive explorer, time and block filters, exact quarter table, linked drill-down, quality/coverage indicators. User can inspect an individual 15-minute interval 15 days, two years or many years later if archived.
- Multi-year charts and large tabular reports must be efficient (server-side aggregation, pagination, bounded datasets, indexes); do not transfer 700k records to the phone at once.
- A backend query interface is needed for historic intervals and aggregates (HA WebSocket API or appropriate authenticated endpoint). UI must enforce HA permissions and not expose the archived data through public endpoints.
- Integrations distributed through HACS install files under `custom_components`; custom frontend dashboard scripts require a **separate resource registration/serving plan**. Prefer documented HA Community Dashboard strategy or a native HA panel, with correct resource loading, versioning, cache busting and removal/update behavior. Ensure genuinely usable setup (automatic provision or clearly guided one-time activation). Do not assume Python integration alone automatically creates Lovelace tabs.
- Settings UI: source mapping, signed direction, single/five target mode, safety margin, smoothing interval, archive status/retention, diagnostics and deliberate factory reset.
- User-facing localized text: Slovenian primary + English translation, with durable entity names and full documentation; no embedded hard-coded SolarEdge assumptions.

### 11. Distribution, website and developer workflow

- One public-release GitHub repository (may be private while developing), containing HACS-compatible Python integration, its frontend assets, `hacs.json`, README, license, changelog, contributor/issue templates, documentation and CI. Latest release through tagged GitHub Releases; users update normally via HACS, preserving config and archived records.
- HACS project presentation with README/info page, logo/icon if accepted by current HACS/Home Assistant Brands rules, screenshots, supported modes, feature limitations, links and setup screenshots.
- GitHub Pages user website with Home, Features, Install, Setup, Dashboard, Tariffs, History, FAQ, Troubleshooting, Changelog, Development. Avoid duplicate/conflicting instructions; `/docs` source should feed site and README links.
- Site explains no extra database needed, source sign convention, expected energy-data quality, network/breaker limitation for CAN ADD, no source-data upload, backup/restore and clean testing.
- CI: pure-Python unit and integration tests, lint/type checks, HACS validation, hassfest, frontend asset/build tests, dependency/security checks, migration and release test.
- Milestones: V0.1 setup/calculation engine/tests, V0.2 SQLite/archive/backfill, V0.3 tariff rules/time block engine, V0.4 Overview/Today frontend, V0.5 Period/Blocks, V0.6 Exceedances, V0.7 History/data quality, V0.8 tariff updates/docs/site, V0.9 beta and V1.0 stable. Implementation order may change without dropping requirements.
- PR-based Codex development. No merging or deletion of user data without review. Test upgrades, HACS removal/reinstall with preserved database, HA config removal/readd, and explicit factory-reset reinstall in a clean HA test instance. Never assume HA can be remotely accessed just because GitHub is connected.

### 12. Acceptance / calculations test matrix (mandatory)

1. Signed source mode with both polarities; separate import+export sensors; import-only; counters; aligned quarter values. W/kW, Wh/kWh conversions and HA entity availability.
2. Instantaneous sign positive import / negative export in all UI and APIs; export cannot cancel import in billing demand.
3. Signed rolling last-15-minute mean and import-only rolling mean at irregular sample timestamps; distinguish both from fixed quarter.
4. All minute/second quarter boundaries, exact interval finalization, last-second rollover, midnight, date/year change, Europe/Ljubljana DST repeated/nonexistent times.
5. Sample gaps, frozen sensor, unavailable state, bad unit, counter reset, sparse source, source change and checkpoint recovery with correctly marked incomplete data.
6. At 10:10 with target 4.8 kW, quarter-import E=0.70 kWh, p=+3 kW, remaining 5 min: forecast instant 3.80 kW, remaining budget 0.50 kWh, allowed 6.00 kW, CAN ADD 3.00 kW, MUST REDUCE 0.00 kW. With p=-2 kW and same E, mathematical CAN ADD=8 kW before physical constraints.
7. Smoothed 30-second window includes previous quarter samples in first seconds of next quarter; 60-second and configurable variants; first forecast does not inherit previous quarter energy.
8. Forecast % vs so-far %, target vs adjusted operational limit, unrecoverable already-exceeded budget, zero margin default, current import and export differences.
9. Block mapping official fixtures covering 2026 vs 2027 changes, weekends and real public holidays, rule expiry warning, targets all-equal and independently changed, historical target snapshots.
10. Three back-to-back 15-minute exceedances produce **three** records; report correct dates, blocks, kW over, % over and duration 45 minutes without grouping.
11. Automatic daily/weekly/monthly/yearly maxima derive from **individual quarter peak** not a long-term hourly mean; all five block rows displayed even where none are active that day.
12. Permanent SQLite archive queries for a record older than 15 days; ten-year dataset performance, startup backfill provenance, idempotence after restart, disk failure, DB schema migrations and backup integrity.
13. UI source staleness, supported/unavailable feature cases, mobile responsiveness, one-second countdown, input-triggered updates and correct safety caveat for physical service limits.
14. HACS install in an isolated test HA; code upgrade preserves settings and DB; uninstall/reinstall retains archive; explicit destructive factory reset removes only own data; Dashboard custom frontend actually loads.
15. README vs implementation feature flags are truthful; Github Pages/HACS documentation created and linked; official tariff-source citations and calendar verification documented.

### 13. Guidance to Codex

Read the entire specification before work. Build and test in small milestones. Never mark a requirement 'completed' merely because files or stubs exist. Maintain an implementation status table with `Planned / Implemented / Tested / HA-verified` per feature. Explicitly report blockers requiring user HA testing. Prefer safety, correctness and honest data-quality labeling over cosmetically polished but misleading numbers.

#### External technical references

- HA 5-minute vs hourly history: https://www.home-assistant.io/docs/configuration/long-term-statistics/
- HA custom dashboard strategies: https://developers.home-assistant.io/docs/frontend/custom-ui/custom-strategy/
- HA frontend resources: https://contributors.home-assistant.io/frontend/custom-ui/resources/
- HA blocking operations: https://contributors.home-assistant.io/core/internals/blocking-operations/
- HACS integration package requirements: https://www.hacs.dev/docs/publish/integration/
- HACS validation: https://hacs.dev/docs/publish/action/
- Slovenia 2027 block overview: https://www.uro.si/prenova-omre%C5%BEnine/%C4%8Dasovni-bloki/2027
