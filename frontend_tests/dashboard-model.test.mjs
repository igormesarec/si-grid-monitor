import assert from "node:assert/strict";
import test from "node:test";

import {
  CHART_SERIES,
  RequestGate,
  adjacentPeriodAnchor,
  blockChartModel,
  calendarDateLabel,
  chartViewStateForRender,
  counterIntervalChartModel,
  dayStatusLabel,
  defaultTodayQuarter,
  energyAxisScale,
  exceedanceRequest,
  historyErrorMessage,
  historyQuarterChartModel,
  ljubljanaDate,
  ljubljanaTimeLabel,
  livePowerChartModel,
  localQuarterLabel,
  moveTodayQuarter,
  periodChartModel,
  periodAxisLabels,
  periodBinDescription,
  periodDrillDown,
  periodRequest,
  quarterEnergyModel,
  quarterNavigation,
  restoreChartScrollState,
  selectTimelineHour,
  smoothedImportSeries,
  todayChartModel,
  todayQuarterAction,
} from "../custom_components/si_grid_monitor/frontend/dashboard-model.mjs";

test("Mode D interval chart renders accepted averages without connecting gaps", () => {
  const model = counterIntervalChartModel({
    quarterStartUtc: "2026-10-21T10:00:00Z",
    quarterEndUtc: "2026-10-21T10:15:00Z",
    contractualTargetKw: 4.8,
    intervals: [
      {start_utc: "2026-10-21T10:00:00Z", end_utc: "2026-10-21T10:00:30Z",
        import_average_kw: 1.2, export_average_kw: null, export_known: false,
        quality: "counter_interval_average"},
      {start_utc: "2026-10-21T10:05:00Z", end_utc: "2026-10-21T10:06:00Z",
        import_average_kw: 0, export_average_kw: 0.4, export_known: true,
        quality: "counter_interval_average"},
      {start_utc: "2026-10-21T10:06:00Z", end_utc: "2026-10-21T10:06:01Z",
        import_average_kw: 402.06, export_average_kw: 0, export_known: true,
        quality: "rejected_anomaly"},
    ],
  });
  assert.equal(model.actualImportSegments.length, 2);
  assert.equal(model.actualExportSegments.length, 1);
  assert.equal(model.actualImportSegments[0][0].kw, 1.2);
  assert.equal(model.actualImportSegments[0][1].timestamp, "2026-10-21T10:00:30.000Z");
  assert.equal(model.actualImportSegments.flat().some(point => point.kw === 402.06), false);
  assert.equal(model.domainMinKw < 0, true);
  assert.equal(model.domainMaxKw >= 4.8, true);
});

test("Mode D cumulative energy follows evidenced intervals and authoritative total", () => {
  const model = quarterEnergyModel({
    trace: [],
    counterIntervals: [
      {start_utc: "2026-10-21T10:00:00Z", end_utc: "2026-10-21T10:00:30Z",
        import_average_kw: 0.6},
      {start_utc: "2026-10-21T10:00:30Z", end_utc: "2026-10-21T10:01:00Z",
        import_average_kw: 0.48},
    ],
    quarterStartUtc: "2026-10-21T10:00:00Z",
    quarterEndUtc: "2026-10-21T10:15:00Z",
    nowUtc: "2026-10-21T10:01:00Z",
    importKwh: 0.009,
    contractualTargetKw: 4.8,
    contractualSafetyTargetKw: null,
    operationalTargetKw: 4.8,
    forecastSmoothedKw: null,
  });
  assert.equal(model.trajectoryMode, "full");
  assert.equal(model.actual.at(-1).kwh, 0.009);
  assert.equal(model.actual.at(-1).timestamp, "2026-10-21T10:01:00.000Z");
  assert.deepEqual(model.projection, []);
});

test("shared period selector serializes standard and custom filters", () => {
  assert.deepEqual(periodRequest({
    periodType: "month", periodAnchor: "2026-10-19", selectedDate: "2026-10-19",
    periodBlock: "3",
  }), {period_type: "month", anchor: "2026-10-19", tariff_block: 3});
  assert.deepEqual(periodRequest({
    periodType: "custom", selectedDate: "2026-10-19", customStart: "2026-10-01",
    customEnd: "2026-10-19", periodBlock: "all",
  }), {
    period_type: "custom", anchor: "2026-10-19",
    custom_start: "2026-10-01", custom_end: "2026-10-19",
  });
});

