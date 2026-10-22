# SI Grid Monitor

SI Grid Monitor is a HACS-compatible Home Assistant custom integration for
Slovenian fixed 15-minute grid-demand monitoring. V0.9.5 beta provides guided setup,
an automatically registered sidebar dashboard, import-only live calculations,
sustained-load forecasting, and a permanent
SQLite quarter archive, a paginated HISTORY explorer, controlled Recorder
reconstruction safeguards, and bilingual dashboard support. It is an early
development release, not the complete V1
product.

The authoritative MASTER PRODUCT SPECIFICATION V1.1 is preserved unchanged in
[`SPECIFICATION.md`](SPECIFICATION.md). V0.2 additions are recorded separately in
[`SPECIFICATION_V1.2_ADDENDUM.md`](SPECIFICATION_V1.2_ADDENDUM.md) and the V0.3
calendar rules are documented in
[`SPECIFICATION_V1.3_ADDENDUM.md`](SPECIFICATION_V1.3_ADDENDUM.md).
V0.4 behavior is documented in
[`SPECIFICATION_V1.4_ADDENDUM.md`](SPECIFICATION_V1.4_ADDENDUM.md).
The user-supplied 2026 contracted-power acceptance case is documented separately
in [`REAL_WORLD_VALIDATION.md`](REAL_WORLD_VALIDATION.md); its values are test
fixtures, never installation defaults.
The combined history/platform-release status is tracked in
[`V0.8_IMPLEMENTATION_STATUS.md`](V0.8_IMPLEMENTATION_STATUS.md).
The V1 requirement audit, safe-upgrade instructions, rollback guidance and clean
Home Assistant beta procedure are in
[`V0.9_BETA_ACCEPTANCE.md`](V0.9_BETA_ACCEPTANCE.md).
The approved four-mode scope that supersedes the older source-mode roadmap is
documented without changing the master specification in
[`SPECIFICATION_V1.5_SOURCE_MODES_ADDENDUM.md`](SPECIFICATION_V1.5_SOURCE_MODES_ADDENDUM.md).

## V0.9.5 beta installation and dashboard

1. Install from HACS and restart Home Assistant.
2. Add SI Grid Monitor from Settings > Devices & services.
3. Choose signed power, separate import/export power, import-only power, or
   cumulative energy counters, then complete the dated B1-B5 contract and settings.
4. Open **SI Grid Monitor** directly from the left sidebar.

No Lovelace dashboard, YAML, pasted JavaScript, or resource registration is
required. One idempotent custom panel safely supports multiple config entries
with separate archive namespaces and is removed only after the final entry unloads.
Every tab displays the active meter's friendly name in a compact sticky control.
When multiple meters exist, the selector stays reachable while scrolling and the
last choice is remembered in local browser storage when supported. If that meter
is later removed or unavailable, the dashboard selects another available entry
and reports the fallback. Changing meters clears entry-specific live, chart,
statistics, calendar and HISTORY state before loading the new namespace.

- **Overview** shows the current quarter, measured trace, import/export, budgets,
  forecasts, advice, prior-quarter summary, and upcoming limits.
- **Today** shows 92/96/100 real quarters, quality states, totals, and five block rows.
- **Period** analyzes Hour/Day/Week/Month/Year/Custom ranges with adaptive
  quarter/hour/day/month bins, coverage, historical targets and drill-down.
- **Blocks** always compares B1-B5 using stored historical targets, validity and
  confirmed-contract statistics, with high-demand quarter details.
- **Exceedances** lists every confirmed exceeded quarter separately with safe
  filtering, sorting, server-side pagination and analytical excess quantities.
- **History** explores the permanent archive with bounded server-side paging,
  quality/block/exceedance filters, exact-quarter drill-down, archive metadata,
  and an administrator-only Recorder audit/reconstruction workflow.
- **Tariff Calendar** shows backend-classified 2026-2030 hours with DST and rule status.

The countdown is browser-local. Missing historical detail is explicitly labeled;
the dashboard never fabricates samples from SQLite quarter summaries.

V0.8.0 retains V0.4.2's gap-aware cumulative-energy segments, adaptive Overview axes and a
complete Today 15-minute interval selector. After updating through HACS, restart
Home Assistant and perform a normal browser/app frontend refresh so the new
versioned JavaScript assets replace any cached V0.4.1 module. Do not remove and
re-add the integration: existing entity identities and all schema-5 quarter rows
are preserved by the additive schema-6 migration.

## Safety and accuracy

