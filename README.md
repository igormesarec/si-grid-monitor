# SI Grid Monitor

**Understand Slovenia's fixed 15-minute grid-import demand in Home Assistant.**

SI Grid Monitor is an independent, HACS-compatible custom integration for monitoring imported electricity, comparing each **fixed 15-minute quarter** with the applicable **B1–B5 contracted-power target**, and exploring historical energy, demand, quality and possible exceedances. It supports multiple meters and a built-in Home Assistant sidebar dashboard.

**Current documented version:** V0.9.5 beta. This is monitoring/decision-support software, **not** a utility-certified meter, guaranteed bill calculation, physical circuit protection or automated load controller.

## Start here

- **[Full documentation and project page](docs/index.md)** — what the system is, who benefits and how to use it.
- **[Five-minute getting started](docs/getting-started.md)** — find a source and verify your first measured quarter.
- **[HACS installation and upgrades](docs/installation.md)** — safe installation and archive-preserving updates.
- **[Choose source mode A/B/C/D](docs/source-modes.md)** — signed live power, separate import/export, import-only power or cumulative counters.
- **[Configuration reference](docs/configuration.md)** — every important setting and dated contracted-power limit.
- **[Dashboard walkthrough](docs/dashboard-guide.md)** — Overview, Today, Period, Blocks, Exceedances, History and Tariff Calendar.
- **[How the calculations work](docs/calculations.md)** and **[Forecasts](docs/forecasts.md)** — fixed-quarter import budget, CAN ADD / MUST REDUCE and sustained estimates.
- **[Troubleshooting](docs/troubleshooting.md)**, **[data quality](docs/data-quality.md)** and **[archive recovery](docs/history-and-archive.md)**.
- **[Slovenščina: hitri začetek](docs/sl/zacetek.md)** and **[slovenski vodnik](docs/sl/vodnik.md)**.

## Quick installation

1. In **HACS → Custom repositories**, add `https://github.com/igormesarec/si-grid-monitor` as an **Integration**.
2. Install SI Grid Monitor, **restart Home Assistant**.
3. Use **Settings → Devices & services → Add integration → SI Grid Monitor**.
4. Pick a real grid-connection source (W/kW or Wh/kWh), confirm its units and direction, and enter your actual date-bound contracted B1–B5 targets.
5. Open **SI Grid Monitor** in the HA sidebar. No Lovelace YAML or manually created derivative helper is required.

## Source choices

| Mode | Measurement | Important limitation |
|---|---|---|
| **A** | One signed grid-power W/kW sensor | Check polarity; import is normalized positive |
| **B** | Separate live import/export W/kW | Sensor timestamp alignment and freshness matter |
| **C** | One live import-only W/kW sensor | Export is **unknown** |
| **D** | Cumulative Wh/kWh import, net or separate counters | Derived power is a **past-interval average**, not instantaneous; net energy can conceal import/export reversals |

For live-power modes with sufficient data, the dashboard offers current-quarter and sustained load forecasts. For cumulative counters, the instantaneous/sustained advice may be unsupported; read [source limitations](docs/source-modes.md).

## What makes a result trustworthy?

- Quarters start at **:00, :15, :30, :45**. Import and export are tracked separately; exported energy never cancels imported energy for a quarter's import-demand calculation.
- **Contracted quarter energy (kWh) = target kW × 0.25 h**. A 4.200 kW limit corresponds to 1.050 kWh.
- Missing measurements, first readings after setup, restarts and counter ambiguity must not be silently turned into zero.
- Completed quarters are archived in an integration-owned, per-meter SQLite database. Normal removal **retains** the archive unless a separate explicit deletion process is authorized.
- **CAN ADD / SUSTAINED CAN ADD is a billing-budget estimate, never an electrical safety rating** for phases, cables, breakers or the grid connection.

## Capabilities and beta status

The project includes four input modes, a guided wizard, separate dated B1–B5 contracted limits, tariff-year and DST handling, a seven-tab dashboard, multiple-meters selection, forecasts for supported live modes, and a permanent history explorer. Real-world testing is continuing, especially counter-derived Mode D readings.

**Known V0.9.5 concern:** a short-lived implausible 402 kW derived Mode D power reading was observed in real testing. See [Troubleshooting](docs/troubleshooting.md). This documentation update does not change the underlying calculation code.

## More information for developers

- [System architecture](docs/developer-architecture.md)
- [Test and acceptance guide](docs/testing-and-validation.md)
- [Current limitations / roadmap](docs/limitations-and-roadmap.md)
- [Detailed manual test plan](MANUAL_TEST_PLAN.md)
- [V0.9 beta acceptance status](V0.9_BETA_ACCEPTANCE.md)
- [Source-mode V1.5 addendum](SPECIFICATION_V1.5_SOURCE_MODES_ADDENDUM.md)
- [Frozen master specification](SPECIFICATION.md) — unchanged

### Project documentation website

The Markdown guides are readable **directly on GitHub**. The repository includes an artifact-only **GitHub Pages preview workflow**, but public Pages deployment has **not** been enabled or claimed here. Publishing needs separate owner approval.

### Validation

GitHub Actions runs Python tests, frontend tests, browser layout tests, Ruff, hassfest and HACS validation. See [testing instructions](docs/testing-and-validation.md). Automated tests do not replace a backed-up real Home Assistant acceptance check.

---

**Safety and accuracy:** Always verify the actual source entity, B1–B5 contracted-power assignment and measured coverage before using results for decisions. SI Grid Monitor does not authorize higher instantaneous load than your electrical installation supports.