test("All-block model preserves backend sort while block model keeps UTC chronology", () => {
  const records = [
    {start_utc: "2026-10-25T01:00:00Z", measured_valid: true, import_demand_kw: 1},
    {start_utc: "2026-10-25T00:00:00Z", measured_valid: true, import_demand_kw: 3},
  ];
  for (const items of [records, [...records].reverse()]) {
    assert.deepEqual(historyQuarterChartModel(items, {preserveOrder: true}).rows.map(row => row.start_utc), items.map(row => row.start_utc));
    assert.deepEqual(historyQuarterChartModel(items).rows.map(row => row.start_utc), records.map(row => row.start_utc));
  }
});

test("exceedance requests preserve shared filters and bounded page state", () => {
  assert.deepEqual(exceedanceRequest({
    periodType: "year", periodAnchor: "2026-01-01", selectedDate: "2026-01-01",
    periodBlock: "4", exceedanceSort: "excess_percentage",
    exceedanceDirection: "asc", exceedancePage: 3, exceedancePageSize: 25,
  }), {
    period_type: "year", anchor: "2026-01-01", tariff_block: 4,
    sort_by: "excess_percentage", direction: "asc", page: 3, page_size: 25,
  });
});

test("block chart always exposes B1 through B5 and readable independent scales", () => {
  const model = blockChartModel([
    {block: 1, active: true, import_kwh: 8, maximum_import_demand_kw: 5.2,
      average_import_demand_kw: 0.8, exceeded_count: 3},
    {block: 4, active: true, import_kwh: 2, maximum_import_demand_kw: 4.2,
      average_import_demand_kw: 1.1, exceeded_count: 1},
  ]);
  assert.deepEqual(model.rows.map(row => row.block), [1, 2, 3, 4, 5]);
  assert.equal(model.energyMaximum, 8);
  assert.equal(model.demandMaximum, 6);
  assert.equal(model.exceedanceMaximum, 3);
  assert.deepEqual(model.demandScale.ticks, [0, 1, 2, 3, 4, 5, 6]);
  assert.equal(model.energyScale.step, 1);
  assert.equal(model.rows[1].active, false);
});

test("period navigation and drill-down preserve calendar intent", () => {
  const period = {
    period_type: "month",
    start_utc: "2026-09-30T22:00:00+00:00",
    end_utc: "2026-10-31T23:00:00+00:00",
    start_local: "2026-10-01T00:00:00+02:00",
    end_local: "2026-11-01T00:00:00+01:00",
  };
  assert.equal(adjacentPeriodAnchor(period, -1).anchor, "2026-09-30T21:59:59.999Z");
  assert.equal(adjacentPeriodAnchor(period, 1).anchor, "2026-10-31T23:00:00.000Z");
  assert.deepEqual(periodDrillDown("year", {bin_key: "2026-10"}, "month"), {
    periodType: "month", anchor: "2026-10-01",
  });
  assert.deepEqual(periodDrillDown("month", {bin_key: "2026-10-19"}, "day"), {
    periodType: "day", anchor: "2026-10-19",
  });
  assert.deepEqual(periodDrillDown("day", {start_utc: "2026-10-19T08:00:00Z"}, "quarter"), {
    quarterStartUtc: "2026-10-19T08:00:00Z",
  });
});

test("period drill-down follows actual bin resolution and canonical missing intervals", () => {
  assert.deepEqual(periodDrillDown("custom", {bin_key: "2028-02"}, "month"), {
    periodType: "month", anchor: "2028-02-01",
  });
  assert.deepEqual(periodDrillDown("custom", {bin_key: "2028-02-29"}, "day"), {
    periodType: "day", anchor: "2028-02-29",
  });
  const firstFold = periodDrillDown("week", {
    bin_key: "2026-10-25T02|7200|0",
    expected_start_utc: "2026-10-25T00:00:00+00:00",
  }, "hour");
  const secondFold = periodDrillDown("week", {
    bin_key: "2026-10-25T02|3600|1",
    expected_start_utc: "2026-10-25T01:00:00+00:00",
  }, "hour");
  assert.deepEqual(firstFold, {
    periodType: "hour", anchor: "2026-10-25T00:00:00+00:00",
  });
  assert.deepEqual(secondFold, {
    periodType: "hour", anchor: "2026-10-25T01:00:00+00:00",
  });
  assert.notEqual(firstFold.anchor, secondFold.anchor);
  assert.deepEqual(periodDrillDown("day", {
    status: "missing",
    bin_key: "2026-10-19T08:15:00+00:00",
    expected_start_utc: "2026-10-19T08:15:00+00:00",
  }, "quarter"), {quarterStartUtc: "2026-10-19T08:15:00+00:00"});
});

