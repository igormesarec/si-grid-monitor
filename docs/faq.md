# Frequently asked questions

**Does this replace the official electricity meter or bill?** No. It computes monitoring and decision-support estimates from Home Assistant data. Official billing depends on the distributor's actual measurements and rules.

**Why 15 minutes?** Fixed quarter boundaries at :00/:15/:30/:45 are the basis of the monitored average imported-power quantity. A rolling 15-minute mean is not the same as that billing-aligned quarter.

**Why doesn't PV export cancel import?** Import-only contractual demand counts imported energy within the quarter. Energy exported at a different time does not erase energy already imported.

**My PV exports while a heat pump runs. Which power should I select?** Prefer an actual grid-connection power sensor, not separate house consumption or PV production.

**I only have a cumulative energy sensor.** Use Mode D, select appropriate counter behavior, and understand that derived kW is an **interval average**. A single bidirectional **net** counter does not confirm exact import-only quarter demand.

**Can I forecast heating/PV generation?** No weather-driven production or heat-pump schedule forecast is supplied. Sustained advice assumes present/recent electrical-load patterns continue.

**Why does CAN ADD appear but SUSTAINED CAN ADD does not?** Current-quarter arithmetic can be available while the more conservative sustained forecast is blocked by incomplete energy coverage or missing recent 120-second smoothing evidence.

**Why is my new meter's first quarter incomplete?** The meter's first valid timestamp may occur after the quarter began. Previously unmeasured minutes are not invented.

**Can I monitor multiple sites?** Yes: independent config entries and histories share one panel. Each needs its own verified contracted-power settings.

**Does the SQLite archive contain second-by-second power history?** No. It stores completed 15-minute summaries and provenance, not continuous instantaneous detail.

**Will HACS update delete my archive?** Ordinary updates are designed to preserve it. Back up first. Native removal retains it by default; permanent deletion is a separate, confirmed workflow.

**Why does a kW card show two decimal places?** V0.9.5 currently uses mixed display precision. A consistent three-decimal enhancement is requested separately; the documentation PR changes no numeric code.

**Is a high CAN ADD safe for breakers?** Not necessarily. It is a billing-budget estimate, not a phase/wiring/overcurrent rating.

**Where do I start?** [Getting started](getting-started.md).