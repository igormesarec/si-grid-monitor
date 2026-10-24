# Changelog

All notable changes to SI Grid Monitor will be documented here.

## [Unreleased]

### V1.0.3 localization draft

- Added a first native ConfigFlow **Language / Jezik** selector with English as
  the default and Slovenščina as the alternative.
- Added a non-destructive Preferred language option and an accessible EN/SL
  switch in the shared dashboard header.
- Dashboard overrides persist across navigation/reloads, take priority over the
  selected meter preference, and do not reset when the active meter changes.
- Existing entries default to English only when no preference exists; archives,
  contracts, source epochs, entry identities and measurements are untouched.
- Integrated full V1.0.2 Contracts, historical evidence, audit pagination,
  Repairs and calendar semantics into both English and Slovenian interfaces.

## [1.0.2] - release candidate

- Added guided Schedule change with atomic two- or three-segment inclusive date
  splits, separate detail editing/correction/removal, complete before/after
  preview and conflict-specific validation.
- Added the meter-scoped Contracts dashboard with current health, timeline,
  B1-B5 comparison, bounded audit history and administrator-only navigation to
  Home Assistant integration settings.
- Added stable per-meter Repairs issues for missing and uncovered expiring
  assignments, automatically cleared after correction or an adjacent successor.
- Added schema 7 as a strictly additive `contract_audit` table. Schema-6 quarter
  measurements, epochs, checkpoints, tariff versions and target provenance are
  not rewritten.
- Tariff Calendar now shows **As recorded** archive/epoch evidence separately
  from the target resolved through **Current configuration**.
- Fixed an empty optional Record date and prevented future-only schedule changes
  from falsely making an otherwise unchanged live quarter configuration mixed.
- Added optimistic schedule-revision validation so an outdated OptionsFlow
  preview cannot overwrite a newer contract edit from another session.
- Completed the Contracts evidence viewer with historical configuration
  snapshots, immutable archived-quarter target evidence and paginated audit events.
- Historical Calendar cells now keep archived null targets unknown and label
  configuration inference separately from archived evidence and current settings.
- Replaced three indistinguishable contract links with one administrator-only
  integration-settings action and selected-meter instructions.

## [1.0.1] - hotfix release candidate

- Restored Home Assistant's native integration **Configure** action by removing
  the custom panel's `config_panel_domain` override. The sidebar dashboard,
  seven tabs and shared multi-meter selector remain registered normally.
- Added regression coverage proving the Configure menu exposes calculation and
  meter settings, dated contracted-power assignment management/addition, and
  archive retention/deletion.
- Added an OptionsFlow regression that shortens an existing dated B1–B5
  assignment and adds a non-overlapping successor without rewriting archived
  targets, measurements or source epochs.

## [1.0.0] - release candidate

- Reduced active input scope to three live-power modes: signed, separate
  import/export, and import-only W/kW sensors.
- Removed cumulative-counter setup, options, conversion runtime, listeners,
  derived entities and live dashboard presentation.
- Added safe legacy Mode D detection before runtime construction. Existing
  configuration and schema-6 archives remain untouched; Wh/kWh values are never
  reinterpreted as W/kW.
- Added an explicit same-entry A/B/C reconfiguration path and bilingual repair
  notice while retaining historical counter-derived provenance.
- Reconfiguration now rejects a live source already owned by another entry,
  preserves the entry/archive namespace, and safely rebinds the config-entry
  unique ID to the accepted source. Disabled legacy entries now unload/reload
  without requiring a runtime object, while removal retains archives by default.
- Added genuine V0.9.6 schema-6 archive coverage proving that counter-derived
  rows, configuration epochs, checkpoints, targets and provenance survive the
  V1 transition without silent reclassification.
- Kept all seven dashboards, import-only billing methodology, B1–B5 targets,
  forecasts, multi-meter isolation, archive safety and three-decimal power/energy
  presentation.
- Added the V1 scope clarification, release-candidate status and documentation
  coordination requirements for open PR #14.

## [0.9.6] - 2026-10-23

- Moved the cumulative-counter minimum observation and plausibility-ceiling
  controls into Mode D Options, with stored values restored on reload and passed
  directly to the active converter; Mode A no longer shows unrelated controls.
- Standardized dashboard kW/kWh presentation and Home Assistant entity display
  hints to three decimal places while retaining full engine/archive precision,
  adaptive chart ticks, integer counts and two-decimal percentages.