test("period chart preserves maximum demand separately from average", () => {
  const model = periodChartModel([{
    bin_key: "2026-10-19",
    maximum_import_demand_kw: 5.2,
    average_import_demand_kw: 0.8,
  }], "demand");
  assert.equal(model.maximum, 6);
  assert.deepEqual(model.ticks, [0, 1, 2, 3, 4, 5, 6]);
  assert.ok(model.valueToY(5.2) < model.valueToY(0.8));
  const withHistoricalTargets = periodChartModel([{
    maximum_import_demand_kw: 5.2, average_import_demand_kw: 0.8,
    targets_kw: [3.5, 6.0],
  }], "demand");
  assert.equal(withHistoricalTargets.maximum, 6.0);
});

test("period chart suppresses duplicate average for one quarter only", () => {
  const single = periodChartModel([{
    status: "complete", valid_count: 1, expected_count: 1,
    maximum_import_demand_kw: 3.2, average_import_demand_kw: 3.2,
  }], "demand");
  const aggregated = periodChartModel([{
    status: "complete", valid_count: 4, expected_count: 4,
    maximum_import_demand_kw: 3.2, average_import_demand_kw: 1.4,
  }], "demand");
  assert.equal(single.items[0].showAverage, false);
  assert.equal(aggregated.items[0].showAverage, true);
});

test("period labels use Ljubljana local time and distinguish the repeated DST hour", () => {
  const labels = periodAxisLabels([
    {expected_start_utc: "2026-10-25T00:00:00+00:00"},
    {expected_start_utc: "2026-10-25T01:00:00+00:00"},
    {expected_start_utc: "2026-10-25T02:00:00+00:00"},
  ], "hour");
  assert.match(labels[0], /^02:00 GMT\+2$/);
  assert.match(labels[1], /^02:00 GMT\+1$/);
  assert.equal(labels[2], "03:00");
  assert.deepEqual(periodAxisLabels([
    {expected_start_utc: "2026-09-30T22:00:00+00:00"},
  ], "day"), ["01 Oct"]);
  assert.deepEqual(periodAxisLabels([
    {expected_start_utc: "2026-12-31T23:00:00+00:00"},
  ], "month"), ["Jan 2027"]);
});

test("HISTORY quarter chart uses one-kilowatt grid and never invents a peak", () => {
  const model = historyQuarterChartModel([{
    start_utc: "2027-01-01T00:00:00+00:00", import_demand_kw: 3.4,
    contractual_target_kw: 4.2, measured_peak_kw: null, measured_valid: true,
  }]);
  assert.deepEqual(model.ticks, [0, 1, 2, 3, 4, 5]);
  assert.equal(model.rows[0].peakPct, null);
  assert.equal(model.rows[0].targetPct, 84);
});

test("HISTORY measurement states keep invalid demand out of every plotted value", () => {
  const model = historyQuarterChartModel([
    {start_utc: "2027-01-01T01:00:00Z", measured_valid: true, import_demand_kw: 0,
      coverage_seconds: 900, quality: "measured_aligned"},
    {start_utc: "2027-01-01T00:45:00Z", measured_valid: false, import_demand_kw: 7.8,
      import_kwh: .1, coverage_seconds: 300, quality: "incomplete"},
    {start_utc: "2027-01-01T00:30:00Z", measured_valid: false, import_demand_kw: 9.2,
      coverage_seconds: 0, quality: "unavailable"},
    {start_utc: "2027-01-01T00:15:00Z", archive_present: false, status: "missing",
      import_demand_kw: 12},
  ]);
  assert.deepEqual(model.rows.map(row => row.measurementState), [
    "valid_zero", "partial", "unavailable", "missing",
  ]);
  assert.deepEqual(model.rows.map(row => row.demandPct), [0, null, null, null]);
  assert.deepEqual(model.rows.map(row => row.demandKw), [0, null, null, null]);
  assert.equal(model.maximum, 1);
});

