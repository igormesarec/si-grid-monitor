# V1.0 source-mode capability matrix

| Capability | A: signed power | B: separate power | C: import-only power |
|---|---:|---:|---:|
| Required HA unit | W/kW | W/kW + W/kW | W/kW |
| Direct live power | Yes | Yes | Yes |
| Imported power/energy | Measured | Measured separately | Measured |
| Exported power/energy | Measured | Measured separately | Unknown |
| Configurable sign | Yes | Not needed | Not needed |
| Import-only contractual demand | Yes | Yes; export never nets import | Yes |
| Instant forecast | Yes | Yes | Yes |
| Smoothed forecast | Yes | Yes | Yes |
| Sustained forecast | Yes | Yes | Yes, without export-surplus credit |
| Historical archive | Schema 6 | Schema 6 | Schema 6 |

All modes use the same engine, tariff calendar, fixed-quarter boundaries,
forecast code and per-entry SQLite archive. Mode B rejects contradictory
simultaneous positive import/export samples and treats asynchronously timestamped
channels conservatively. Mode C never manufactures export evidence.

## Unsupported legacy Mode D

V0.9.5/V0.9.6 cumulative-energy entries are recognized only for safe upgrade.
They are not started, polled, converted or shown as a selectable V1.0 mode. Their
configuration, checkpoint metadata, source epochs and archived rows are retained.
Explicit reconfiguration to A/B/C preserves the entry/archive identity and starts
a new source epoch. A duplicate source is rejected rather than merged.

## Future functionality

Cumulative energy-counter support, including import-only counters,
bidirectional net-energy counters and separate import/export counters, is
reserved for future development. It requires additional research into
measurement intervals, quarter-boundary alignment, counter resets, quantization
and contractual demand accuracy. No implementation date is committed.
