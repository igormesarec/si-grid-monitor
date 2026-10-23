# SI Grid Monitor

SI Grid Monitor is a HACS-compatible Home Assistant integration for Slovenian
fixed 15-minute grid-demand monitoring. V1.0 is intentionally focused on three
live-power input modes and one shared, import-only calculation/archive engine.

The frozen master specification remains unchanged in
[`SPECIFICATION.md`](SPECIFICATION.md). The approved V1.0 scope clarification is
in [`SPECIFICATION_V1.6_V1_SCOPE_ADDENDUM.md`](SPECIFICATION_V1.6_V1_SCOPE_ADDENDUM.md).
Earlier addenda and implementation reports remain as historical records; they
do not override the V1.0 supported-mode list.

## Supported measurement modes

| Mode | Source | Import | Export | Live forecasts |
|---|---|---:|---:|---:|
| A | One signed W/kW grid-power sensor | Measured | Measured | Yes |
| B | Separate nonnegative import and export W/kW sensors | Measured | Measured | Yes |
| C | One nonnegative import-only W/kW sensor | Measured | Unknown | Yes, conservatively |

Positive internal power always means grid import; negative means grid export.
Mode B retains separate import and export evidence, so exported energy never
offsets imported contractual demand. Mode C reports export as unknown, never as
measured zero.

### Future functionality: cumulative energy counters

Cumulative energy-counter support, including import-only counters,
bidirectional net-energy counters and separate import/export counters, is
reserved for future development. It requires additional research into
measurement intervals, quarter-boundary alignment, counter resets, quantization
and contractual demand accuracy. No implementation date is committed.

Mode D was experimental in V0.9.5/V0.9.6 and is not selectable or active in
V1.0. Historical counter-derived archive rows remain readable with their
original quality and provenance.

## Installation

1. Install SI Grid Monitor through HACS and restart Home Assistant.
2. Add it from **Settings → Devices & services**.
3. Name the meter, choose Mode A, B or C, and select W/kW grid sensor(s).
4. Confirm direction and configure the dated B1–B5 contracted-power assignment.
5. Open **SI Grid Monitor** from the automatically registered sidebar entry.

No Lovelace YAML, JavaScript resource registration, external database, or Home
Assistant credentials are required. Multiple config entries share one sidebar
panel while keeping independent entry IDs, entities, configuration epochs and
SQLite archives. The active meter selector is sticky, remembers the last valid
selection in local browser storage, and clears entry-specific state before a
switch.

## Upgrade from a V0.9.5/V0.9.6 Mode D entry

V1.0 recognizes `source_mode=cumulative_energy` before runtime construction. It
does not open a Mode D measurement pipeline, subscribe to the Wh/kWh entity,
reinterpret the counter as W/kW, mutate the config entry, or rewrite/delete its
schema-6 archive. Home Assistant shows a repair notice explaining that the
meter needs a supported live-power source.

Use the integration's **Reconfigure** action to select Mode A, B or C. This
preserves the existing config-entry ID and archive namespace while subsequent
accepted live-power measurements begin a new source/configuration epoch. The
legacy counter fields and historical rows remain preserved. If reconfiguration
is not appropriate, create a separate supported meter and keep the legacy
database; deletion is never required for upgrade.

## Dashboard

The authenticated dashboard contains seven tabs:

- **Overview:** live quarter, import/export, forecasts, energy budgets, CAN ADD
  and MUST REDUCE, archive navigation and upcoming tariff transitions.
- **Today:** 92/96/100 fixed quarters, live/upcoming/missing states, five block
  summaries and exact quarter selection.
- **Period:** Hour/Day/Week/Month/Year/Custom aggregation with truthful coverage.
- **Blocks:** B1–B5 statistics and paginated quarter analysis using original targets.
- **Exceedances:** confirmed events, near-limit diagnostics and unconfirmed quality.
- **History:** paginated schema-6 archive, provenance, coverage and exact-quarter detail.
- **Tariff Calendar:** Europe/Ljubljana block classification, DST and rule status.

Completed valid, incomplete, unavailable, missing after monitoring began,
pre-monitoring, live and upcoming intervals are kept distinct. Partial observed
energy is separate from confirmed totals. Pre-monitoring intervals are not
counted as missing. Contractual utilization and valid-quarter coverage are not
presented as measurement-time coverage.

Power and energy values display with three decimals (for example `4.200 kW` and
`0.024 kWh`) while calculations and SQLite storage retain full precision.
Percentages and integer counts retain their appropriate formats. Unknown values
remain unavailable, never `0.000`.

## Billing method and safety

- Fixed quarters follow local `:00/:15/:30/:45` boundaries with canonical UTC
  identity across Europe/Ljubljana DST transitions.
- Contractual demand is imported quarter energy divided by 0.25 h.
- Export is recorded separately and never cancels import.
- Rolling signed 15-minute power remains a separate flow metric.
- Stale or missing readings are not filled with zero or fabricated consumption.
- Confirmed exceedances require valid measurements, known historical target and
  confirmed tariff/configuration provenance.
- **CAN ADD is remaining 15-minute energy-budget headroom, not physical breaker,
  phase, wiring, connection or inverter capacity.**

The official 2026/2027 Slovenian tariff schedules are versioned. Years without a
verified official schedule are unavailable by default; explicitly enabled
provisional rules remain visibly provisional and cannot create confirmed legal
statistics. Dated contracted-power assignments do not silently carry forward.

## Archive safety

The integration-owned SQLite schema remains version 6, WAL-backed and isolated
per config entry. Normal restart, reload, HACS update, source unavailability and
integration removal do not delete the archive. Permanent deletion requires the
entry-specific workflow, exact fresh confirmation and optional backup; the
authorization expires after ten minutes.

Old rows retain original source epoch, target, tariff rule, simulation state,
coverage, quality and exceedance eligibility. V1.0 does not recalculate or
promote historical Mode D data.

## Development validation

```powershell
.venv\Scripts\python -m pytest --basetemp=.test-v10
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .
.venv\Scripts\python -m compileall custom_components tests
node --test frontend_tests/*.test.mjs
npm run test:layout
```

GitHub Actions additionally run hassfest and HACS validation. Automated success
does not prove real Home Assistant, Android Companion App, HACS upgrade or live
meter acceptance; follow [`MANUAL_TEST_PLAN.md`](MANUAL_TEST_PLAN.md).

## Branding note

Transparent 256×256 and 512×512 repository assets are included. This does not
claim to fix the known HACS custom-integration icon issue; see
[`hacs/frontend#949`](https://github.com/hacs/frontend/pull/949).

## Release status

V1.0.0 remains a release candidate until the manual Home Assistant upgrade and
clean-install checklist passes. No release, tag, deployment or merge is implied
by CI success. See [`V1.0_IMPLEMENTATION_STATUS.md`](V1.0_IMPLEMENTATION_STATUS.md).
Earlier milestone evidence remains available in
[`V0.8_IMPLEMENTATION_STATUS.md`](V0.8_IMPLEMENTATION_STATUS.md) and the other
versioned status reports; those files describe historical releases, not the
current V1.0 feature scope.

## License

MIT — see [`LICENSE`](LICENSE).
