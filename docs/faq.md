# Frequently asked questions

**Does this replace the official electricity meter or bill?** No. It computes monitoring and decision-support estimates from Home Assistant data. Official billing depends on the distributor's actual measurements and rules.

**Why 15 minutes?** Fixed quarter boundaries at :00/:15/:30/:45 are the basis of the monitored average imported-power quantity. A rolling 15-minute mean is not the same as that billing-aligned quarter.

**Why doesn't PV export cancel import?** Import-only contractual demand counts imported energy within the quarter. Energy exported at a different time does not erase energy already imported.

**My PV exports while a heat pump runs. Which power should I select?** Prefer an actual grid-connection power sensor, not separate house consumption or PV production.

**I only have a cumulative energy sensor.** V1.0 does not support Wh/kWh
counters as active inputs. Use a suitable live grid W/kW sensor for Mode A/B/C,
or wait for future counter research. Do not create a claim of instantaneous
power or confirmed demand from an ambiguous net counter.

**Can I forecast heating/PV generation?** No weather-driven production or heat-pump schedule forecast is supplied. Sustained advice assumes present/recent electrical-load patterns continue.

**Why does CAN ADD appear but SUSTAINED CAN ADD does not?** Current-quarter arithmetic can be available while the more conservative sustained forecast is blocked by incomplete energy coverage or missing recent 120-second smoothing evidence.

**Why is my new meter's first quarter incomplete?** The meter's first valid timestamp may occur after the quarter began. Previously unmeasured minutes are not invented.

**Can I monitor multiple sites?** Yes: independent config entries and histories share one panel. Each needs its own verified contracted-power settings.

**Does the SQLite archive contain second-by-second power history?** No. It stores completed 15-minute summaries and provenance, not continuous instantaneous detail.

**Will HACS update delete my archive?** Ordinary updates are designed to preserve it. Back up first. Native removal retains it by default; permanent deletion is a separate, confirmed workflow.

**How are values formatted?** V1.0 displays kW and kWh with three decimals while
retaining full internal and archive precision. Unknown remains unavailable, not
`0.000`.

**What happens to my V0.9.6 Mode D entry?** It is disabled without deleting its
archive. Home Assistant shows a notice. Back up first, then explicitly
reconfigure the same entry to A/B/C or retain the historical database.

**Is a high CAN ADD safe for breakers?** Not necessarily. It is a billing-budget estimate, not a phase/wiring/overcurrent rating.

**Where do I start?** [Getting started](getting-started.md).
