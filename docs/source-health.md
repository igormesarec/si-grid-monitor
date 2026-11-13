# Source-health diagnostics

V1.0.6 records **state transitions**, not every source report. Each meter has an
independent source-health timeline in its own SQLite namespace. Repeated reports
with the same state, reason, source and source epoch reuse the open interval, so
normal measurement cadence does not create unbounded event chatter.

## States and evidence

The report distinguishes healthy, stale, unavailable, invalid value, missing
source entity, source-timestamp mismatch, configuration transition, runtime
restarting, runtime stopped and unknown. Timestamps are UTC identities and are
also presented in Europe/Ljubljana time.

An interval start is the earliest time the integration observed that state. It
is not necessarily the physical instant a device failed. An open interval has
no known end. After an unclean restart, the integration closes previous evidence
with **end unknown at restart** rather than inventing a duration across downtime.

## Relationship to quarter quality

Source-health incidents and completed-quarter summaries are different evidence:

- Quarter completeness asks whether a completed fixed interval has evidence
  sufficient for a valid measurement result.
- Measurement-time coverage is measured seconds divided by applicable monitored
  seconds.
- A quarter's `gap_seconds` is an aggregate produced by the calculation engine.
- A source-health interval is an observed runtime state transition.

An incident can overlap an incomplete quarter, but its duration is never assumed
to equal the quarter's gap seconds. Historical quarters created before V1.0.6
may have no incident detail; the dashboard says so explicitly.

## Recurring observations

The report may group interruptions that recur in the same local half-hour on at
least two dates. This is descriptive correlation only. It does not diagnose a
router, inverter, integration, network or power-supply cause.

## CSV exports and access

Administrators can export a bounded date range as incident, daily-quality or
incomplete-quarter CSV. Values that spreadsheet software could interpret as a
formula are neutralized. Exports are generated from the selected meter only,
contain no write operation and are limited to one year. The selected health
state and source epoch are applied to incident exports; the source epoch is
also applied to quality and incomplete-quarter exports. Incident rows are read
in bounded 200-row SQLite pages, while the resulting CSV is complete up to the
explicit 10,000-row export ceiling. A larger or concurrently changing result is
rejected with instructions to narrow the filters or retry; it is never returned
as a silently truncated CSV. Do not publish exports without reviewing source
entity IDs and provenance fields.

Dashboard pages remain bounded, but their summary counts, observed durations
and affected-quarter metrics use the complete filtered range. A page containing
50 or 200 visible incidents therefore does not limit the period summary.

## Brief outage and recovery

The runtime queues health changes in observation order. If the database write
for one state is still running, a later unavailable and recovery transition
retain their individual timestamps and are written afterward. Each write has a
bounded retry sequence; an unsuccessful transition remains queued ahead of
newer states instead of being skipped.

The live chart retains bounded interruption windows after recovery. A recovery
inside the normal 60-second sample-validity allowance therefore starts a new
measured/smoothed visual segment and does not reconnect the pre-outage trace
across the observed unavailable interval. This affects visualization and
diagnostic provenance only; calculation and energy integration are unchanged.

## Troubleshooting sequence

1. Confirm the selected meter and current source entity.
2. Compare the last valid measurement with Home Assistant's source state time.
3. Inspect the incident reason and source epoch.
4. Inspect affected quarters separately; do not equate incident duration with
   missing measurement seconds.
5. If the issue spans a restart, treat exact downtime duration as unknown.
6. Preserve the archive and diagnostics before reconfiguring the source.

Source Health is diagnostic reporting. It does not change the source freshness
threshold, contractual calculation, tariff classification or archived history.