- Internally, **positive means grid import** and **negative means grid export**.
- The signed rolling last-15-minute mean is not the fixed-quarter billing-style
  demand. The latter uses imported energy only; export never cancels import.
- Live power is integrated as piecewise constant only while the signal is fresh.
  Gaps are marked incomplete and are never filled with invented zeroes.
- Reconstructed values are sample-derived estimates, not supplier-meter-exact
  billing records.
- **CAN ADD and SUSTAINED CAN ADD are energy-budget estimates. They are not proof that a breaker,
  phase, cable, connection, or inverter can safely carry that power.**

## V0.9 beta status

V0.9 is a stabilization candidate, not a claim of real Home Assistant
acceptance. Automated coverage and remaining manual blockers are classified in
the beta acceptance report linked above.

| Feature | Planned | Implemented | Tested | HA-verified |
|---|:---:|:---:|:---:|:---:|
| HACS/manifest/config-flow skeleton | Yes | Yes | Yes (CI) | No |
| Local transparent brand icons (1×/2×) | Yes | Yes | PNG validated | No |
| Signed live W/kW power source | Yes | Yes | Yes | No |
| Separate import/export W/kW sources | Yes | Yes | Yes | No |
| Import-only W/kW source | Yes | Yes | Yes | No |
| Automatic cumulative Wh/kWh conversion | Yes | Yes | Yes | No |
| Signed rolling 15-minute mean | Yes | Yes | Yes | No |
| Fixed-quarter import-only demand | Yes | Yes | Yes | No |
| Import/export switching and boundary splits | Yes | Yes | Yes | No |
| 30/60/90/120/180 s smoothing, 120 s default | Yes | Yes | Yes | No |
| Forecast, allowed import, CAN ADD/MUST REDUCE | Yes | Yes | Yes | No |
| Stale/gap quality handling | Yes | Yes | Yes | No |
| Europe/Ljubljana DST quarter mapping | Yes | Yes | Yes | No |
| 15/30/60/120-minute sustained forecast | V0.2 | Yes | Yes | No |
| SQLite archive, checkpoints, recovery | V0.2 | Yes | Yes, including boundary reload | No |
| Detailed-recorder historical backfill | V0.2 | Yes | Epoch/provenance tests | No |
| Source/sign/target reconfiguration epochs | V0.2 | Yes | Yes | No |
| Official 2026/2027 tariff/calendar rules | V0.3 | Yes | Yes | No |
| 2028–2030 explicit provisional/unverified policy | V0.3 | Yes | Yes | No |
| Five block-specific targets and migration | V0.3 | Yes | Yes | No |
| Seven-tab dashboard including HISTORY | V0.4-V0.8 | Yes | Yes (automated) | No |
| Controlled Recorder audit/reconstruction | V0.8 | Yes | Pure/unit tests | No |
| English/Slovenian dashboard localization | V0.8 | Yes | Automated fallback tests | No |
| GitHub Pages source/build preview | V0.8 | Yes | Static build | Not published |
| Official HACS default listing | External future work | No | No | No |

All four modes use the same calculation and archive engine. Import-only mode
marks export unknown. Counter mode exposes integration-owned derived-power
entities and treats each derivative as an evidenced interval average, not an
instantaneous measurement; unsupported forecasts remain unavailable.

## Source modes and generated entities

- **Signed live power** accepts W/kW and retains the existing configurable polarity.
- **Separate import/export power** requires two nonnegative W/kW sensors and rejects
  conflicting simultaneous import and export readings.
- **Import-only power** accepts one nonnegative W/kW sensor. Export is unknown,
  never silently reported as measured zero.
- **Cumulative energy counters** require imported energy and optionally accept
  exported energy in Wh/kWh. SI Grid Monitor creates stable entry-owned derived
  import/export power entities automatically; no YAML or helper is required.

Counter resets establish a new baseline. Gaps and intervals that cross a fixed
quarter boundary without sufficient allocation evidence are retained as
incomplete rather than confirmed billing measurements.

## Current entities

The signed live-power mode exposes current signed power, rolling signed and
import-only 15-minute means, current fixed-quarter imported/exported energy and
import average, target and operational target, remaining budget and allowed
average import, instant and smoothed forecasts, utilization, CAN ADD, MUST
REDUCE, elapsed/remaining seconds, quality, projected exceedance,
unrecoverable-quarter, stale-input status, and these additional entities:

- **Sustained CAN ADD power**: the conservative additional continuous load for
  the configured 15/30/60/120-minute horizon.
