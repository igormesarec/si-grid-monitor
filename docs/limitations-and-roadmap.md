# Current limitations and roadmap

**V0.9.5 is a beta.** It is a Home Assistant monitoring and decision-support project, **not** a certified utility meter, physical protection device, guaranteed bill predictor or control system.

## Limits of interpretation

- Power sources can be stale or incomplete; results cannot be made certain by formatting to additional decimal places.
- Import-only billing excludes export compensation inside the quarter; do not subtract exported energy at different times.
- Counter-derived Mode D power is a retrospective **interval average**, not a live instantaneous value.
- A single bidirectional *net* counter cannot uniquely reconstruct import-only energy if flows reverse between updates.
- Source availability, smoothing coverage, tariff validity and configuration epochs can block forecasts or confirmed exceedances.
- Historical SQLite summaries cannot reconstruct an exact instantaneous power trace without separate timestamped source evidence.
- Power-headroom recommendations do not validate circuit, phase, breaker or wiring limits.

## V0.9.5 real-world observations

- Mode C recovered sustained CAN ADD after a newly created meter reached sufficient valid quarter and smoothing coverage.
- A Mode D test showed a short-lived **402.06 kW** derived power display and subsequent zero values with very small accumulated energy. Counter timestamps, measurement cadence, resolution and derivative plausibility need further validation.
- Mode D's current dashboard can show unavailable instantaneous-style charts and a misleading stale-source wording because it does not carry a true instantaneous sample.
- HISTORY provenance is technically accurate but sometimes verbose on narrow mobile layouts.

These are reported observations, **not code fixes delivered by this manual**.

## Possible follow-up work (not implemented here)

- Investigate and safely handle short counter intervals and quantization in Mode D.
- Improve interval-based Mode D chart and measurement-kind labels.
- Translate raw unavailable reason codes into user-friendly messages.
- Standardize display precision to **three decimal places** for kW and kWh where appropriate, without rounding internal calculations.
- Continue manual acceptance tests and maintain authoritative documentation for tariff-rule updates.

Do not represent these proposed changes as already merged or released.