- Kept both quarters touched by an unaligned counter interval explicitly
  incomplete. A multi-quarter 30-second-cadence regression conserves the exact
  energy while preventing ambiguous cross-boundary allocation from becoming a
  confirmed contractual result.
- Added an explicit TODAY **Current / Live** action. TODAY defaults to the live
  quarter and preserves a deliberately selected archived quarter across normal
  10-second refreshes.
- Prevented quantized cumulative counters from producing trusted short-interval
  derivative spikes. Counter deltas now accumulate for a configurable minimum
  observation interval (30 seconds by default) before conversion.
- Added a configurable meter-specific plausibility ceiling (100 kW by default).
  Rejected anomalies are excluded from billing integration, retained in
  provenance diagnostics and cannot create confirmed contractual exceedances.
- Kept the real counter-energy delta intact while accumulating short reports;
  gaps, resets, rejected discontinuities and unsupported cross-quarter
  allocation remain incomplete rather than being spread across time.
- Separated counter-derived interval-average power from instantaneous live
  power throughout entities, WebSocket data and the dashboard. Mode D now
  reports instantaneous and sustained forecasts as unsupported instead of
  describing the absent instantaneous sample as stale.
- Added a gap-aware Mode D interval chart and cumulative-energy trajectory using
  only accepted evidenced intervals and the authoritative engine energy total.
- Required bidirectional net counters to use Home Assistant `total` state class;
  `total_increasing` remains valid for monotonic import/export counters but is
  rejected for a counter expected to decrease during reverse flow.
- Added regressions for the reported 402.06 kW quantization spike, rapid state
  reports, unchanged readings, plausibility rejection/recovery, first baseline,
  net-counter state class and exact quarter-energy preservation.

- Made archive deletion authorization entry-scoped and valid for only 10 minutes;
  an expired or missing confirmation always falls back to retaining schema-6 data.
- Added explicit HISTORY export provenance for directly measured, net-inferred,
  and unknown export so an unsupported export channel never appears as measured zero.
- Preserved per-quarter export evidence for separate cumulative counters across
  failure, recovery and checkpoint restore. Mixed quarters show only the observed
  export subtotal and explicitly identify their unknown intervals.
- Added conservative bidirectional-net discontinuity handling using explicit
  `last_reset` metadata and an implausible interval-rate guard while preserving
  ordinary negative reverse-flow deltas.
- Added V0.9.5's four supported input designs: signed live power, separate
  nonnegative import/export power, import-only power, and cumulative Wh/kWh
  counters with integration-owned derived-power entities.
- Removed aligned quarter records (former Mode E) from the setup choices and
  active product roadmap without changing or deleting historical archive rows.
- Preserved import-only billing by carrying separate import/export quantities
  through the shared engine; export never offsets imported quarter energy.
- Added conservative counter quality handling for first readings, resets,
  duplicates, gaps and cross-quarter intervals. Counter derivatives remain
  interval averages and do not masquerade as verified instantaneous forecasts.
- Added a responsive sticky active-meter control shared by every dashboard tab.
  It displays the friendly name, remembers the last selection locally when
  browser storage is available, safely falls back with a notice when that entry
  disappears, and retains entry-scoped request gates across every view.
- Expanded cumulative-counter setup into import-only, bidirectional net and
  separate import/export behaviors. Net polarity is configurable; separate
  channels retain independent baselines and asynchronous update cadence.
- Kept bidirectional net-derived contractual results unconfirmed because a net
  delta can hide import/export reversals between readings.
- Preserved the V0.9 Mode A source identity so upgrading does not create a false
  configuration epoch or duplicate signed-source configuration.
- Added explicit archive-removal policy: keep is the default; permanent deletion
  requires exact confirmation, can create a consistent backup, waits for durable
  shutdown, and removes only the selected meter's database and sidecars.
- HISTORY now separates completed time before archive monitoring began from
  genuinely missing completed intervals during a known source epoch.

- Started the V0.9.0 beta-readiness milestone with a complete V1 acceptance
  matrix, safe V0.8 upgrade/rollback guidance and a clean-HA test procedure.
- Made config-entry setup transactional: failed platform forwarding now stops
  the runtime, removes its registry entry and unregisters a newly created panel.
  Partial runtime startup also closes SQLite and removes listeners/tasks before
  returning the original error.
