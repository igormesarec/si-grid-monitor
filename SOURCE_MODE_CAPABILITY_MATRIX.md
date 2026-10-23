# V0.9.6 source-mode capability matrix

| Capability | Signed power | Separate power | Import-only power | Energy counters |
|---|---:|---:|---:|---:|
| Input units | W/kW | W/kW | W/kW | Wh/kWh |
| Signed grid power | Measured/normalized | Import minus export | Import (nonnegative) | Derived interval average; signed for net-counter mode |
| Import power | Known | Known separately | Known | Derived from import counter; inferred only in net mode |
| Export power | Known | Known separately | Unknown | Unknown for import-only; measured separately or inferred from net delta |
| Quarter import demand | Supported | Supported, never netted | Supported | Counter-derived when separately evidenced; unconfirmed for net deltas |
| Instant forecast | Supported when fresh | Supported when both fresh | Supported conservatively | Unavailable |
| Sustained forecast | Supported when covered | Supported when covered | Conservative; no surplus claim | Unavailable |
| Generated entities | None | None | None | Derived import/export power |
| Recorder startup backfill | Existing Mode A behavior | Not automatic | Not automatic | Not automatic |

Mode D behavior choices are **import-only**, **bidirectional net** (selectable
polarity, default increase = import), and **separate import/export**. Separate
counters keep independent timestamps and baselines. The Mode D entities belong
to the SI Grid Monitor config entry, use stable unique IDs, and are recreated by
normal platform setup without creating Home Assistant helpers or modifying HA
`.storage` internals.

Counter conversion requires a minimum evidenced observation interval (default
30 seconds) and applies a user-configurable physical plausibility ceiling
(default 100 kW). Fast quantized reports accumulate against the earlier baseline
instead of producing a trusted derivative spike. Rejected discontinuities create
an explicit incomplete gap and anomaly provenance; their uncertain energy is not
spread into a billing quarter. The generated power entities and chart are
interval averages with start/end timestamps, never instantaneous samples.
