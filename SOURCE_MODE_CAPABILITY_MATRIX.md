# V0.9.5 source-mode capability matrix

| Capability | Signed power | Separate power | Import-only power | Energy counters |
|---|---:|---:|---:|---:|
| Input units | W/kW | W/kW | W/kW | Wh/kWh |
| Signed grid power | Measured/normalized | Import minus export | Import (nonnegative) | Derived interval average |
| Import power | Known | Known separately | Known | Derived |
| Export power | Known | Known separately | Unknown | Derived only with export counter |
| Quarter import demand | Supported | Supported, never netted | Supported | Estimated/counter-derived when evidenced |
| Instant forecast | Supported when fresh | Supported when both fresh | Supported conservatively | Unavailable |
| Sustained forecast | Supported when covered | Supported when covered | Conservative; no surplus claim | Unavailable |
| Generated entities | None | None | None | Derived import/export power |
| Recorder startup backfill | Existing Mode A behavior | Not automatic | Not automatic | Not automatic |

The Mode D entities belong to the SI Grid Monitor config entry, use stable unique
IDs, and are recreated by normal platform setup without creating Home Assistant
helpers or modifying `.storage` directly.
