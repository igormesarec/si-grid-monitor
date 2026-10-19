import assert from "node:assert/strict";
import test from "node:test";

class FakeElement {
  constructor() {
    this.isConnected = true;
  }

  attachShadow() {
    this.shadowRoot = {
      activeElement: null,
      innerHTML: "",
      querySelector: () => null,
      querySelectorAll: () => [],
    };
    return this.shadowRoot;
  }
}

globalThis.HTMLElement = FakeElement;
globalThis.customElements = {define() {}};

const {SIGridMonitorPanel} = await import(
  "../custom_components/si_grid_monitor/frontend/dashboard.js?panel-tests=0.6.0"
);

const START_A = "2026-10-19T08:00:00+00:00";
const START_B = "2026-10-19T08:15:00+00:00";

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return {promise, reject, resolve};
}

function quarter(startUtc, displayStatus = "completed", overrides = {}) {
  return {
    start_utc: startUtc,
    end_utc: new Date(new Date(startUtc).getTime() + 900_000).toISOString(),
    display_status: displayStatus,
    quality: displayStatus === "completed" ? "measured" : displayStatus,
    measurement_valid: displayStatus === "completed",
    contractual_status: "confirmed",
    tariff_block: 2,
    contractual_target_kw: 3.9,
    import_demand_kw: displayStatus === "completed" ? 0 : null,
    export_average_kw: displayStatus === "completed" ? 0 : null,
    confirmed_exceeded: false,
    ...overrides,
  };
}

function day(quarters) {
  return {
    date: "2026-10-19",
    expected_quarters: quarters.length,
    quarters,
    blocks: [],
    summary: {},
  };
}

function panelForToday(quarters = [quarter(START_A)]) {
  const panel = new SIGridMonitorPanel();
  panel._render = () => {};
  panel._entryId = "meter-a";
  panel._gate.switchEntry("meter-a");
  panel._historyGate.switchEntry("meter-a");
  panel._tab = "today";
  panel._selectedDate = "2026-10-19";
  panel._selectedTodayQuarterUtc = quarters[0].start_utc;
  panel._day = day(quarters);
  return panel;
}

test("periodic TODAY refresh joins the selected delayed archive request", async () => {
  const panel = panelForToday();
  const archive = deferred();
  let quarterCalls = 0;
  panel._call = async type => {
    if (type === "day") return day([quarter(START_A)]);
    quarterCalls += 1;
    return archive.promise;
  };

  const selection = panel._selectTodayQuarter(START_A);
  await Promise.resolve();
  assert.equal(panel._historicalLoading, true);

  const refresh = panel._loadTab();
  await Promise.resolve();
  assert.equal(quarterCalls, 1, "refresh must share ownership of the in-flight request");

  archive.resolve({quarter: {start_utc: START_A, import_kwh: 0.25}});
  await Promise.all([selection, refresh]);
  assert.equal(panel._historicalLoading, false);
  assert.equal(panel._historical.quarter.start_utc, START_A);
  assert.equal(panel._historicalError, null);
});

test("a cancelled archive owner is recovered by the next refresh", async () => {
  const panel = panelForToday();
  const cancelled = deferred();
  const replacement = deferred();
  let quarterCalls = 0;
  panel._call = async type => {
    if (type === "day") return day([quarter(START_A)]);
    quarterCalls += 1;
    return quarterCalls === 1 ? cancelled.promise : replacement.promise;
  };

  const selection = panel._selectTodayQuarter(START_A);
  await Promise.resolve();
  panel._historyGate.invalidate();
  const refresh = panel._loadTab();
  await Promise.resolve();
  assert.equal(quarterCalls, 2, "refresh must replace a request whose ownership was cancelled");

  cancelled.resolve({quarter: {start_utc: START_A, marker: "stale"}});
  replacement.resolve({quarter: {start_utc: START_A, marker: "replacement"}});
  await Promise.all([selection, refresh]);
  assert.equal(panel._historicalLoading, false);
  assert.equal(panel._historical.quarter.marker, "replacement");
});