test("HISTORY model synchronizes newest-first order regardless of input order", () => {
  const model = historyQuarterChartModel([
    {start_utc: "2027-01-01T00:00:00Z", measured_valid: true, import_demand_kw: 1},
    {start_utc: "2027-01-01T00:30:00Z", measured_valid: true, import_demand_kw: 2},
    {start_utc: "2027-01-01T00:15:00Z", measured_valid: true, import_demand_kw: 3},
  ]);
  assert.deepEqual(model.rows.map(row => row.start_utc), [
    "2027-01-01T00:30:00Z", "2027-01-01T00:15:00Z", "2027-01-01T00:00:00Z",
  ]);
});

test("period bins distinguish missing data, incomplete data, and measured zero", () => {
  const bins = [
    {bin_key: "missing", status: "missing", valid_count: 0, expected_count: 1,
      import_kwh: 0},
    {bin_key: "incomplete", status: "incomplete", valid_count: 0, expected_count: 1,
      import_kwh: 0, partial_observed_import_kwh: 0.1},
    {bin_key: "zero", status: "complete", valid_count: 1, expected_count: 1,
      import_kwh: 0},
    {bin_key: "measured", status: "complete", valid_count: 1, expected_count: 1,
      import_kwh: 0.25},
  ];
  const model = periodChartModel(bins, "energy");
  assert.deepEqual(model.items.map(item => item.hasMeasuredData), [false, false, true, true]);
  assert.match(periodBinDescription(bins[0]), /missing data is not zero/);
  assert.match(periodBinDescription(bins[1]), /partial observations are excluded/);
  assert.match(periodBinDescription(bins[2]), /measured; 0\.00 kWh/);
  assert.match(periodBinDescription(bins[3]), /measured; 0\.25 kWh/);
});

class FakeChartScroller {
  constructor(root, key, scrollLeft = 0) {
    this.root = root;
    this.dataset = {chartScroll: key};
    this.scrollLeft = scrollLeft;
    this.focusOptions = null;
  }

  focus(options) {
    this.root.activeElement = this;
    this.focusOptions = options;
  }
}

class FakeChartRoot {
  constructor(entries) {
    this.activeElement = null;
    this.elements = entries.map(([key, scrollLeft]) => (
      new FakeChartScroller(this, key, scrollLeft)
    ));
  }

  querySelectorAll(selector) {
    assert.equal(selector, "[data-chart-scroll]");
    return this.elements;
  }

  element(key) {
    return this.elements.find(element => element.dataset.chartScroll === key);
  }
}

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

test("chart DOM restores independent scroll and keyboard focus over repeated refreshes", () => {
  const before = new FakeChartRoot([["power", 173], ["energy", 461]]);
  before.activeElement = before.element("energy");
  const captured = chartViewStateForRender(
    before, {power: 0, energy: 0},
    {previousDataKey: "meter-a:q1", nextDataKey: "meter-a:q1"},
  );
  assert.deepEqual(captured.positions, {power: 173, energy: 461});
  assert.equal(captured.focused, "energy");

  const refreshed = new FakeChartRoot([["power", 0], ["energy", 0]]);
  restoreChartScrollState(refreshed, captured.positions, captured.focused);
  assert.equal(refreshed.element("power").scrollLeft, 173);
  assert.equal(refreshed.element("energy").scrollLeft, 461);
  assert.equal(refreshed.activeElement, refreshed.element("energy"));
  assert.deepEqual(refreshed.element("energy").focusOptions, {preventScroll: true});

  refreshed.element("power").scrollLeft = 219;
  refreshed.element("energy").scrollLeft = 507;
  refreshed.activeElement = refreshed.element("power");
  const repeated = chartViewStateForRender(
    refreshed, captured.positions,
    {previousDataKey: "meter-a:q1", nextDataKey: "meter-a:q1"},
  );
  assert.deepEqual(repeated.positions, {power: 219, energy: 507});
  assert.equal(repeated.focused, "power");
});