- Added beta lifecycle regressions for clean setup/unload, failed setup rollback,
  archive persistence across code reinstall, multiple-meter namespaces, startup
  cleanup and synchronized backend/frontend versioning.
- Hardened cancellation and partial-platform startup rollback: both platform
  orders unload cleanly, stale `runtime_data` is cleared before retry, and
  runtime shutdown completes pending archive/checkpoint work despite individual
  listener cleanup failures before reporting the collected errors.
- Made runtime shutdown itself cancellation-safe: durable drain, pending-quarter,
  checkpoint and SQLite-close work runs in one shielded idempotent task with a
  finite cancellation grace period. An unload interrupted before cleanup finishes
  retains its runtime registry reference for a safe join/retry instead of
  advertising successful removal while archive work is active.
- Added same-entry runtime ownership gating: setup now waits a bounded interval
  for a prior durable shutdown, defers without overwriting registry/runtime data
  while SQLite ownership remains active, and transfers ownership only after the
  prior task confirms archive closure. Failed rollback uses the same rule.

## [0.8.2] - 2026-10-21

- Corrected HISTORY completeness statistics so only already completed fixed
  quarters can be missing. The current in-progress quarter and later quarters
  are reported separately as future/uncompleted.
- Added explicit completed-expected, completed-archived, incomplete,
  unavailable and future/uncompleted counts. Local-day ranges retain their
  true 92/96/100-quarter Europe/Ljubljana DST lengths.
- Added regression coverage for current and future dates, local midnight,
  exact quarter transitions, real gaps and both 2026 DST transition days.

## [0.8.1] - 2026-10-21

- Aligned HISTORY axis ticks and quarter grids inside a shared scroll area,
  including phone layouts and desktop scrollbars. Partial measurement status
  wraps outside the bar, with no partial contractual-demand bar.
- Restored optional date/energy/demand/utilization/quality sorting for All-block
  HISTORY while keeping newest-first defaults and chronological block reports.
- Added headless browser geometry tests across 320/360/390/430/768/1280 px,
  light/dark themes, enlarged text, scrolling and keyboard card expansion.
- Added the V0.8.1 mobile HISTORY hotfix: narrow headers and filter controls now
  stack without overlap, the quarter chart no longer requires a 760 px canvas,
  and phones use expandable quarter cards instead of a repeatedly scrolled table.
- HISTORY now shows a bounded newest-first chronological record list when all
  tariff blocks are selected, with B1-B5 identity chips and unchanged
  measurement-validity semantics. Frontend modules use the `0.8.1` cache key.
- Made the schema-5 to schema-6 archive upgrade explicitly transactional and
  restart-safe, including validation/recovery of partial development objects.
- Made each reconstruction update and its revision entry one atomic operation;
  stale audits now revalidate measurement, source/configuration epoch and target
  provenance before any write.
- Clarified HISTORY overall-range versus filtered-result totals, exposed the
  source-configuration-epoch filter, and added parameterized English/Slovenian
  translations for dynamic navigation, HISTORY, audit and error messages.
- Revalidated controlled reconstruction against the exact dated contracted-power
  assignment and tariff block at apply time, rejecting stale audit plans.
- Split HISTORY exceedance filters into Confirmed Yes, Confirmed No and
  Unconfirmed while preserving SQLite NULL semantics.
- Added a bounded newest-first HISTORY block-quarter chart/table without
  inventing instantaneous peaks, plus consistent BLOCKS/PERIOD reference grids,
  visual legends and Europe/Ljubljana DST-safe axis labels.

## [0.8.0] - 2026-10-20

- Added the HISTORY archive explorer with canonical UTC quarter identities,
  server-side filters/sorting/pagination, quality/provenance distributions,
  exact-quarter drill-down and bounded responses suitable for dense archives.
- Added additive SQLite schema 6 tables for reconstruction jobs, immutable
  before/after revision records and backup metadata; existing schema-5 quarters
  migrate in place without target, tariff or measurement recalculation.
- Added administrator-only, user-initiated detailed-Recorder audit and confirmed
  reconstruction. Audits are dry-run, chunked, epoch-aware and never use hourly
  long-term statistics; applying requires confirmation and creates a SQLite backup.
- Added offline tariff lifecycle metadata. 2026/2027 remain official; 2028–2030
  remain explicitly provisional and require opt-in.
- Added a shared English/Slovenian dashboard localization layer with English
  fallback and runtime-language refresh, plus updated HA translations.
