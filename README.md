# SI Grid Monitor

SI Grid Monitor is a HACS-compatible Home Assistant custom integration for
Slovenian fixed 15-minute grid-demand monitoring. V0.3 provides the setup
flow, import-only live calculations, sustained-load forecasting, and a permanent
SQLite quarter archive. It is an early development release, not the complete V1
product.

The authoritative MASTER PRODUCT SPECIFICATION V1.1 is preserved unchanged in
[`SPECIFICATION.md`](SPECIFICATION.md). V0.2 additions are recorded separately in
[`SPECIFICATION_V1.2_ADDENDUM.md`](SPECIFICATION_V1.2_ADDENDUM.md) and the V0.3
calendar rules are documented in
[`SPECIFICATION_V1.3_ADDENDUM.md`](SPECIFICATION_V1.3_ADDENDUM.md).
The user-supplied 2026 contracted-power acceptance case is documented separately
in [`REAL_WORLD_VALIDATION.md`](REAL_WORLD_VALIDATION.md); its values are test
fixtures, never installation defaults.

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

## V0.3 status

| Feature | Planned | Implemented | Tested | HA-verified |
|---|:---:|:---:|:---:|:---:|
| HACS/manifest/config-flow skeleton | Yes | Yes | Yes (CI) | No |
| Local transparent brand icons (1×/2×) | Yes | Yes | PNG validated | No |
| One signed live W/kW power source | Yes | Yes | Yes | No |
| Separate import/export adapter design | Yes | Pure Python only | Yes | No |
| Import-only adapter design | Yes | Pure Python only | Yes | No |
| Cumulative-energy adapter design | Yes | Pure Python only | Yes | No |
| Aligned completed-quarter adapter design | Yes | Pure Python only | Yes | No |
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
| Six-tab professional dashboard | V0.4-V0.7 | No | No | No |
| GitHub Pages and HACS default listing | V0.8 | No | No | No |

“Pure Python only” means that the adapter and its validation contract exist but
the Home Assistant config entry and entity lifecycle for that source mode do
not. V0.3 rejects those choices in the setup flow instead of creating a partly
working or misleading configuration.

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

Configure one shared value or B1–B5 independently in integration options. On a
V0.2 upgrade the previous target is copied into all five blocks. Current-quarter
calculations use the active block; sustained forecasts classify and select the
target for every future quarter separately.

Contracted-power assignments are user-owned and date-bound independently from
tariff calendar rules. The backend period model supports different B1–B5 values
for non-overlapping future validity periods, retaining provenance and the date a
record was issued. The V0.3 Home Assistant options UI edits the currently
effective five values; advance scheduling of future assignments is not yet an
options-flow feature. A 2026 assignment must not be assumed valid for 2027–2030.

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
   its sign direction, and explicitly enter your contractual target.
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

- Only source mode A (one signed live power entity) is wired into Home Assistant.
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
- Date-bound contracted-power periods are represented and tested in the backend,
  but V0.3 does not yet provide an options-flow editor for scheduling a future
  assignment before its effective date.
- Completed quarters retain the tariff policy and rule status that applied when
  they were written. Changing provisional-calendar policy does not relabel old
  rows. Legacy rows without policy provenance remain explicitly unknown.
- The archive is integration-owned, namespaced per config entry, WAL-backed and
  retained forever by default. Removal policy and export tooling are not yet UI
  features; uninstalling the integration does not promise archive deletion.
- Dashboard tabs, the graphical Overview card, alerts, and public archive
  query/export services are not implemented. The calendar query API is currently
  a backend Python interface for later dashboard work.
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
- **V0.5:** PERIOD and BLOCKS with Hour/Day/Week/Month/Year/Custom selection and
  quarter-peak-preserving aggregation.
- **V0.6:** EXCEEDANCES with granular individual-quarter reporting.
- **V0.7:** HISTORY, coverage/quality exploration, pagination, and long-term
  archive query API.
- **V0.8:** reviewed tariff update notices, complete English/Slovenian
  localization, docs, GitHub Pages, HACS listing, upgrade/reinstall lifecycle.
- **V0.9:** beta and clean-HA verification.
- **V1.0:** stable release after the full specification acceptance matrix passes.

## License

MIT — see [`LICENSE`](LICENSE).
