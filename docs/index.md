# SI Grid Monitor — understand your grid demand

**SI Grid Monitor** is an independent, HACS-compatible Home Assistant integration for monitoring Slovenia's fixed 15-minute imported-electricity demand. It helps you understand how much power you have imported in each billing interval, how this relates to your contracted power in tariff blocks B1–B5, and whether additional demand is likely to fit within the remaining quarter.

**Version documented: V0.9.5 beta.** This is monitoring and decision support, not a certified utility meter, automatic load controller, or electrical safety device.

## Why use it?

A household may have a heat pump, an EV charger, solar PV and ordinary appliances. A high instantaneous power reading is not identical to the **average grid import during a fixed 15-minute quarter**. SI Grid Monitor turns timely sensor readings into a transparent view of that quarter, its data quality, and an estimated remaining budget. It can also monitor a workshop, garage or second site, **one configuration entry and archive per meter**.

### The workflow at a glance

```text
Grid-connected sensor (W, kW, Wh or kWh)
       ↓ choose one of four source modes
Normalize sign, timestamps and units
       ↓
Import-only fixed 15-minute energy calculation
       ↓
Apply dated B1–B5 contracted limits and tariff rules
       ↓
Overview · Today · Period · Blocks · Exceedances · History · Calendar
       ↓
Permanent per-meter SQLite archive and measurement-quality audit
```

## Get started

1. [Install the integration](installation.md) from HACS and restart Home Assistant.
2. [Choose the appropriate sensor mode](source-modes.md). Live grid power is recommended where possible.
3. [Enter your distributor-assigned contracted-power limits](configuration.md), with their actual validity dates.
4. Check **SI Grid Monitor** in Home Assistant's sidebar.
5. [Learn to interpret the seven dashboard tabs](dashboard-guide.md) and [measurement-quality states](data-quality.md).

### What you'll see

| Display | Meaning |
|---|---|
| Import / export power | Current source-based value for live-power modes; a **past-interval estimate** for cumulative counters |
| Quarter import (kWh) | Recorded imported energy so far in the current :00/:15/:30/:45 quarter |
| Quarter demand (kW) | Imported energy divided by 0.25 hour, when complete evidence exists |
| CAN ADD THIS QUARTER | Modelled additional load for the remainder of this one interval, **not** electrical connection capacity |
| SUSTAINED CAN ADD | Conservative sustained-load estimate across the selected 15/30/60/120-minute horizon, only when supported |
| Quality and coverage | Whether readings justify an estimate or a confirmed contractual statement |
| History | Stored 15-minute summaries with original limits and provenance, not a fabricated power trace |

## Read the manual

**First use:** [Getting started](getting-started.md) · [Installation](installation.md) · [Source modes](source-modes.md) · [Configuration](configuration.md)

**Interpretation:** [Dashboard guide](dashboard-guide.md) · [Calculations](calculations.md) · [Forecasts](forecasts.md) · [Tariffs](tariffs.md) · [Data quality](data-quality.md)

**Manage and troubleshoot:** [History and archives](history-and-archive.md) · [Multiple meters](multiple-meters.md) · [Troubleshooting](troubleshooting.md) · [FAQ](faq.md) · [Glossary](glossary.md)

**Technical:** [Architecture](developer-architecture.md) · [Testing](testing-and-validation.md) · [Limitations and roadmap](limitations-and-roadmap.md)

**Slovenščina:** [Hiter začetek](sl/zacetek.md) · [Uporaba in razlaga](sl/vodnik.md)

Source: [GitHub repository](https://github.com/igormesarec/si-grid-monitor). The normative specification remains in the root `SPECIFICATION.md` and versioned addenda. The manual explains the currently implemented behavior; it does not modify those specifications.

> **Safety:** A positive CAN ADD estimate does not confirm that your wiring, breaker, meter connection, inverter, or individual phases can safely supply additional instantaneous power. Always follow electrical ratings and professional advice.