- Added responsive GitHub Pages source and a build-only preview workflow. Pages
  deployment and repository settings remain owner-controlled.

## [0.6.0] - 2026-10-19

- Ordered every PERIOD chart bin by its canonical expected UTC start, with a
  normalized archived UTC fallback for exceptional archive-only bins; mixed
  missing/measured data and both rollback folds now remain chronological.
- Captured the Exceedances live timestamp once on Home Assistant's event-loop
  thread before dispatching the immutable archive query to the executor.
- Hardened previous-period comparisons so both periods require complete valid
  coverage and equal quarter counts; partial and DST-length-mismatched periods
  are explicitly non-comparable without extrapolation.
- Corrected Exceedances incomplete/unconfirmed totals to count distinct quarter
  slots rather than adding overlapping diagnostic categories.
- Made PERIOD drill-down follow actual bin resolution and canonical UTC bounds,
  including missing bins and repeated DST hours, while distinguishing missing
  data from genuinely measured zero values.
- Reduced tariff-filter planning to one classification per UTC hour and added a
  populated ten-year bounded-performance regression.
- Combined the planned V0.5 and V0.6 milestones into one schema-5-compatible
  release with PERIOD, BLOCKS and EXCEEDANCES dashboard pages.
- Added authenticated, entry-namespaced SQL aggregation for local-calendar
  Hour/Day/Week/Month/Year/Custom ranges with DST-correct half-open UTC bounds.
- Added adaptive historical bins that retain the real maximum 15-minute import
  demand separately from averages and never turn missing records into zeroes.
- Added five-block reconciliation using each quarter's immutable target, tariff,
  quality, simulation and contractual provenance; all B1-B5 rows remain visible.
- Added confirmed exceedance summaries and one-row-per-quarter server-side
  sorting, filtering and pagination. Consecutive exceedances are not merged.
- Preserved SQLite schema 5, existing configuration entries, entity identities,
  source modes and the V0.4.2 live calculation engine without recalculation.

## [0.4.2] - 2026-10-19

- Rendered complete cumulative import trajectories when coverage reconciles and
  recent supported suffixes anchored to the authoritative backend total when an
  earlier gap exists; stale or unsupported history remains point-only.
- Added adaptive Overview power and energy axes, exact three-decimal contractual
  quarter-energy references, and one shared series color/dash definition used by
  chart strokes and legends.
- Suppressed the unused negative power region and zero-export path until genuine
  export occurs, while retaining an explicit zero line and expanding for peaks.
- Separated current-quarter forecast status from sustained-horizon quality and
  exposed source age and coverage explanations without changing the 60-second
  staleness or billing calculation.
- Added a complete Today 15-minute selector with Previous/Next controls, a DST-
  aware dropdown, accessible whole-slot interaction, stable selection/scroll/focus,
  and distinct archived, live, missing, unavailable, and upcoming detail states.
- Clarified confirmed Today statistics, partial observed energy, contributing
  quarter counts, and the electrical-safety limits of CAN ADD advice.
- Cache-busted both dashboard modules through the V0.4.2 panel URL; updating does
  not require deleting the config entry or SQLite archive.

## [0.4.1] - 2026-10-19

- Fixed the historical-quarter and Today WebSocket crash caused by treating
  `sqlite3.Row` values as column names; both paths now enumerate `row.keys()`.
- Added safe history error codes, server-side traceback logging and explicit
  retry states so archive failures are never presented as an empty archive.
- Localized the selected tariff-calendar weekday and preserved the horizontal
  timeline position, hour highlight and keyboard focus on 23/24/25-hour days.
- Added an import/export live-power chart with shared 1 kW support lines and an
  import-only cumulative quarter-energy chart with target and projection.
- Separated historical smoothed import from the dashed future-power assumption
  supplied by the engine; the final 15-minute average remains a labeled result,
  never an instantaneous power series.
- Aligned the last historical smoothing point with the backend forecast anchor
  using the engine's time-weighted, stale-limited coverage rules across varying
  sensor update intervals; gaps are never bridged.
- Made cumulative-energy history gap-aware: only fully supported, reconciled
  traces are connected, while incomplete/restarted traces show the authoritative
  backend point without fabricating earlier energy.
- Distinguished the verified distributor limit, contractual safety reference,
  temporary simulation threshold and actual engine operational target on both
  live charts (for example 3.50 - 0.20 versus 2.50 - 0.20 = 2.30 kW).
