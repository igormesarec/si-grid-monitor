# Changelog

All notable changes to SI Grid Monitor will be documented here.

## [Unreleased]

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