- **Sustained MUST REDUCE power**: the continuing reduction required by the
  most restrictive evaluated quarter.
- **Sustained forecast quality**: availability, coverage, source age, limiting
  quarter/target, unrecoverable state, and the forecast assumption.

### Current-quarter versus sustained advice

**CAN ADD THIS QUARTER** and **MUST REDUCE THIS QUARTER** end at the current
`:00/:15/:30/:45` boundary. **SUSTAINED CAN ADD** and **SUSTAINED MUST REDUCE**
evaluate that remainder plus future fixed quarters intersecting the horizon.
They repeat the recent signed-power path and also evaluate the latest valid
instantaneous value held constant; the safer result wins. This is a persistence
estimate, not a PV, weather, appliance, or supplier-meter prediction.

For every scenario, the proposed load is applied to signed grid power first and
then import is clamped with `max(0, signed_power + addition)`. Export at another
time never offsets import. Each future quarter uses the contracted target for
its independently classified tariff block.

Entity IDs are generated by Home Assistant and can receive suffixes. Unique IDs
are stable per config entry.

## Slovenian tariff calendar

V0.3 classifies each fixed quarter as B1–B5 using local Europe/Ljubljana civil
time, higher season (November–February), lower season (March–October), weekday
status and official Slovenian work-free holidays. The 2026 and 2027 hourly tables
come from URO; the legally amended schedule begins on 1 January 2027.

URO currently publishes no separate official schedule for 2028–2030. These
years therefore return **unverified / no block** by default. Users may explicitly
enable a **provisional continuation of the 2027 table** for planning, but those
results remain labeled provisional and are not legally confirmed.

Tariff availability does not control metering. In an unverified year with
provisional use disabled, signed/import/export power, quarter energy, completed
quarter demand, SQLite archiving and checkpoints continue normally. Contractual
budgets, forecasts, utilization, CAN ADD/MUST REDUCE and exceedance advice are
unavailable with a reason attribute. If provisional use is enabled, those
values are explicitly provisional estimates; their exceedances are never added
to confirmed contractual statistics.

Initial setup creates one assignment from the explicitly entered target and
inclusive start/end dates. Integration Options expose a validated JSON period
editor for one or more non-overlapping assignments. Each object contains
`effective_from`, `effective_to`, five `block_targets_kw` values, `provenance`
and an optional `recorded_on` date. This interim editor supports separate
assignments for 2026–2030 without creating extra config entries.

On a V0.2 upgrade the previous target remains copied into all five legacy fields,
but its validity is unknown, so migration stores no confirmed assignment and
does not invent dates. Physical measurements and archiving continue while
contractual sensors remain unavailable until the user adds a dated assignment.
Current-quarter calculations use the active dated assignment; sustained
forecasts resolve the independently applicable assignment and block for every
future quarter.

Contracted-power assignments are user-owned and date-bound independently from
tariff calendar rules. The period model and Options editor retain provenance and
the date a record was issued. An expired assignment is never carried into a
later year; a 2026 assignment must not be assumed valid for 2027–2030.

Example Options value:

```json
[{"effective_from":"2026-01-01","effective_to":"2026-12-31","block_targets_kw":[3.5,3.9,4.1,4.2,4.2],"provenance":"distributor assignment","recorded_on":"2025-10-17"}]
```

New entities expose current/next block and target, season, day type, transition
countdown, calendar year, rule status, and contracted power B1–B5. Calendar
status attributes include the rule version, source, local timestamp, UTC offset,
fold and holiday name.

## Branding and HACS display limitation

The integration ships transparent local-brand assets at the standard 1× and 2×
sizes:

- `custom_components/si_grid_monitor/brand/icon.png` — 256 × 256
- `custom_components/si_grid_monitor/brand/icon@2x.png` — 512 × 512