- Suppressed a projected line and user-facing value whenever its final imported
  energy is lower than energy already imported, while retaining the raw value
  internally for diagnosis and showing the reason.
- Added wrapping legends, explicit power/energy units, local time endpoints and
  non-overlapping reference labels for narrow Android light/dark layouts.
- Made live SVGs horizontally scroll inside their cards at their native 1120-pixel
  minimum drawing width, preserving labels and strokes without overflowing the
  full panel at 320/360/390/768-pixel viewport widths.
- Added GMT-offset chart times for unambiguous DST rollback intervals and a
  distinct forecast-anchor marker when post-rollover trace coverage cannot
  support a connected historical smoothing path.
- Preserved independent power/energy chart scroll positions and focused chart
  across 10-second refreshes, resetting them only for a meter or quarter change.
- Moved shared scrolling, legend and line styling into the permanent component
  stylesheet so the energy chart remains scrollable when no live trace exists.
- Exposed the existing temporary simulation threshold through setup and Options
  without changing dated assignments or confirmed archive statistics.
- Kept SQLite schema 5, configuration epochs, entity identities and archived
  measurements unchanged.

## [0.4.0] - 2026-10-18

- Added a guided six-step setup flow and fixed untouched dropdown defaults.
- Replaced the user-facing JSON editor with native dated B1-B5 assignment management.
- Added an automatically provisioned sidebar panel with no Lovelace, YAML, or resource setup.
- Added authenticated bounded WebSocket queries and responsive Overview, Today, and Tariff Calendar views.
- Added bounded next-lower-target detection while preserving per-quarter sustained forecasting.
- Preserved SQLite schema 5, provenance, V0.3 schedules, and entity identities.
- Corrected TODAY with a mathematically zero-centered shared-kW SVG: import-only
  demand is above zero, average export is below zero, and block-specific targets
  form a scaled stepped line across all 92/96/100 DST-aware quarters.
- Added live-quarter overlays and explicit UPCOMING/MISSING states without
  promoting projections to completed demand or confirmed exceedances.
- Unified daily and B1-B5 archive validity rules, separated partial energy, and
  excluded incomplete, provisional, unknown-configuration and simulation data
  from confirmed contractual statistics.
- Isolated multiple meters with entry-scoped archive requests, state resets and
  asynchronous generation guards; improved exact-quarter/DST archive navigation.
- Clarified lower-limit transitions versus forecasted reduction and added
  behavioral Python/Node regression suites plus frontend validation in CI.

## [0.3.0] - 2026-10-18

### Added

- Versioned Slovenian tariff calendar package with dedicated 2026–2030 rule
  modules, Europe/Ljubljana DST handling and official work-free holidays.
- Official URO 2026 and 2027 hourly block tables. The amended 2027 schedule is
  effective 1 January 2027.
- Explicit unavailable/provisional status for 2028–2030. The 2027 pattern is
  continued only when the user deliberately enables provisional rules.
- Five independent contracted-power settings, shared/per-block editing and an
  automatic V0.2 migration that copies the old target to B1–B5.
- Current/next block, season, day type, block target, transition countdown,
  calendar year, rule status and five contracted-power sensors.
- Daily, weekly, monthly, yearly, next-transition and upcoming-quarter calendar
  query methods for future dashboard use.
- SQLite schema 5 tariff, date-bound target and five-target configuration epochs.
- A documented, date-bound real-world 2026 B1–B5 validation fixture and backend
  contracted-power period model; fixture values remain user configuration and
  are never substituted for defaults or migrated V0.2 targets.
- A validated Options-flow JSON editor for multiple non-overlapping assignments,
  including separate 2026–2030 validity periods and immutable target provenance.

### Correctness

- Current and sustained import-only calculations select the target independently
  for every applicable fixed quarter.
- Runtime calculations, target sensors, sustained forecasts and SQLite rows use
  the dated assignment. Expiry leaves physical monitoring/archive active while
  contractual outputs explicitly become unavailable.
- Automated acceptance coverage verifies target selection, live advice,
  forecasts, tariff transitions and archived confirmed exceedances against the
  selected block target for the documented 2026 fixture.
- Historical measurements and targets are not rewritten when calendar metadata
  is added. Unknown rules/configuration and incomplete quarters cannot create
  confirmed exceedances.

