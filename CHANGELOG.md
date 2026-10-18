# Changelog

All notable changes to SI Grid Monitor will be documented here.

## [Unreleased]

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
- SQLite schema 3 tariff provenance and five-target configuration epochs.

### Correctness

- Current and sustained import-only calculations select the target independently
  for every applicable fixed quarter.
- Historical measurements and targets are not rewritten when calendar metadata
  is added. Unknown rules/configuration and incomplete quarters cannot create
  confirmed exceedances.

### Fixed

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
