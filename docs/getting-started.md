# Getting started: your first successful quarter

Use this checklist after [installation](installation.md). You need an existing Home Assistant **grid-connection** sensor and your actual electricity distributor's contracted-power assignment. House consumption, PV generation and grid import are different measurements.

## 1. Find the source sensor

In Home Assistant go to **Developer Tools → States** (or **Settings → Devices & services → Entities**) and inspect the candidate sensor.

Check:

- The **entity ID** (such as `sensor.grid_power`): choose the actual entity from your system; examples are not default names.
- The **unit**: live power is W/kW, cumulative energy is Wh/kWh.
- **State class**: a Mode D counter should normally be `total` or `total_increasing`.
- **Sign or direction**: on some SolarEdge grid sensors a positive reading is **export**, negative is **import**. Confirm with a known household load.
- **Freshness**: a source that goes without a new timestamp for over 60 seconds may create data gaps in V0.9.5.

A live W/kW grid sensor is usually preferable to a Wh/kWh counter if you need instantaneous forecasts.

## 2. Add a meter

Open **Settings → Devices & services → Add integration → SI Grid Monitor**.

1. Give it a memorable name, e.g. `Main Grid`.
2. Select [Mode A, B, C or D](source-modes.md) based on the **actual** sensor, not the features you hope to see.
3. Select the sensor entity or entities and review any polarity preview.
4. Enter the official five contracted-power targets B1–B5 or the shared target, with genuine local validity dates. A new meter does **not** automatically inherit an existing meter's contracted-power contract.
5. Leave simulation **off** for normal monitoring. The 120-second smoothing and 60-minute sustained horizon are reasonable initial defaults.
6. Submit. Open the single **SI Grid Monitor** sidebar item and select the new meter if needed.

## 3. Verify direction and units

For signed Mode A, check that an appliance switched on **increases imported grid power** when the home is drawing from the grid. If the reading goes toward export instead, change the polarity option. Check that the selected input is not in kWh when the setup expects kW. Incorrect direction invalidates the calculation; do not compensate with a different contracted limit.

Mode C knows imported power but **does not know export**; the interface should show export as unknown rather than an asserted measured zero. Mode D's derived kW means *average between counter readings*, not power now.

## 4. Let an uninterrupted full quarter pass

Quarters are fixed by the wall clock, not by when you installed: **22:00–22:15, 22:15–22:30**, etc. A new sensor baseline or Home Assistant restart at 22:07 can leave the 22:00–22:15 quarter incomplete.

Once a fresh quarter has run from its beginning with no excessive measurement gaps, verify:

| Check | Good outcome |
|---|---|
| Source age | Fresh for a live-power input |
| Quarter import kWh | Rises when power is drawn from grid |
| Current block/target | Matches the selected dated assignment |
| Coverage | Complete or clearly explained |
| Sustained forecast (A/B/C) | Available only with fresh history, complete quarter and supported limits |
| History | New completed quarter appears with appropriate provenance |
| Exceedance | Confirmed only with sufficient data and a valid contractual target |

Do not assume the first quarter after setup must be complete. See [Data quality](data-quality.md).

## 5. Examples of interpreting the result

With a **2.600 kW** contracted limit, the quarter budget is **0.650 kWh**. If the current quarter has imported **0.100 kWh**, then **0.550 kWh** of contractual energy budget remains; the available average power depends on exactly how much of the 15 minutes is left. These are billing-budget values, **not** guaranteed physical headroom. See [Calculations](calculations.md).

## 6. If something looks wrong

If import shows **402 kW** at a normal home, stop treating that derived reading as trustworthy and inspect the source timestamps and units. Such short-interval counter spikes have been observed during V0.9.5 Mode D testing and are a known issue under investigation; see [Troubleshooting](troubleshooting.md).

For help with a particular field, see [Configuration](configuration.md); for the tabs, see [Dashboard guide](dashboard-guide.md).
