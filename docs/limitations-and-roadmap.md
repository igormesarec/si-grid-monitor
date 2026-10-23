# Current limitations and roadmap

**V1.0.0 code is merged into `main` via PR #16 but remains a release candidate pending real Home Assistant acceptance.**
SI Grid Monitor is monitoring and decision-support software, not a certified
utility meter, physical protection device, guaranteed bill predictor or control
system.

## Limits of interpretation

- Power sources can be stale or incomplete; results cannot be made certain by formatting to additional decimal places.
- Import-only billing excludes export compensation inside the quarter; do not subtract exported energy at different times.
- Home Assistant power sampling is reconstructed evidence, not distributor-meter-exact billing data.
- Source availability, smoothing coverage, tariff validity and configuration epochs can block forecasts or confirmed exceedances.
- Historical SQLite summaries cannot reconstruct an exact instantaneous power trace without separate timestamped source evidence.
- Power-headroom recommendations do not validate circuit, phase, breaker or wiring limits.

## Release-candidate observations

- Mode C recovered sustained CAN ADD after a newly created meter reached sufficient valid quarter and smoothing coverage.
- HISTORY provenance is technically accurate but sometimes verbose on narrow mobile layouts.

Legacy Mode D testing exposed counter timestamp, boundary, reset and quantization
uncertainty. V1.0 removes Mode D from active functionality rather than claiming
those research questions are solved.

## Possible follow-up work (not implemented here)

- Translate raw unavailable reason codes into user-friendly messages.
- Continue manual acceptance tests and maintain authoritative documentation for tariff-rule updates.

### Future functionality: cumulative counters

Cumulative energy-counter support, including import-only counters,
bidirectional net-energy counters and separate import/export counters, is
reserved for future development. It requires additional research into
measurement intervals, quarter-boundary alignment, counter resets, quantization
and contractual demand accuracy. No implementation date is committed.

V1.0 code is merged, but the release candidate is not yet validated or declared stable.
