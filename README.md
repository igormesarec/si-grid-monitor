# SI Grid Monitor

**Understand Slovenia's fixed 15-minute grid-import demand in Home Assistant.**

SI Grid Monitor is an independent, HACS-compatible integration that monitors
imported electricity, compares each fixed quarter with the applicable B1–B5
contracted-power target, and preserves auditable quarter history. It is useful
for homes and small sites with heat pumps, EV charging, solar PV or other loads
that need clearer visibility into quarter-hour grid import.

**Release status:** V1.0.0 three-mode code is now merged into `main` (PR #16),
but remains a **release candidate** pending real Home Assistant acceptance.
V0.9.6 is the preceding published development version; do not assume V1.0 is installed.

This is monitoring and decision-support software—not a distributor-certified
meter, guaranteed bill calculation, physical protection device or automatic
load controller.

## V1.0 capabilities

- Import-only contractual demand for exact local `:00/:15/:30/:45` quarters.
- Five B1–B5 tariff blocks and date-bound contracted-power assignments.
- Instantaneous, time-weighted smoothed and sustained load forecasts when their
  measurement and contract prerequisites are satisfied.
- Clear CAN ADD / MUST REDUCE estimates for billing-energy budgets.
- Seven-tab authenticated Home Assistant sidebar dashboard.
- Permanent, per-meter schema-6 SQLite history with quality and provenance.
- Multiple independent meter entries behind one shared sidebar panel.
- Three-decimal kW/kWh presentation without reducing stored precision.
- English and Slovenian configuration and dashboard terminology.

Exported energy is recorded separately where the selected source measures it.
It never offsets imported energy when calculating contractual quarter demand.

## Supported V1.0 measurement modes

| Mode | Source | Import | Export | Forecasting |
|---|---|---|---|---|
| **A** | One signed W/kW grid-power sensor | Measured | Measured | Supported with valid fresh coverage |
| **B** | Separate nonnegative import and export W/kW sensors | Measured separately | Measured separately | Supported when both inputs are valid and aligned |
| **C** | One nonnegative import-only W/kW sensor | Measured | **Unknown** | Supported conservatively, without export-surplus credit |

Positive normalized power means grid import; negative means grid export. Mode C
does not turn unknown export into measured `0.000`.

### Future functionality: cumulative energy counters

Cumulative energy-counter support, including import-only counters,
bidirectional net-energy counters and separate import/export counters, is
reserved for future development. It requires additional research into
measurement intervals, quarter-boundary alignment, counter resets, quantization
and contractual demand accuracy. No implementation date is committed.

Mode D was experimental in V0.9.5/V0.9.6. It is not selectable or active in the
V1.0 release candidate. Historical counter-derived rows remain readable with
their original quality and provenance.

## Start here

- **[Documentation home](docs/index.md)** — project introduction and complete manual.
- **[Installation and safe upgrades](docs/installation.md)** — HACS installation,
  V0.9.6 → V1.0 migration, backup and rollback.
- **[Getting started](docs/getting-started.md)** — configure and verify the first quarter.
- **[Source Modes A/B/C](docs/source-modes.md)** — choose the correct live-power input.
- **[Configuration reference](docs/configuration.md)** — contracts, margins,
  smoothing, simulation, retention and removal.
- **[Dashboard guide](docs/dashboard-guide.md)** — Overview, Today, Period,
  Blocks, Exceedances, History and Tariff Calendar.
- **[Calculations](docs/calculations.md)** and **[forecasts](docs/forecasts.md)** —
  equations, quality gates and limitations.
- **[History and archive safety](docs/history-and-archive.md)**,
  **[data quality](docs/data-quality.md)** and
  **[troubleshooting](docs/troubleshooting.md)**.
- **[Slovenščina: hiter začetek](docs/sl/zacetek.md)** and
  **[slovenski vodnik](docs/sl/vodnik.md)**.

No project screenshots are currently committed to the repository. The included
brand icons are not presented as Home Assistant screenshots.

## Installation summary

1. In **HACS → Custom repositories**, add
   `https://github.com/igormesarec/si-grid-monitor` as an **Integration**.
2. Install SI Grid Monitor and restart Home Assistant.
3. Open **Settings → Devices & services → Add integration → SI Grid Monitor**.
4. Name the meter, choose Mode A, B or C, and select the real grid W/kW sensor(s).
5. Configure the actual validity dates and B1–B5 contracted-power values.
6. Open **SI Grid Monitor** from the automatically registered sidebar entry.

No Lovelace YAML, manual JavaScript registration, external database or Home
Assistant credentials are required.

## V0.9.6 → V1.0 upgrade

Back up Home Assistant and `.storage/si_grid_monitor_*.db` before testing the
release candidate. Existing Mode A/B/C entries retain their entry identity,
entities and archive namespace.

A legacy Mode D entry is detected before runtime construction. V1.0 does not
poll its Wh/kWh source or reinterpret it as W/kW. Its configuration, schema-6
database, checkpoints, epochs and historical rows remain preserved, and Home
Assistant displays an unsupported-mode notice.

Use **Reconfigure** to explicitly choose Mode A, B or C. The integration
validates the new W/kW source and rejects it if another SI Grid Monitor entry
already owns the same canonical source identity. A successful migration keeps
the existing config-entry ID and archive namespace, updates `entry.unique_id`
to the accepted live source, and begins a new source epoch. Old Mode D rows are
not merged into the new epoch or silently promoted to confirmed measurements.
Deleting the entry is not required.

See the [full backup-first migration procedure](docs/installation.md).

## Dashboard and evidence

The dashboard provides:

1. **Overview** — live quarter, import/export, forecasts and budget advice.
2. **Today** — 92/96/100 DST-aware quarter slots and B1–B5 summaries.
3. **Period** — hour/day/week/month/year/custom aggregation.
4. **Blocks** — historical block statistics and quarter drill-down.
5. **Exceedances** — confirmed events, near-limit and unconfirmed records.
6. **History** — paginated schema-6 archive, quality and provenance.
7. **Tariff Calendar** — block schedule, rule status and transitions.

Completed valid, incomplete, unavailable, missing-after-monitoring,
pre-monitoring, live and upcoming intervals remain distinct. Partial observed
energy is separate from confirmed totals. Unknown values remain unavailable,
never manufactured as zero.

## Safety and limitations

- **CAN ADD is a mathematical 15-minute energy-budget estimate.** It is not
  permission to exceed breaker, phase, cable, inverter or connection ratings.
- Forecasts repeat recent or current behavior; they do not predict weather,
  appliance schedules or PV production.
- Home Assistant samples can produce reconstructed estimates that differ from
  official distributor measurements.
- Official 2026/2027 tariff tables are versioned. Unverified future years are
  unavailable by default; opt-in provisional rules cannot create confirmed
  contractual statistics.
- Ordinary integration removal retains the archive. Permanent deletion requires
  fresh entry-specific confirmation and can create a backup.

## Technical and project documentation

- [Tariff rules and dated contracts](docs/tariffs.md)
- [Multiple meters](docs/multiple-meters.md)
- [FAQ](docs/faq.md) and [glossary](docs/glossary.md)
- [Developer architecture](docs/developer-architecture.md)
- [Testing and validation](docs/testing-and-validation.md)
- [Limitations and roadmap](docs/limitations-and-roadmap.md)
- [Historical V0.8 implementation status](V0.8_IMPLEMENTATION_STATUS.md)
- [V1.0 source-mode capability matrix](SOURCE_MODE_CAPABILITY_MATRIX.md)
- [Frozen master specification](SPECIFICATION.md)
- V1.0 scope clarification in `SPECIFICATION_V1.6_V1_SCOPE_ADDENDUM.md`
  (introduced by PR #16)

The Markdown guides are readable directly on GitHub. A workflow may build a
Pages preview artifact, but this documentation task does **not** publish or
enable GitHub Pages.

## License

MIT — see [LICENSE](LICENSE).
