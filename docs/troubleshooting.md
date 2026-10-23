# Troubleshooting — symptoms, checks and safe remedies

Start with **Settings → Devices & services → SI Grid Monitor** to identify the correct meter entry and source entity. In **Developer Tools → States**, inspect the sensor's value, unit, state class, and timestamps. Keep screenshots and logs free of secrets.

| Symptom | Likely explanation | Check / remedy |
|---|---|---|
| No integration after installation | HA needs restart or stale cache | Restart Home Assistant after HACS install, refresh browser |
| Import and export reversed | Source polarity mismatched | Compare a known load with grid sensor; change Mode A sign option |
| Export shows Unknown | Normal for Mode C and import-only Mode D | Do **not** replace Unknown with 0.000 |
| Quarter incomplete after setup | Started in middle of quarter / downtime | Observe the next complete :00/:15/:30/:45 interval |
| Forecast smoothing unavailable | Less than selected window of valid recent data | Inspect source age and 120-second coverage; allow fresh readings |
| SUSTAINED CAN ADD unavailable in Mode C | Current-quarter energy gap, stale input or missing recent history | Try the next fully observed quarter; see [Forecasts](forecasts.md) |
| Very large allowed remainder | Tiny remaining fraction of quarter | It is billing-budget arithmetic, **not safe physical load advice** |
| Mode D shows no real-time trace | Cumulative counters have interval averages, not live power | Use Mode A/B/C if instantaneous forecasting is needed |
| Mode D shows 402 kW | Suspicious very-short interval derivative, quantization, timestamp or reset | Do not rely on result; inspect paired counter values, timestamps, unit and reset attributes |
| Derived power flickers between zero and high values | Counter update intervals too short relative to resolution | Review counter cadence/resolution and V0.9.5 Mode D limitations |
| Counter direction wrong | Wrong bidirectional polarity | Select increase-means-import or reverse and confirm with a known event |
| Net-counter exact demand unavailable | Net energy can hide import/export reversals | Use a dedicated import counter or live grid-power sensor |
| Different B4 limits on two meter entries | Independently configured assignments | Verify actual distributor notice for each physical connection |
| Partial zero appears in History | Data is incomplete or inferred | Inspect coverage and provenance; never treat missing energy as zero |
| Tariff year unverified | Future year without official bundled rule | Leave provisional off unless intentionally planning |
| Extra meter data seems wrong | Wrong active meter or stale UI | Select correct friendly-name meter and refresh |
| Old archive not attached to recreated meter | Different config-entry namespace | Restore original entry/backup; see [History](history-and-archive.md) |
| Permanent deletion not happening | Authorization expired or doesn't match entry | Native removal retains safely; recheck Options if deletion was actually intended |

## Report a reproducible bug

Include application version, chosen mode (A/B/C/D), raw HA sensor unit/state_class, source update cadence, expected vs actual value, exact local quarter, quality and a **redacted** screenshot. For Mode D, at least two successive raw counter values with timestamps are essential. Never post your HA token or database.

## Known test observations, not solved code changes

V0.9.5 real HA testing observed a brief **402.06 kW** counter-derived display and missing instant-style graphs in Mode D. These concerns remain under investigation and the documentation PR does **not** fix them.

A separate Mode C test showed that the sustained forecast became available after full quarter and smoothing coverage returned. Treat this as evidence of that specific workflow, not a guarantee for all sensor cadences.

Read [Getting started](getting-started.md), [Data quality](data-quality.md) and [Limitations](limitations-and-roadmap.md).