test("energy scroll survives empty live trace while meter and quarter changes reset", () => {
  const energyOnly = new FakeChartRoot([["energy", 388]]);
  energyOnly.activeElement = energyOnly.element("energy");
  const preserved = chartViewStateForRender(
    energyOnly, {power: 144, energy: 301},
    {previousDataKey: "meter-a:q1", nextDataKey: "meter-a:q1"},
  );
  assert.deepEqual(preserved.positions, {power: 144, energy: 388});

  const refreshedEnergyOnly = new FakeChartRoot([["energy", 0]]);
  restoreChartScrollState(refreshedEnergyOnly, preserved.positions, preserved.focused);
  assert.equal(refreshedEnergyOnly.element("energy").scrollLeft, 388);
  assert.equal(refreshedEnergyOnly.activeElement, refreshedEnergyOnly.element("energy"));

  const meterSwitch = chartViewStateForRender(
    energyOnly, preserved.positions,
    {reset: true, previousDataKey: "meter-a:q1", nextDataKey: "meter-b:q1"},
  );
  assert.deepEqual(meterSwitch, {
    positions: {power: 0, energy: 0}, focused: null,
  });

  const quarterRollover = chartViewStateForRender(
    energyOnly, preserved.positions,
    {previousDataKey: "meter-a:q1", nextDataKey: "meter-a:q2"},
  );
  assert.deepEqual(quarterRollover, {
    positions: {power: 0, energy: 0}, focused: null,
  });
});

test("quarter navigation is exactly 15 minutes and never enters live future", () => {
  const live = "2026-10-25T01:15:00.000Z";
  assert.equal(quarterNavigation(live, -1, live), "2026-10-25T01:00:00.000Z");
  assert.equal(quarterNavigation("2026-10-25T01:00:00.000Z", 1, live), null);
  assert.match(localQuarterLabel("2026-10-25T00:30:00.000Z"), /GMT\+2/);
  assert.match(localQuarterLabel("2026-10-25T01:30:00.000Z"), /GMT\+1/);
  assert.equal(ljubljanaDate(new Date("2026-01-01T23:30:00.000Z")), "2026-01-02");
});

test("chart time labels distinguish the repeated Ljubljana rollback hour", () => {
  const summerFold = ljubljanaTimeLabel("2026-10-25T00:30:00Z");
  const winterFold = ljubljanaTimeLabel("2026-10-25T01:30:00Z");
  assert.match(summerFold, /02:30/);
  assert.match(winterFold, /02:30/);
  assert.match(summerFold, /GMT\+2|CEST/);
  assert.match(winterFold, /GMT\+1|CET/);
  assert.notEqual(summerFold, winterFold);
});

test("calendar date labels localize the weekday", () => {
  assert.match(calendarDateLabel("2026-10-18", "en"), /^Sunday,/);
  assert.match(calendarDateLabel("2026-10-18", "sl"), /^nedelja,/i);
});

function fakeTimeline(hours, scrollLeft = 840) {
  const timeline = {
    buttons: [],
    scrollLeft,
    activeElement: null,
    querySelectorAll() { return this.buttons; },
  };
  const buttons = hours.map(hour => ({
    dataset: {hour},
    selected: false,
    attributes: {},
    classList: {toggle(_name, value) { this.owner.selected = value; }},
    setAttribute(name, value) { this.attributes[name] = value; },
    focus(options) { timeline.activeElement = this; this.focusOptions = options; },
  }));
  for (const button of buttons) button.classList.owner = button;
  timeline.buttons = buttons;
  return timeline;
}