test("a stale quarter result cannot replace a newer selected quarter", async () => {
  const panel = panelForToday([quarter(START_A), quarter(START_B)]);
  const first = deferred();
  const second = deferred();
  panel._call = async (type, request) => (
    request.start_utc === START_A ? first.promise : second.promise
  );

  const selectFirst = panel._selectTodayQuarter(START_A);
  await Promise.resolve();
  const selectSecond = panel._selectTodayQuarter(START_B);
  await Promise.resolve();

  first.resolve({quarter: {start_utc: START_A}});
  await selectFirst;
  assert.equal(panel._historicalLoading, true);
  assert.equal(panel._historicalStart, START_B);

  second.resolve({quarter: {start_utc: START_B}});
  await selectSecond;
  assert.equal(panel._historicalLoading, false);
  assert.equal(panel._historical.quarter.start_utc, START_B);
});

test("a delayed archive result cannot cross a meter switch", async () => {
  const panel = panelForToday();
  const oldMeter = deferred();
  panel._call = async () => oldMeter.promise;

  const selection = panel._selectTodayQuarter(START_A);
  await Promise.resolve();
  panel._loadTab = async () => {};
  await panel._selectEntry("meter-b");
  oldMeter.resolve({quarter: {start_utc: START_A, meter: "meter-a"}});
  await selection;

  assert.equal(panel._entryId, "meter-b");
  assert.equal(panel._historical, null);
  assert.equal(panel._historicalLoading, false);
});

test("archive failure clears loading and a forced retry succeeds", async () => {
  const panel = panelForToday();
  let attempts = 0;
  panel._call = async () => {
    attempts += 1;
    if (attempts === 1) throw new Error("temporary websocket failure");
    return {quarter: {start_utc: START_A}};
  };

  await panel._selectTodayQuarter(START_A);
  assert.equal(panel._historicalLoading, false);
  assert.match(panel._historicalError, /Could not retrieve the selected quarter/);

  await panel._quarter(START_A, {force: true});
  assert.equal(attempts, 2);
  assert.equal(panel._historicalLoading, false);
  assert.equal(panel._historical.quarter.start_utc, START_A);
});

test("TODAY SVG gives every quarter status a full-slot pointer target", () => {
  const quarters = [
    quarter(START_A, "completed"),
    quarter(START_B, "missing", {measurement_valid: false}),
    quarter("2026-10-19T08:30:00+00:00", "live", {
      measurement_valid: true, import_demand_kw: 0, export_average_kw: 0,
    }),
    quarter("2026-10-19T08:45:00+00:00", "upcoming", {measurement_valid: false}),
    quarter("2026-10-19T09:00:00+00:00", "live_unavailable", {measurement_valid: false}),
  ];
  const panel = panelForToday(quarters);
  const chart = panel._todayChart(quarters);

  assert.equal((chart.match(/class="quarter-hit-area"/g) || []).length, quarters.length);
  assert.equal((chart.match(/data-quarter=/g) || []).length, quarters.length);
  assert.match(chart, /data-status="completed"[^>]*><rect class="quarter-hit-area"/);
  assert.match(chart, /data-status="missing"[^>]*><rect class="quarter-hit-area"/);
  assert.match(chart, /data-status="live"[^>]*><rect class="quarter-hit-area"/);
  assert.match(chart, /data-status="upcoming"[^>]*><rect class="quarter-hit-area"/);
  assert.match(chart, /data-status="live_unavailable"[^>]*><rect class="quarter-hit-area"/);
  assert.match(panel._legendStyles(), /quarter-hit-area\{fill:transparent;pointer-events:all\}/);
});

test("TODAY keeps the dropdown as the accessible narrow-slot alternative", () => {
  const panel = panelForToday([quarter(START_A)]);
  const html = panel._today();
  assert.match(html, /<select data-today-quarter/);
  assert.match(html, /aria-label="Selected 15-minute interval"/);
});

