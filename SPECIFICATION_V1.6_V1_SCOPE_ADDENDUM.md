# SI Grid Monitor V1.0 Scope Clarification Addendum

Status: approved product-scope clarification for V1.0.0. This file does not
modify the frozen `SPECIFICATION.md`.

## Active measurement sources

V1.0 supports exactly three live-power source modes:

1. Mode A — one signed live grid-power sensor in W or kW.
2. Mode B — separate nonnegative import and export live-power sensors in W or kW.
3. Mode C — one nonnegative import-only live-power sensor in W or kW.

All three use the established common import-only calculation, forecasting,
tariff and schema-6 archive engine. Existing entry IDs, entity unique IDs,
configuration epochs and immutable historical provenance remain compatible.

## Removed experimental source

Mode D cumulative energy counters are not active V1.0 functionality. New setup,
options, runtime listeners, counter conversion, generated derived-power entities
and live counter charts do not expose or execute it.

Legacy V0.9.5/V0.9.6 entries are recognized before runtime startup and disabled
without interpreting Wh/kWh as power, opening a counter pipeline, rewriting
configuration, or deleting/reclassifying archive rows. An explicit A/B/C
reconfiguration preserves the entry/archive namespace and begins a new source
epoch.

## Future functionality

Cumulative energy-counter support, including import-only counters,
bidirectional net-energy counters and separate import/export counters, is
reserved for future development. It requires additional research into
measurement intervals, quarter-boundary alignment, counter resets, quantization
and contractual demand accuracy. No implementation date is committed.
