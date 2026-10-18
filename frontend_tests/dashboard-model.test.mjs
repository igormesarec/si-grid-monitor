import assert from "node:assert/strict";
import test from "node:test";

import {
  RequestGate,
  dayStatusLabel,
  ljubljanaDate,
  localQuarterLabel,
  quarterNavigation,
  todayChartModel,
} from "../custom_components/si_grid_monitor/frontend/dashboard-model.mjs";

test("zero-centered chart uses one kW scale for import, export, and target", () => {
  const model = todayChartModel([{
    start_utc: "2026-01-01T00:00:00+00:00",
    display_status: "completed",
    measurement_valid: true,
    import_demand_kw: 3,
    export_average_kw: 1,
    contractual_target_kw: 4.2,
  }]);
  const item = model.items[0];
  assert.equal(model.zeroY, model.margin.top + (model.height - model.margin.top - model.margin.bottom) / 2);
  assert.ok(item.targetY < item.importY);
  assert.ok(item.importY < model.zeroY);
  assert.ok(item.exportY === model.zeroY);
  assert.ok(item.exportHeight > 0);
  assert.ok(model.valueToY(-1) > model.zeroY);
  assert.ok(Math.abs(item.importHeight / item.exportHeight - 3) < 1e-12);
});

test("measured zero is data while a missing interval has no plotted value", () => {
  const model = todayChartModel([
    {display_status: "completed", measurement_valid: true, import_demand_kw: 0,
      export_average_kw: 0, contractual_target_kw: 4.2},
    {display_status: "missing", measurement_valid: false, import_demand_kw: null,
      export_average_kw: null, contractual_target_kw: 4.2},
  ]);
  assert.equal(model.items[0].importKw, 0);
  assert.equal(model.items[0].importHeight, 0);
  assert.equal(model.items[1].importKw, null);
  assert.equal(dayStatusLabel(model.items[1]), "MISSING");
});

test("chart retains all 92, 96, or 100 DST-day slots", () => {
  for (const count of [92, 96, 100]) {
    const model = todayChartModel(Array.from({length: count}, (_, index) => ({
      start_utc: new Date(Date.UTC(2026, 0, 1, 0, index * 15)).toISOString(),
      display_status: "upcoming",
      measurement_valid: false,
      import_demand_kw: null,
      export_average_kw: null,
      contractual_target_kw: 4.2,
    })));
    assert.equal(model.items.length, count);
    assert.ok(model.slot > 0);
  }
});

test("meter generation gate rejects delayed responses from the prior meter", () => {
  const gate = new RequestGate();
  const meterA = gate.switchEntry("meter-a");
  assert.ok(gate.accepts(meterA));
  const meterB = gate.switchEntry("meter-b");
  assert.ok(!gate.accepts(meterA));
  assert.ok(gate.accepts(meterB));
  const newerB = gate.invalidate();
  assert.ok(!gate.accepts(meterB));
  assert.ok(gate.accepts(newerB));
});

test("quarter navigation is exactly 15 minutes and never enters live future", () => {
  const live = "2026-10-25T01:15:00.000Z";
  assert.equal(quarterNavigation(live, -1, live), "2026-10-25T01:00:00.000Z");
  assert.equal(quarterNavigation("2026-10-25T01:00:00.000Z", 1, live), null);
  assert.match(localQuarterLabel("2026-10-25T00:30:00.000Z"), /GMT\+2/);
  assert.match(localQuarterLabel("2026-10-25T01:30:00.000Z"), /GMT\+1/);
  assert.equal(ljubljanaDate(new Date("2026-01-01T23:30:00.000Z")), "2026-01-02");
});