### Fixed

- Missing or disabled provisional tariff rules no longer interrupt physical
  import/export metering, fixed-quarter completion, SQLite writes or checkpoint
  saving; only contractual forecasts and advice become unavailable.
- Provisional-rule exceedances are stored as estimates with an explicit reason
  and are excluded from legally confirmed exceedance counts.
- Calendar annotation preserves historical `exceeded` and `excess_kw` values;
  verification status and confirmed exceedance are stored separately.
- The last completed quarter is restored from SQLite for sensor presentation
  after restart, including its quality and provenance.
- Tariff-policy changes create configuration epochs and completed rows retain the
  policy that applied when they were recorded.
- V0.2 targets remain preserved in their legacy fields, but migration does not
  invent validity dates or treat them as a confirmed dated assignment.
- Recorder backfill now replays each historical source/sign configuration epoch
  and its effective contractual target instead of applying current settings to
  older measurements. Unknown or mixed provenance suppresses exceedance claims.
- Completed-quarter writes use an immutable as-of configuration snapshot.
  Mid-quarter target/source changes are recorded explicitly as mixed/unknown.
- Reload and shutdown drain archive work, retry quarters whose durable write did
  not complete, save the final checkpoint, and only then close SQLite.
- Archive summaries exclude incomplete and unavailable quarters from confirmed
  energy, demand maxima and averages; partial observed energy is reported
  separately. Legacy V0.2 rows migrate as unverified rather than producing
  potentially false contractual exceedances.

## [0.2.0] - 2026-10-18

### Added

- Permanent namespaced SQLite quarter archive with WAL, migrations, indexes,
  quality-ranked idempotent upserts, source epochs and restart checkpoints.
- Detailed Home Assistant recorder reconstruction using the same import-only
  integration engine as live calculations; gaps remain incomplete.
- Separate instant and 120-second-default smoothed import-only forecasts and
  two-decimal utilization entities.
- Editable source, sign, target, safety margin, smoothing, simulation threshold,
  retention and sustained-horizon options without deleting the config entry.
- Sustained CAN ADD, sustained MUST REDUCE and sustained forecast-quality
  entities for 15/30/60/120-minute horizons.
- Conservative sustained forecasting across a repeating recent signed path and
  a latest-instantaneous scenario, with per-quarter target-provider API.
- English and Slovenian UI strings, automated acceptance tests, V1.2 addendum
  and a real-Home-Assistant manual test plan.

### Correctness

- Contractual demand, utilization, forecasts, budgets, archive, reconstruction,
  exceedance detection and statistics use imported energy only. Export is stored
  separately and never nets imported demand.
- Simulation thresholds are not written into genuine contractual history.
- Full internal precision is retained; published percentages and power advice
  use two-decimal display precision.

### Not yet implemented

- Official Slovenian five-block tariff/calendar selection, dashboard tabs,
  notifications, public archive query/export UI and predictive PV/weather models.
- Real-device Home Assistant lifecycle and long-duration soak validation remain
  required before release.

## [0.1.1] - 2026-10-18

### Changed

- Optimized the transparent local-brand icons at 256 × 256 and 512 × 512
  (`icon.png` and `icon@2x.png`).

### Documentation

- Documented the known HACS frontend limitation for locally supplied custom-
  integration icons. Repository-side brand assets do not by themselves ensure
  that the HACS listing displays the icon.

## [0.1.0] - 2026-10-18

### Added

- HACS-compatible Home Assistant custom-integration skeleton and UI config flow.
- Signed live grid-power runtime with positive-import/negative-export normalization.
- Pure-Python source adapters for signed power, separate import/export power,
  import-only power, cumulative energy, and aligned completed quarters.
- Piecewise-constant time integration with explicit coverage, gaps, staleness,
  exact fixed-quarter boundary splitting, and Europe/Ljubljana DST mapping.
- Separate rolling signed/import-only means and fixed-quarter imported demand.
- Instant and smoothed forecasts, remaining budget, allowed import, CAN ADD,
  MUST REDUCE, and unrecoverable-quarter outputs.
- English and Slovenian setup/entity translations.
- Unit-test, Ruff, hassfest, and HACS validation workflows.

### Not yet implemented

- Runtime wiring for source modes other than one signed live power sensor.
- SQLite archive/backfill, tariff/calendar rules, dashboard, report API, alerts,
  and GitHub Pages documentation.
