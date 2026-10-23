# Glossary

| Term | Plain-language meaning |
|---|---|
| kW | Kilowatt, the rate of energy flow (power) |
| kWh | Kilowatt-hour, accumulated energy |
| Import | Electricity drawn from the public grid |
| Export | Electricity delivered to the public grid |
| Signed power | Positive or negative number indicating one of the two directions |
| Polarity | Setting defining whether a positive raw value means import or export |
| Quarter | Fixed 15-minute interval starting at :00, :15, :30 or :45 |
| Contracted power | Assigned kW limit for a tariff block, expressed as quarter-average import |
| B1–B5 | Slovenian network-tariff time blocks (classification is date/rule dependent) |
| Budget | Contracted kW multiplied by 0.25 hour, in kWh |
| Rolling average | Mean of recent readings across a moving time window, not necessarily aligned to a tariff quarter |
| Smoothing | Time-weighted recent valid power used in forecasting |
| CAN ADD | Estimated additional load fitting contractual energy budget under stated assumptions |
| MUST REDUCE | Estimated reduction needed under the model to meet target |
| Sustained horizon | Future 15/30/60/120 minutes evaluated across multiple quarters |
| Coverage | Portion of required time supported by usable readings |
| Stale | Latest sensor evidence older than supported freshness threshold |
| Incomplete | Measured or contractual evidence insufficient for a confirmed quarter |
| Provenance | Record of where a measurement, limit or derived result came from |
| Source epoch | Period of consistent source/polarity meaning |
| SQLite | Local database storing per-meter quarter summaries and related metadata |
| Checkpoint | Saved in-progress state for recovery after restart |
| HACS | Home Assistant Community Store, which installs supported community integrations |
| DST | Daylight saving time; causes 92/100-quarter local days at switchovers |
| Counter-derived | Historical V0.9.5/V0.9.6 provenance inferred from cumulative-energy changes; not an active V1.0 source |
| Legacy Mode D | Preserved experimental cumulative-counter configuration/history disabled in V1.0 |
| Provisional | Assumption for an unverified future tariff period, never a confirmed official rule |
| Simulation | Hypothetical threshold used for testing rather than official contract statistics |

See [Calculations](calculations.md) for equations and [Data quality](data-quality.md) for evidence categories.
