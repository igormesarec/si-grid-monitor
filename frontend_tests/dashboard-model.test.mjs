import assert from "node:assert/strict";
import test from "node:test";

import {
  RequestGate,
  calendarDateLabel,
  dayStatusLabel,
  historyErrorMessage,
  ljubljanaDate,
  livePowerChartModel,
  localQuarterLabel,
  quarterEnergyModel,
  quarterNavigation,
  selectTimelineHour,
  smoothedImportSeries,
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

test("calendar date labels localize the weekday", () => {
  assert.match(calendarDateLabel("2026-10-18", "en"), /^Sunday,/);
  assert.match(calendarDateLabel("2026-10-18", "sl"), /^nedelja,/i);
});

function fakeTimeline(hours, scrollLeft = 840) {
  const buttons = hours.map(hour => ({
    dataset: {hour},
    selected: false,
    attributes: {},
    classList: {toggle(_name, value) { this.owner.selected = value; }},
    setAttribute(name, value) { this.attributes[name] = value; },
  }));
  for (const button of buttons) button.classList.owner = button;
  return {
    buttons,
    scrollLeft,
    querySelectorAll() { return buttons; },
  };
}

test("hour selection preserves horizontal scroll and selected focus on 23/25-hour days", () => {
  for (const count of [23, 25]) {
    const hours = Array.from({length: count}, (_, index) => `2026-10-25T${String(index).padStart(2, "0")}:00:00Z`);
    const timeline = fakeTimeline(hours);
    const selected = selectTimelineHour(timeline, hours[22]);
    assert.equal(timeline.scrollLeft, 840);
    assert.equal(selected.dataset.hour, hours[22]);
    assert.equal(selected.selected, true);
    assert.equal(selected.attributes["aria-pressed"], "true");
    assert.equal(timeline.buttons.filter(button => button.selected).length, 1);
  }
});

test("history errors stay distinct from successful empty results", () => {
  assert.match(historyErrorMessage("quarter", {code: "archive_unavailable"}), /temporarily unavailable/);
  assert.match(historyErrorMessage("day", {code: "day_query_failed"}), /Could not load/);
});

test("live chart separates measured paths, smoothing, and backend future assumption", () => {
  const model = livePowerChartModel({
    trace: [
      {timestamp: "2026-01-01T00:00:00Z", signed_kw: 3},
      {timestamp: "2026-01-01T00:00:30Z", signed_kw: -2},
      {timestamp: "2026-01-01T00:01:00Z", signed_kw: 1},
    ],
    nowUtc: "2026-01-01T00:01:00Z",
    quarterEndUtc: "2026-01-01T00:15:00Z",
    contractualTargetKw: 4.2,
    operationalTargetKw: 4.0,
    windowSeconds: 60,
    staleAfterSeconds: 60,
    futureImportPowerKw: 1.5,
    futureAnchorUtc: "2026-01-01T00:01:00Z",
    forecastQuality: "estimated",
  });
  assert.deepEqual(model.gridValues, [-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5]);
  assert.ok(model.actualImportSegments.flat().some(point => point.kw === 3));
  assert.ok(model.actualExportSegments.flat().some(point => point.kw === -2));
  assert.equal(model.smoothedImportSegments.flat().at(-1).kw, 1.5);
  assert.deepEqual(model.futureForecast, [
    {timestamp: "2026-01-01T00:01:00.000Z", kw: 1.5},
    {timestamp: "2026-01-01T00:15:00.000Z", kw: 1.5},
  ]);
});

test("time-weighted smoothing reaches the backend anchor at varied sensor intervals", () => {
  for (const intervalSeconds of [15, 30, 55]) {
    const anchorMs = Date.parse("2026-01-01T00:05:00Z");
    const trace = [];
    for (let timestamp = anchorMs - 180000; timestamp <= anchorMs; timestamp += intervalSeconds * 1000) {
      trace.push({timestamp: new Date(timestamp).toISOString(), signed_kw: 2.75});
    }
    const series = smoothedImportSeries(
      trace, 120, 60, new Date(anchorMs).toISOString(),
    );
    assert.equal(series.at(-1).timestamp, "2026-01-01T00:05:00.000Z");
    assert.equal(series.at(-1).complete, true);
    assert.ok(Math.abs(series.at(-1).import_kw - 2.75) < 1e-12);
  }

  const weighted = smoothedImportSeries([
    {timestamp: "2026-01-01T00:00:00Z", signed_kw: 1},
    {timestamp: "2026-01-01T00:00:30Z", signed_kw: -8},
    {timestamp: "2026-01-01T00:01:00Z", signed_kw: 3},
    {timestamp: "2026-01-01T00:01:30Z", signed_kw: 5},
  ], 120, 60, "2026-01-01T00:02:00Z");
  assert.equal(weighted.at(-1).complete, true);
  assert.ok(Math.abs(weighted.at(-1).import_kw - 2.25) < 1e-12);
});

test("smoothing leaves stale gaps open and resumes only after full valid coverage", () => {
  const trace = [
    {timestamp: "2026-01-01T00:00:00Z", signed_kw: 2},
    {timestamp: "2026-01-01T00:00:30Z", signed_kw: 2},
    {timestamp: "2026-01-01T00:04:00Z", signed_kw: 4},
    {timestamp: "2026-01-01T00:04:30Z", signed_kw: 4},
    {timestamp: "2026-01-01T00:05:00Z", signed_kw: 4},
    {timestamp: "2026-01-01T00:05:30Z", signed_kw: 4},
  ];
  const stale = smoothedImportSeries(trace, 120, 60, "2026-01-01T00:04:30Z");
  assert.equal(stale.at(-1).complete, false);
  const recovered = smoothedImportSeries(trace, 120, 60, "2026-01-01T00:06:00Z");
  assert.equal(recovered.at(-1).complete, true);
  assert.equal(recovered.at(-1).import_kw, 4);

  const chart = livePowerChartModel({
    trace,
    nowUtc: "2026-01-01T00:06:00Z",
    quarterEndUtc: "2026-01-01T00:15:00Z",
    windowSeconds: 120,
    staleAfterSeconds: 60,
  });
  assert.equal(chart.smoothedImportSegments.length, 1);
  assert.equal(chart.smoothedImportSegments.at(-1).at(-1).timestamp, "2026-01-01T00:06:00.000Z");
});

test("power forecast omits unavailable assumptions and never bridges a stale gap", () => {
  const model = livePowerChartModel({
    trace: [
      {timestamp: "2026-01-01T00:00:00Z", signed_kw: 2},
      {timestamp: "2026-01-01T00:03:00Z", signed_kw: 12},
    ],
    nowUtc: "2026-01-01T00:03:30Z",
    quarterEndUtc: "2026-01-01T00:15:00Z",
    contractualTargetKw: 4.2,
    windowSeconds: 60,
    staleAfterSeconds: 60,
    futureImportPowerKw: 12,
    futureAnchorUtc: "2026-01-01T00:03:30Z",
    forecastQuality: "unavailable",
    forecastReason: "stale source",
  });
  assert.equal(model.actualImportSegments.length, 2);
  assert.deepEqual(model.futureForecast, []);
  assert.equal(model.forecastReason, "stale source");
  assert.equal(model.gridLimitKw, 12);
  assert.ok(model.gridValues.includes(-1) && model.gridValues.includes(1));
});

test("zero or one sample does not fabricate smoothing or a forecast", () => {
  for (const trace of [[], [{timestamp: "2026-01-01T00:04:00Z", signed_kw: -2}]]) {
    const model = livePowerChartModel({
      trace,
      nowUtc: "2026-01-01T00:04:00Z",
      quarterEndUtc: "2026-01-01T00:15:00Z",
      contractualTargetKw: null,
      futureImportPowerKw: null,
      futureAnchorUtc: null,
      forecastQuality: "unavailable",
      forecastReason: "insufficient coverage",
    });
    assert.deepEqual(model.smoothedImportSegments, []);
    assert.deepEqual(model.futureForecast, []);
    assert.equal(model.forecastReason, "insufficient coverage");
  }
});

test("quarter energy is monotonic, import-only, and uses distinct contractual targets", () => {
  const model = quarterEnergyModel({
    trace: [
      {timestamp: "2026-01-01T00:00:00Z", signed_kw: 6},
      {timestamp: "2026-01-01T00:05:00Z", signed_kw: -8},
      {timestamp: "2026-01-01T00:10:00Z", signed_kw: 6},
    ],
    quarterStartUtc: "2026-01-01T00:00:00Z",
    quarterEndUtc: "2026-01-01T00:15:00Z",
    nowUtc: "2026-01-01T00:15:00Z",
    importKwh: 1,
    contractualTargetKw: 4.2,
    operationalTargetKw: 4.0,
    forecastSmoothedKw: 4,
    staleAfterSeconds: 301,
  });
  assert.equal(model.usedKwh, 1);
  assert.equal(model.actual.at(-1).kwh, 1);
  assert.ok(model.actual.every((point, index) => index === 0 || point.kwh >= model.actual[index - 1].kwh));
  assert.equal(model.contractualLimitKwh, 1.05);
  assert.equal(model.operationalTargetKwh, 1.0);
  assert.equal(model.projectedFinalKwh, 1);
  assert.equal(model.projection[0].kwh, 1);
  assert.equal(model.projection.at(-1).kwh, 1);
});

test("representative energy projection agrees with backend final-average forecast", () => {
  const trace = Array.from({length: 10}, (_, index) => ({
    timestamp: new Date(Date.parse("2026-01-01T00:00:00Z") + index * 30000).toISOString(),
    signed_kw: 3.6,
  }));
  const model = quarterEnergyModel({
    trace,
    quarterStartUtc: "2026-01-01T00:00:00Z",
    quarterEndUtc: "2026-01-01T00:15:00Z",
    nowUtc: "2026-01-01T00:05:00Z",
    importKwh: 0.3,
    contractualTargetKw: 4.2,
    operationalTargetKw: 4.0,
    forecastSmoothedKw: 2.8,
    staleAfterSeconds: 60,
  });
  assert.equal(model.trajectoryAvailable, true);
  assert.equal(model.currentPoint.kwh, 0.3);
  assert.equal(model.projection[0].kwh, 0.3);
  assert.equal(model.projection.at(-1).kwh, 0.7);
  assert.equal(model.contractualLimitKwh, 1.05);
  assert.equal(model.operationalTargetKwh, 1.0);
});

test("partial or inconsistent traces never fabricate prior cumulative energy", () => {
  const partial = quarterEnergyModel({
    trace: [{timestamp: "2026-01-01T00:04:00Z", signed_kw: 3}],
    quarterStartUtc: "2026-01-01T00:00:00Z",
    quarterEndUtc: "2026-01-01T00:15:00Z",
    nowUtc: "2026-01-01T00:05:00Z",
    importKwh: 0.3,
    contractualTargetKw: 4.2,
    operationalTargetKw: 4.0,
    forecastSmoothedKw: null,
    staleAfterSeconds: 60,
  });
  assert.equal(partial.trajectoryAvailable, false);
  assert.equal(partial.hasGap, true);
  assert.deepEqual(partial.actual, []);
  assert.equal(partial.currentPoint.kwh, 0.3);
  assert.deepEqual(partial.projection, []);

  const inconsistent = quarterEnergyModel({
    trace: [{timestamp: "2026-01-01T00:00:00Z", signed_kw: 3.6}],
    quarterStartUtc: "2026-01-01T00:00:00Z",
    quarterEndUtc: "2026-01-01T00:15:00Z",
    nowUtc: "2026-01-01T00:01:00Z",
    importKwh: 0.5,
    contractualTargetKw: 4.2,
    operationalTargetKw: 4.0,
    forecastSmoothedKw: 1.0,
    staleAfterSeconds: 60,
  });
  assert.equal(inconsistent.trajectoryAvailable, false);
  assert.deepEqual(inconsistent.actual, []);
  assert.equal(inconsistent.currentPoint.kwh, 0.5);
  assert.equal(inconsistent.projectionConsistent, false);
  assert.deepEqual(inconsistent.projection, []);
  assert.equal(inconsistent.projectedFinalKwh, null);
  assert.equal(inconsistent.diagnosticProjectedFinalKwh, 0.25);
  assert.match(inconsistent.projectionReason, /below energy already imported/);
});

test("simulation target is explicit and quarter rollover starts from the new backend total", () => {
  const model = quarterEnergyModel({
    trace: [{timestamp: "2026-01-01T00:15:00Z", signed_kw: 3}],
    quarterStartUtc: "2026-01-01T00:15:00Z",
    quarterEndUtc: "2026-01-01T00:30:00Z",
    nowUtc: "2026-01-01T00:16:00Z",
    importKwh: 0.05,
    contractualTargetKw: 3.5,
    contractualSafetyTargetKw: 3.3,
    operationalTargetKw: 2.3,
    simulationTargetKw: 2.5,
    simulationEnabled: true,
    forecastSmoothedKw: 2.0,
    staleAfterSeconds: 60,
  });
  assert.equal(model.currentPoint.kwh, 0.05);
  assert.equal(model.contractualLimitKwh, 0.875);
  assert.equal(model.contractualSafetyTargetKwh, 0.825);
  assert.equal(model.operationalTargetKwh, 0.575);
  assert.equal(model.simulationTargetKwh, 0.625);
});

test("missing contracts stay absent while provisional engine targets remain explicit", () => {
  const model = quarterEnergyModel({
    trace: [{timestamp: "2028-01-01T00:00:00Z", signed_kw: 2}],
    quarterStartUtc: "2028-01-01T00:00:00Z",
    quarterEndUtc: "2028-01-01T00:15:00Z",
    nowUtc: "2028-01-01T00:01:00Z",
    importKwh: 1 / 30,
    contractualTargetKw: null,
    contractualSafetyTargetKw: null,
    operationalTargetKw: 3.3,
    forecastSmoothedKw: 2,
    staleAfterSeconds: 60,
  });
  assert.equal(model.contractualLimitKwh, null);
  assert.equal(model.contractualSafetyTargetKwh, null);
  assert.equal(model.operationalTargetKwh, 0.825);
});