test("initial live-unavailable detail does not describe missing history", () => {
  const selected = quarter(START_A, "live_unavailable", {measurement_valid: false});
  const panel = panelForToday([selected]);
  const html = panel._todayQuarterDetails(selected);
  assert.match(html, /Current measurements are unavailable/);
  assert.match(html, /not a missing historical archive record/);
  assert.doesNotMatch(html, /No valid archived measurement exists/);
});

test("BLOCKS keeps five rows and opens filtered exceedances", () => {
  const panel = new SIGridMonitorPanel();
  panel._periodBlock = "3";
  panel._blocks = {
    period: {label: "October 2026"},
    blocks: [1, 2, 3, 4, 5].map(block => ({
      block, active: block < 4, valid_measured_hours: block,
      valid_count: block, contractual_eligible_count: block,
      incomplete_count: 0, missing_count: 0, import_kwh: block,
      export_kwh: 0, maximum_import_demand_kw: block,
      average_import_demand_kw: block / 2, targets_kw: [3 + block / 10],
      exceeded_count: block === 3 ? 2 : 0, confirmed_exceedance_pct: 1,
      maximum_excess_kw: block === 3 ? 0.4 : null,
      peak_timestamp: START_A, high_demand_quarters: [],
    })),
  };
  const html = panel._blocksView();
  assert.equal((html.match(/<tr data-block=/g) || []).length, 5);
  assert.match(html, /B3 details/);
  assert.match(html, /data-open-exceedances/);
  assert.match(html, /original target and provenance|original targets and provenance/i);
});

test("EXCEEDANCES renders one row per quarter with safe pagination state", () => {
  const panel = new SIGridMonitorPanel();
  panel._exceedances = {
    period: {label: "October 2026"},
    summary: {
      exceedance_count: 3, exceeded_duration_minutes: 45,
      maximum_import_demand_kw: 5.4, maximum_excess_kw: 0.6,
      maximum_excess_percentage: 12.5, average_excess_kw: 0.43,
      confirmed_exceedance_rate_pct: 3, contractual_eligible_count: 100,
      incomplete_or_unconfirmed_count: 2, most_affected_block: 2,
      greatest_exceedance: {start_utc: START_B},
    },
    bins: [{bin_key: START_A, exceeded_count: 3, maximum_excess_kw: 0.6}],
    items: [5.2, 5.4, 5.1].map((demand, index) => ({
      start_utc: new Date(new Date(START_A).getTime() + index * 900_000).toISOString(),
      end_utc: new Date(new Date(START_A).getTime() + (index + 1) * 900_000).toISOString(),
      tariff_block: 2, contractual_target_kw: 4.8, import_demand_kw: demand,
      excess_kw: demand - 4.8, excess_percentage: 100 * (demand - 4.8) / 4.8,
      excess_energy_kwh: (demand - 4.8) * .25, quality: "reconstructed",
      contractual_status: "confirmed",
    })),
    pagination: {page: 1, pages: 1, total: 3},
  };
  const html = panel._exceedancesView();
  assert.equal((html.match(/data-exceedance-quarter=/g) || []).length, 3);
  assert.match(html, /45 <small>minutes/);
  assert.match(html, /analytical only/);
  assert.match(html, /data-chart-scroll="exceedances"/);
});

test("delayed PERIOD-family response cannot cross a meter switch", async () => {
  const panel = new SIGridMonitorPanel();
  panel._render = () => {};
  panel._entryId = "meter-a";
  panel._gate.switchEntry("meter-a");
  panel._tab = "blocks";
  const delayed = deferred();
  panel._call = async () => delayed.promise;
  const request = panel._loadTab();
  await Promise.resolve();
  panel._loadTab = async () => {};
  await panel._selectEntry("meter-b");
  delayed.resolve({period: {label: "wrong meter"}, blocks: []});
  await request;
  assert.equal(panel._entryId, "meter-b");
  assert.equal(panel._blocks, null);
});