These files make the repository-side integration package ready to serve its
local icon. They do **not** guarantee that the HACS dashboard or repository
listing will display it. HACS has a known frontend limitation around loading
locally provided custom-integration icons; see
[`hacs/frontend#949`](https://github.com/hacs/frontend/pull/949). A placeholder
in HACS can therefore remain even when these assets are installed and valid.

## Install and test locally

This PR branch is not a published HACS release and HACS custom repositories
normally install the default branch. Before merge, test it manually:

1. Download the PR branch archive from GitHub.
2. Copy `custom_components/si_grid_monitor` into the test Home Assistant
   configuration's `custom_components` directory.
3. Restart Home Assistant, clear the browser cache if the integration is not
   listed, then continue with setup below.

After review and merge, the HACS custom-repository path is:

1. In HACS, open **Integrations**, choose **Custom repositories**, and add
   `https://github.com/igormesarec/si-grid-monitor` as an **Integration**.
2. Install **SI Grid Monitor**, then restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and select
   **SI Grid Monitor**.
4. Select **One signed live grid-power sensor**, choose a W or kW entity, confirm
   its sign direction, and enter the target plus its inclusive validity dates.
5. Verify the live sign: import must be positive and export negative. Source,
   polarity, target, margin, smoothing, simulation threshold, retention and
   sustained horizon can be changed from the integration options.
6. Follow [`MANUAL_TEST_PLAN.md`](MANUAL_TEST_PLAN.md) before treating any
   result as operationally useful.

No Home Assistant credentials, internet connection, YAML, or external database
are required for normal calculation. Test first in a non-production HA instance.
V0.3 treats a live source as stale after 60 seconds; this threshold becomes
configurable/derived in a later milestone.

## Developer test

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-test.txt
.venv/Scripts/python -m pytest
.venv/Scripts/python -m ruff check .
```

On Linux/macOS, use `.venv/bin/python`. GitHub Actions additionally run hassfest
and the HACS repository validator.

## Current limitations

- Mode D power is an interval-average estimate. Instantaneous and sustained advice
  is unavailable when the source evidence cannot support it.
- Live-sensor quarters are labeled reconstructed/incomplete; no supplier-exact
  claim is made.
- Recorder reconstruction and SQLite migration/recovery are automated but still
  require validation against a real supported Home Assistant installation.
- Historical reconstruction starts only where a persisted source/sign epoch is
  available and uses the target effective in that epoch. A quarter crossed by a
  source or target change is marked mixed/unknown and cannot create a contractual
  exceedance. Pre-migration rows whose assumptions cannot be audited are retained
  as `legacy_unverified` and excluded from confirmed contractual statistics.
- Confirmed archive maxima, averages and energy totals exclude incomplete or
  unavailable quarters. Their observed partial energy is retained separately so
  missing coverage is visible rather than silently promoted to a valid quarter.
- The calendar is legally verified only for 2026 and 2027 as of 18 October 2026.
  Provisional 2028–2030 continuation requires explicit opt-in and may differ from
  rules later published by URO.
- The V0.3 multi-period Options editor is validated JSON rather than a polished
  per-period form. Invalid, overlapping or reversed periods cannot be saved.
- Completed quarters retain the tariff policy and rule status that applied when
  they were written. Changing provisional-calendar policy does not relabel old
  rows. Legacy rows without policy provenance remain explicitly unknown.
- The archive is integration-owned, namespaced per config entry, WAL-backed and
  retained forever by default. Removal policy and export tooling are not yet UI
  features; uninstalling the integration does not promise archive deletion.
- The HISTORY archive explorer and public export services remain planned for
  V0.7. Historical reports use only existing schema-5 rows and cannot recreate
  measurements from dates before the archive began.
- The one-second backend refresh is an initial runtime mechanism; recorder and
  frontend update strategy require HA testing and later optimization.
- HACS install/update/removal and clean-reinstall behavior require validation in
  an isolated Home Assistant instance before any release claim.

## Roadmap

- **V0.2:** import-only forecasting, configurable live settings,
  sustained load advice, independent SQLite archive, checkpoints, recorder
  backfill, provenance, and Forever default retention.
- **V0.3:** current branch: dated official 2026/2027 rules, explicit unverified
  future-year handling, holidays, five targets, calendar entities/API and
  immutable block/rule/target archive provenance.
- **V0.4:** OVERVIEW and TODAY; the first Overview card is the live graphical
  current quarter with one-second countdown, instant/30-second forecasts, CAN
  ADD/MUST REDUCE, and all five Today block rows even when inactive.
- **V0.6:** combined V0.5/V0.6 release: PERIOD and BLOCKS with shared
  quarter-peak-preserving aggregation, plus granular paginated EXCEEDANCES.
- **V0.7:** HISTORY, coverage/quality exploration, pagination, and long-term
  archive query API.
- **V0.8:** reviewed tariff update notices, complete English/Slovenian
  localization, docs, GitHub Pages, HACS listing, upgrade/reinstall lifecycle.
- **V0.9:** beta and clean-HA verification.
- **V1.0:** stable release after the full specification acceptance matrix passes.

## License

MIT — see [`LICENSE`](LICENSE).