test("hour selection preserves horizontal scroll and selected focus on 23/24/25-hour days", () => {
  for (const count of [23, 24, 25]) {
    const hours = Array.from({length: count}, (_, index) => `2026-10-25T${String(index).padStart(2, "0")}:00:00Z`);
    const timeline = fakeTimeline(hours);
    const selected = selectTimelineHour(timeline, hours[22]);
    assert.equal(timeline.scrollLeft, 840);
    assert.equal(selected.dataset.hour, hours[22]);
    assert.equal(selected.selected, true);
    assert.equal(selected.attributes["aria-pressed"], "true");
    assert.equal(timeline.buttons.filter(button => button.selected).length, 1);
    selected.focus({preventScroll: true});
    assert.equal(timeline.activeElement, selected);
    assert.deepEqual(selected.focusOptions, {preventScroll: true});
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
  assert.deepEqual(model.gridValues, [-3, -2, -1, 0, 1, 2, 3, 4, 5]);
  assert.equal(model.domainMinKw, -3);
  assert.equal(model.domainMaxKw, 5);
  assert.ok(model.actualImportSegments.flat().some(point => point.kw === 3));
  assert.ok(model.actualExportSegments.flat().some(point => point.kw === -2));
  assert.equal(model.smoothedImportSegments.flat().at(-1).kw, 1.5);
  assert.deepEqual(model.futureForecast, [
    {timestamp: "2026-01-01T00:01:00.000Z", kw: 1.5},
    {timestamp: "2026-01-01T00:15:00.000Z", kw: 1.5},
  ]);
  assert.equal(model.detachedForecastAnchor, null);
});

test("quarter rollover keeps inherited backend smoothing as a detached anchor", () => {
  const model = livePowerChartModel({
    trace: [
      {timestamp: "2026-01-01T00:15:00Z", signed_kw: 4},
      {timestamp: "2026-01-01T00:15:30Z", signed_kw: 4},
    ],
    nowUtc: "2026-01-01T00:16:00Z",
    quarterEndUtc: "2026-01-01T00:30:00Z",
    contractualTargetKw: 4.2,
    windowSeconds: 120,
    staleAfterSeconds: 60,
    futureImportPowerKw: 2.75,
    futureAnchorUtc: "2026-01-01T00:16:00Z",
    forecastQuality: "estimated",
  });
  assert.deepEqual(model.smoothedImportSegments, []);
  assert.deepEqual(model.detachedForecastAnchor, {
    timestamp: "2026-01-01T00:16:00.000Z",
    kw: 2.75,
  });
  assert.deepEqual(model.futureForecast, [
    {timestamp: "2026-01-01T00:16:00.000Z", kw: 2.75},
    {timestamp: "2026-01-01T00:30:00.000Z", kw: 2.75},
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
  assert.equal(model.domainMinKw, 0);
  assert.equal(model.domainMaxKw, 14);
  assert.equal(model.hasExport, false);
  assert.ok(model.gridValues.includes(0) && model.gridValues.includes(12));
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

test("partial traces anchor only their supported recent suffix to authoritative energy", () => {
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
  assert.equal(partial.trajectoryMode, "partial");
  assert.deepEqual(partial.actual, [
    {timestamp: "2026-01-01T00:04:00.000Z", kwh: 0.25},
    {timestamp: "2026-01-01T00:05:00.000Z", kwh: 0.3},
  ]);
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
  assert.equal(inconsistent.trajectoryMode, "partial");
  assert.equal(inconsistent.actual.at(-1).kwh, 0.5);
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

test("chart series use one canonical color and dash mapping", () => {
  assert.deepEqual(CHART_SERIES.energyProjection, {color: "#8b5cf6", dash: "7 4"});
  assert.equal(CHART_SERIES.energyActual.color, CHART_SERIES.import.color);
  assert.notEqual(CHART_SERIES.contract.dash, CHART_SERIES.contractSafety.dash);
  assert.notEqual(CHART_SERIES.simulation.dash, CHART_SERIES.operational.dash);
});

test("power axis is positive-only without export and asymmetric when export is measured", () => {
  for (const peak of [0.01, 1, 4, 8, 15, 60]) {
    const model = livePowerChartModel({
      trace: [{timestamp: "2026-01-01T00:00:00Z", signed_kw: peak}],
      nowUtc: "2026-01-01T00:00:30Z",
      quarterEndUtc: "2026-01-01T00:15:00Z",
      contractualTargetKw: 3.9,
      staleAfterSeconds: 60,
    });
    assert.equal(model.domainMinKw, 0);
    assert.ok(model.domainMaxKw > Math.max(peak, 3.9));
    assert.equal(model.actualExportSegments.length, 0);
  }
  const mixed = livePowerChartModel({
    trace: [
      {timestamp: "2026-01-01T00:00:00Z", signed_kw: -1.5},
      {timestamp: "2026-01-01T00:00:30Z", signed_kw: 8},
    ],
    nowUtc: "2026-01-01T00:01:00Z",
    quarterEndUtc: "2026-01-01T00:15:00Z",
    contractualTargetKw: 3.9,
    staleAfterSeconds: 60,
  });
  assert.ok(mixed.domainMinKw < -1.5);
  assert.ok(mixed.domainMaxKw > 8);
  assert.notEqual(Math.abs(mixed.domainMinKw), mixed.domainMaxKw);
});

test("energy axis has intermediate ticks and preserves exact contractual precision", () => {
  const axis = energyAxisScale([0.1, 0.975, 0.7]);
  assert.ok(axis.maxKwh > 0.975);
  assert.ok(axis.ticks.length >= 4);
  assert.ok(axis.ticks.some(value => value > 0 && value < axis.maxKwh));
  assert.equal((3.9 * 0.25).toFixed(3), "0.975");
});

test("middle gaps expose only a continuous recent energy suffix ending at backend total", () => {
  const model = quarterEnergyModel({
    trace: [
      {timestamp: "2026-01-01T00:00:00Z", signed_kw: 2},
      {timestamp: "2026-01-01T00:00:30Z", signed_kw: 2},
      {timestamp: "2026-01-01T00:04:00Z", signed_kw: 3},
      {timestamp: "2026-01-01T00:04:30Z", signed_kw: 3},
    ],
    quarterStartUtc: "2026-01-01T00:00:00Z",
    quarterEndUtc: "2026-01-01T00:15:00Z",
    nowUtc: "2026-01-01T00:05:00Z",
    importKwh: 0.1,
    contractualTargetKw: 3.9,
    operationalTargetKw: 3.9,
    forecastSmoothedKw: 2,
    staleAfterSeconds: 60,
  });
  assert.equal(model.trajectoryMode, "partial");
  assert.equal(model.actual[0].timestamp, "2026-01-01T00:04:00.000Z");
  assert.equal(model.actual.at(-1).timestamp, "2026-01-01T00:05:00.000Z");
  assert.equal(model.actual.at(-1).kwh, 0.1);
  assert.ok(model.actual.every((point, index) => index === 0 || point.kwh >= model.actual[index - 1].kwh));
});

test("stale current data and restart gaps remain point-only", () => {
  for (const trace of [
    [{timestamp: "2026-01-01T00:01:00Z", signed_kw: 2}],
    [],
  ]) {
    const model = quarterEnergyModel({
      trace,
      quarterStartUtc: "2026-01-01T00:00:00Z",
      quarterEndUtc: "2026-01-01T00:15:00Z",
      nowUtc: "2026-01-01T00:05:00Z",
      importKwh: 0.1,
      contractualTargetKw: 3.9,
      operationalTargetKw: 3.9,
      forecastSmoothedKw: null,
      staleAfterSeconds: 60,
    });
    assert.equal(model.trajectoryMode, "point_only");
    assert.deepEqual(model.actualSegments, []);
    assert.equal(model.currentPoint.kwh, 0.1);
  }
});

test("all-export supported suffix is flat and never decreases imported energy", () => {
  const model = quarterEnergyModel({
    trace: [
      {timestamp: "2026-01-01T00:04:00Z", signed_kw: -4},
      {timestamp: "2026-01-01T00:04:30Z", signed_kw: -2},
    ],
    quarterStartUtc: "2026-01-01T00:00:00Z",
    quarterEndUtc: "2026-01-01T00:15:00Z",
    nowUtc: "2026-01-01T00:05:00Z",
    importKwh: 0.1,
    contractualTargetKw: 3.9,
    operationalTargetKw: 3.9,
    forecastSmoothedKw: 0.4,
    staleAfterSeconds: 60,
  });
  assert.equal(model.trajectoryMode, "partial");
  assert.ok(model.actual.every(point => point.kwh === 0.1));
});

test("today selector handles archived, live, missing, upcoming and DST-sized days", () => {
  for (const count of [92, 96, 100]) {
    const quarters = Array.from({length: count}, (_, index) => ({
      start_utc: new Date(Date.UTC(2026, 9, 25, 0, index * 15)).toISOString(),
      display_status: index === 4 ? "missing" : index === 5 ? "live" : index > 5 ? "upcoming" : "completed",
    }));
    assert.equal(defaultTodayQuarter(quarters, "2026-10-25", "2026-10-25"), quarters[5].start_utc);
    assert.equal(moveTodayQuarter(quarters, quarters[5].start_utc, -1), quarters[4].start_utc);
    assert.equal(moveTodayQuarter(quarters, quarters[0].start_utc, -1), null);
    assert.equal(todayQuarterAction(quarters[0]), "archive");
    assert.equal(todayQuarterAction(quarters[4]), "missing");
    assert.equal(todayQuarterAction(quarters[5]), "live");
    assert.equal(todayQuarterAction(quarters[6]), "upcoming");
  }
});
