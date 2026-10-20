# Changelog

All notable changes to SI Grid Monitor will be documented here.

## [Unreleased]

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
