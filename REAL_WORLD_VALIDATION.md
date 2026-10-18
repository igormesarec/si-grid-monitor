# Real-world validation fixtures

These fixtures validate SI Grid Monitor behavior but are never installation
defaults. Contracted power is user-specific and must be entered from the user's
own distributor record.

## Distributor-assigned 2026 contracted power

User-provided record date: **17 October 2025**. Validity: **1 January 2026
through 31 December 2026**, inclusive. The distributor determined these values
from 15-minute measurements:

| Tariff block | Contracted power |
|---|---:|
| B1 | 3.50 kW |
| B2 | 3.90 kW |
| B3 | 4.10 kW |
| B4 | 4.20 kW |
| B5 | 4.20 kW |

Automated tests combine this period with the separately versioned official URO
2026 tariff calendar. They verify block-to-target selection, transitions,
current-quarter advice, instant/smoothed forecasts, utilization and immutable
archive exceedance provenance.

The record does not establish any target for 2027–2030. The period API supports
separate, non-overlapping future periods, but future values must be explicitly
provided by the user. The existing V0.2 migration still copies its effective
single target—4.80 kW in the historical test fixture—to all five V0.3 fields; it
never substitutes the values above or invents validity dates. In Home Assistant,
the 2026 fixture can be entered through the validated multi-period JSON field in
Integration Options; after 31 December 2026 it expires and contractual advice is
unavailable until a separate later assignment is configured.
