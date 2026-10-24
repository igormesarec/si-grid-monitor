# Troubleshooting — symptoms, checks and safe remedies

Start with **Settings → Devices & services → SI Grid Monitor** to identify the correct meter entry and source entity. In **Developer Tools → States**, inspect the sensor's value, unit, state class, and timestamps. Keep screenshots and logs free of secrets.

| Symptom | Likely explanation | Check / remedy |
|---|---|---|
| No integration after installation | HA needs restart or stale cache | Restart Home Assistant after HACS install, refresh browser |
| Import and export reversed | Source polarity mismatched | Compare a known load with grid sensor; change Mode A sign option |
| Export shows Unknown | Normal for Mode C | Do **not** replace Unknown with 0.000 |
| Quarter incomplete after setup | Started in middle of quarter / downtime | Observe the next complete :00/:15/:30/:45 interval |
| Forecast smoothing unavailable | Less than selected window of valid recent data | Inspect source age and 120-second coverage; allow fresh readings |
| SUSTAINED CAN ADD unavailable in Mode C | Current-quarter energy gap, stale input or missing recent history | Try the next fully observed quarter; see [Forecasts](forecasts.md) |
| Very large allowed remainder | Tiny remaining fraction of quarter | It is billing-budget arithmetic, **not safe physical load advice** |
| Legacy Mode D notice after upgrade | Expected V1.0 behavior for an experimental counter entry | Back up, then explicitly reconfigure the same entry to A/B/C or keep its preserved archive |
| Duplicate source rejected during reconfiguration | Another entry already owns the same canonical source | Keep the existing owner or select a genuinely different W/kW source; do not merge/delete archives |
| Wh/kWh sensor rejected | V1.0 accepts live W/kW only | Select a real grid-power sensor; cumulative counters are future functionality |
| Different B4 limits on two meter entries | Independently configured assignments | Verify actual distributor notice for each physical connection |
| Partial zero appears in History | Data is incomplete or inferred | Inspect coverage and provenance; never treat missing energy as zero |
| Tariff year unverified | Future year without official bundled rule | Leave provisional off unless intentionally planning |
| Extra meter data seems wrong | Wrong active meter or stale UI | Select correct friendly-name meter and refresh |
| Old archive not attached to recreated meter | Different config-entry namespace | Restore original entry/backup; see [History](history-and-archive.md) |
| Permanent deletion not happening | Authorization expired or doesn't match entry | Native removal retains safely; recheck Options if deletion was actually intended |

## Report a reproducible bug

Include application version, chosen mode (A/B/C), raw HA sensor unit, source
update cadence, expected vs actual value, exact local quarter, quality and a
**redacted** screenshot. For a legacy migration issue, include the old mode and
new selected source without sharing the database. Never post your HA token or
private meter identifiers.

## Known acceptance boundary

Mode C testing showed sustained advice can recover after a complete quarter and
smoothing coverage return. Treat this as evidence of that workflow, not a
guarantee for all hardware cadences. Legacy Mode D counter anomalies motivated
its move to future research; V1.0 does not continue that runtime.

Read [Getting started](getting-started.md), [Data quality](data-quality.md) and [Limitations](limitations-and-roadmap.md).
# Missing or expiring contract warning

Warnings start 30 days before an assignment ends without an adjacent successor;
the final 7 days are urgent. The first uncovered local day is an error. A fully
covering successor beginning the next day suppresses the expiry warning.

Open **Contracts**, verify the active meter, then use **Open integration
settings**. Locate the meter name shown in the report and use Home Assistant's
**Configure** action. Add a successor or use Schedule change.

If confirmation reports a stale preview, another session changed the schedule
after your preview was generated. Nothing from that preview was saved. Reopen
the operation, review the current schedule and create a new preview.
Measurements continue during a gap, but SI Grid Monitor does not reuse an
expired value, substitute zero/4.800 kW, or confirm contractual exceedances.
