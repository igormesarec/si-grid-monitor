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
  "../custom_components/si_grid_monitor/frontend/dashboard.js?panel-tests=1.0.3"
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

function memoryStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem: key => values.has(key) ? values.get(key) : null,
    setItem: (key, value) => values.set(key, String(value)),
    values,
  };
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

test("installation language initializes dashboard and meter switching does not reset it", () => {
  globalThis.localStorage = memoryStorage();
  const panel = new SIGridMonitorPanel();
  panel._reconcileEntries([
    {entry_id: "meter-a", title: "Main", preferred_language: "sl"},
    {entry_id: "meter-b", title: "Garage", preferred_language: "en"},
  ]);
  assert.equal(panel._language, "sl");
  panel._activateEntry("meter-b");
  assert.equal(panel._language, "sl", "meter changes must not change dashboard language");
});

test("explicit EN/SL dashboard override persists across panel instances and reloads", () => {
  const storage = memoryStorage();
  globalThis.localStorage = storage;
  const first = new SIGridMonitorPanel();
  first._render = () => {};
  first._selectLanguage("sl");
  assert.equal(storage.values.get("si_grid_monitor.dashboard_language.v1"), "sl");

  const reopened = new SIGridMonitorPanel();
  reopened._reconcileEntries([
    {entry_id: "meter-a", title: "Main", preferred_language: "en"},
  ]);
  assert.equal(reopened._language, "sl", "browser override must win over install default");
  reopened._render = () => {};
  reopened._selectLanguage("en");
  assert.equal(storage.values.get("si_grid_monitor.dashboard_language.v1"), "en");
});

test("shared dashboard header exposes an accessible language switch on every page", () => {
  globalThis.localStorage = memoryStorage();
  const panel = new SIGridMonitorPanel();
  panel._language = "en";
  panel._render();
  assert.match(panel.shadowRoot.innerHTML, /role="group"/);
  assert.match(panel.shadowRoot.innerHTML, /aria-label="Dashboard language"/);
  assert.match(panel.shadowRoot.innerHTML, /data-dashboard-language="en"/);
  assert.match(panel.shadowRoot.innerHTML, /data-dashboard-language="sl"/);
  assert.match(panel.shadowRoot.innerHTML, /data-dashboard-language="en" aria-pressed="true"/);
});

test("panel reconnect owns exactly one countdown and one refresh timer", () => {
  const originalSetInterval = globalThis.setInterval;
  const originalClearInterval = globalThis.clearInterval;
  const created = [];
  const cleared = [];
  globalThis.setInterval = (callback, milliseconds) => {
    const handle = {callback, milliseconds, id: created.length + 1};
    created.push(handle);
    return handle;
  };
  globalThis.clearInterval = handle => cleared.push(handle);
  try {
    const panel = new SIGridMonitorPanel();
    panel._render = () => {};
    panel.connectedCallback();
    panel.connectedCallback();
    assert.deepEqual(created.map(item => item.milliseconds), [1000, 10000]);

    panel.disconnectedCallback();
    assert.deepEqual(cleared, created);
    assert.equal(panel._timer, null);
    assert.equal(panel._refresh, null);

    panel.connectedCallback();
    assert.deepEqual(created.map(item => item.milliseconds), [1000, 10000, 1000, 10000]);
    panel.disconnectedCallback();
    assert.equal(cleared.length, 4);
  } finally {
    globalThis.setInterval = originalSetInterval;
    globalThis.clearInterval = originalClearInterval;
  }
});

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

test("TODAY defaults to live, preserves history on refresh, and returns to Current / Live", async () => {
  const today = new Intl.DateTimeFormat("sv-SE", {timeZone: "Europe/Ljubljana"})
    .format(new Date());
  const historical = quarter(`${today}T08:00:00+00:00`, "completed", {import_demand_kw: 1.23456});
  const live = quarter(`${today}T08:15:00+00:00`, "live", {import_demand_kw: 0.45678});
  const panel = panelForToday([historical, live]);
  panel._selectedDate = today;
  panel._selectedTodayQuarterUtc = null;
  let archiveCalls = 0;
  panel._call = async type => {
    if (type === "day") return day([historical, live]);
    archiveCalls += 1;
    return {quarter: {start_utc: historical.start_utc, import_kwh: 0.123456}};
  };

  await panel._loadTab();
  assert.equal(panel._selectedTodayQuarterUtc, live.start_utc);
  assert.equal(archiveCalls, 0, "live quarter must not request a nonexistent archive row");
  assert.match(panel._today(), /data-today-live[^>]*>Current \/ Live</);

  await panel._selectTodayQuarter(historical.start_utc);
  assert.equal(panel._selectedTodayQuarterUtc, historical.start_utc);
  assert.equal(archiveCalls, 1);
  await panel._loadTab();
  assert.equal(panel._selectedTodayQuarterUtc, historical.start_utc,
    "automatic refresh must preserve an explicit historical selection");
  assert.equal(panel._historical.quarter.start_utc, historical.start_utc);

  await panel._selectTodayLive();
  assert.equal(panel._selectedTodayQuarterUtc, live.start_utc);
  assert.equal(panel._historical, null);
});

test("dashboard formats kW and kWh to three decimals without converting unknown to zero", () => {
  const panel = new SIGridMonitorPanel();
  panel._historical = {quarter: {
    start_utc: START_A,
    import_demand_kw: 1.23456,
    import_kwh: 0.123456,
    export_kwh: null,
    contractual_target_kw: 3.9,
    quality: "measured",
    tariff_rule_status: "official",
    confirmed_exceeded: false,
  }};
  const html = panel._historicalCard();
  assert.match(html, /1\.235 <small>kW/);
  assert.match(html, /0\.123 <small>kWh/);
  assert.match(html, /Export<\/span><strong>—/);
  assert.doesNotMatch(html, /Export<\/span><strong>0\.000/);
});

test("a delayed archive result cannot cross a meter switch", async () => {
  const panel = panelForToday();
  panel._entries = [
    {entry_id: "meter-a", title: "Meter A"},
    {entry_id: "meter-b", title: "Meter B"},
  ];
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

test("active meter persists across panel instances and removed meters fall back visibly", () => {
  const originalStorage = globalThis.localStorage;
  const storage = memoryStorage({"si_grid_monitor.active_meter.v1": "meter-b"});
  globalThis.localStorage = storage;
  try {
    const restored = new SIGridMonitorPanel();
    restored._hass = {language: "en"};
    restored._reconcileEntries([
      {entry_id: "meter-a", title: "Garage meter"},
      {entry_id: "meter-b", title: "House meter"},
    ]);
    assert.equal(restored._entryId, "meter-b");
    assert.equal(restored._meterNotice, undefined);

    const afterRemoval = new SIGridMonitorPanel();
    afterRemoval._hass = {language: "en"};
    afterRemoval._reconcileEntries([{entry_id: "meter-a", title: "Garage meter"}]);
    assert.equal(afterRemoval._entryId, "meter-a");
    assert.match(afterRemoval._meterNotice, /previously selected meter is unavailable/i);
    assert.match(afterRemoval._meterNotice, /Garage meter/);
    assert.equal(storage.getItem("si_grid_monitor.active_meter.v1"), "meter-a");
  } finally {
    globalThis.localStorage = originalStorage;
  }
});

test("meter persistence failure is non-fatal", () => {
  const originalStorage = globalThis.localStorage;
  globalThis.localStorage = {
    getItem() { throw new Error("blocked"); },
    setItem() { throw new Error("blocked"); },
  };
  try {
    const panel = new SIGridMonitorPanel();
    panel._hass = {language: "en"};
    panel._reconcileEntries([{entry_id: "meter-a", title: "House meter"}]);
    assert.equal(panel._entryId, "meter-a");
  } finally {
    globalThis.localStorage = originalStorage;
  }
});

test("every dashboard tab renders the active friendly name and selector", () => {
  const panel = new SIGridMonitorPanel();
  panel._loaded = true;
  panel._hass = {language: "en"};
  panel._entries = [
    {entry_id: "meter-a", title: "Garage meter"},
    {entry_id: "meter-b", title: "House main meter"},
  ];
  panel._entryId = "meter-b";
  panel._gate.switchEntry("meter-b");
  panel._historyGate.switchEntry("meter-b");
  for (const tab of ["overview", "today", "period", "blocks", "exceedances", "history", "calendar"]) {
    panel._tab = tab;
    panel._render();
    assert.match(panel.shadowRoot.innerHTML, /data-active-meter-name>House main meter/);
    assert.match(panel.shadowRoot.innerHTML, /data-entry/);
    assert.match(panel.shadowRoot.innerHTML, /class="meter meter-toolbar"/);
  }
});

test("all dashboard requests remain entry-namespaced after a meter switch", async () => {
  const panel = new SIGridMonitorPanel();
  panel._render = () => {};
  panel._entries = [
    {entry_id: "meter-a", title: "Meter A"},
    {entry_id: "meter-b", title: "Meter B"},
  ];
  panel._entryId = "meter-a";
  panel._gate.switchEntry("meter-a");
  panel._historyGate.switchEntry("meter-a");
  panel._loadTab = async () => {};
  await panel._selectEntry("meter-b");

  const requests = [];
  panel._loadTab = SIGridMonitorPanel.prototype._loadTab.bind(panel);
  panel._call = async (type, _request, entryId) => {
    requests.push({type, entryId});
    if (type === "day") return {quarters: [], blocks: [], summary: {}};
    if (type === "history") return {items: [], pagination: {}, summary: {}};
    if (type === "calendar") return {hours: []};
    return {};
  };
  for (const tab of ["overview", "today", "period", "blocks", "exceedances", "history", "calendar"]) {
    panel._tab = tab;
    await panel._loadTab();
  }
  assert.ok(requests.length >= 9);
  assert.deepEqual(new Set(requests.map(request => request.entryId)), new Set(["meter-b"]));
  assert.deepEqual(new Set(requests.map(request => request.type)), new Set([
    "current", "transitions", "day", "period", "blocks", "exceedances",
    "history", "calendar", "tariff_status",
  ]));
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
  panel._entries = [
    {entry_id: "meter-a", title: "Meter A"},
    {entry_id: "meter-b", title: "Meter B"},
  ];
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

test("analysis scrolling survives refresh and resets only for a new selection", () => {
  const panel = new SIGridMonitorPanel();
  panel._chartScrollPositions = {power: 12, energy: 34, period: 456, exceedances: 78};
  assert.equal(panel._chartScrollPositions.period, 456);
  panel._resetAnalysisScroll();
  assert.deepEqual(panel._chartScrollPositions, {
    power: 12, energy: 34, period: 0, exceedances: 0,
  });
});

test("PERIOD chart never announces a missing bin as measured zero", () => {
  const panel = new SIGridMonitorPanel();
  panel._periodChartMode = "energy";
  panel._period = {
    period: {resolution: "quarter"},
    bins: [
      {bin_key: START_A, expected_start_utc: START_A, status: "missing",
        valid_count: 0, expected_count: 1, import_kwh: 0, export_kwh: 0},
      {bin_key: START_B, expected_start_utc: START_B, status: "complete",
        valid_count: 1, expected_count: 1, import_kwh: 0, export_kwh: 0},
    ],
  };
  const html = panel._periodChart();
  assert.match(html, /missing data is not zero/);
  assert.match(html, /measured; 0\.000 kWh imported/);
  assert.equal((html.match(/class="import-bar"/g) || []).length, 1);
});

test("PERIOD legends match visible series and single quarters do not duplicate demand", () => {
  const panel = new SIGridMonitorPanel();
  panel._periodChartMode = "demand";
  panel._period = {
    period: {resolution: "quarter"},
    bins: [{
      bin_key: START_A, expected_start_utc: START_A, status: "complete",
      valid_count: 1, expected_count: 1, maximum_import_demand_kw: 3.2,
      average_import_demand_kw: 3.2, targets_kw: [3.9],
    }],
  };
  const single = panel._periodChart();
  assert.equal((single.match(/class="import-bar"/g) || []).length, 1);
  assert.equal((single.match(/class="average-bar"/g) || []).length, 0);
  assert.match(single, /Maximum import demand/);
  assert.doesNotMatch(single, /Average import demand/);
  assert.match(single, /Historical contracted-power limit/);

  panel._period.bins[0].expected_count = 4;
  panel._period.bins[0].valid_count = 4;
  const aggregated = panel._periodChart();
  assert.equal((aggregated.match(/class="average-bar"/g) || []).length, 1);
  assert.match(aggregated, /Average import demand/);

  panel._periodChartMode = "energy";
  const energy = panel._periodChart();
  assert.match(energy, /Imported energy \(kWh\)/);
  assert.match(energy, /Exported energy \(kWh\)/);
  assert.doesNotMatch(energy, /Maximum import demand/);
});

test("PERIOD renders Ljubljana labels rather than sliced UTC offsets", () => {
  const panel = new SIGridMonitorPanel();
  panel._periodChartMode = "energy";
  panel._period = {
    period: {resolution: "hour"},
    bins: [
      {expected_start_utc: "2026-10-25T00:00:00+00:00", status: "complete",
        valid_count: 4, expected_count: 4, import_kwh: 1, export_kwh: 0},
      {expected_start_utc: "2026-10-25T01:00:00+00:00", status: "complete",
        valid_count: 4, expected_count: 4, import_kwh: 1, export_kwh: 0},
    ],
  };
  const html = panel._periodChart();
  assert.match(html, /02:00 GMT\+2/);
  assert.match(html, /02:00 GMT\+1/);
  assert.doesNotMatch(html, /00\+00:00/);
});

test("HISTORY block report synchronizes chart and table without inventing peaks", () => {
  const panel = new SIGridMonitorPanel();
  panel._historyBlock = "2";
  const rows = [
    {start_utc: START_B, end_utc: "2026-10-19T08:30:00+00:00", tariff_block: 2,
      import_demand_kw: 3.4, contractual_target_kw: 3.9, measured_peak_kw: null,
      measured_valid: true, confirmed_exceeded: false, import_kwh: .85, export_kwh: 0,
      quality: "measured_aligned", coverage_pct: 100},
    {start_utc: START_A, end_utc: START_B, tariff_block: 2,
      import_demand_kw: 4.1, contractual_target_kw: 3.9, measured_peak_kw: null,
      measured_valid: true, confirmed_exceeded: true, excess_kw: .2,
      import_kwh: 1.025, export_kwh: 0, quality: "measured_aligned", coverage_pct: 100},
  ];
  const html = panel._historyQuarterReport({items: rows});
  assert.equal((html.match(/class="history-chart-row state-valid"/g) || []).length, 2);
  assert.equal((html.match(/data-history-quarter=/g) || []).length, 6);
  assert.equal((html.match(/class="history-peak"/g) || []).length, 0);
  assert.match(html, /Not archived; not inferred/);
  assert.ok(html.indexOf(START_B) < html.indexOf(START_A));
});

test("HISTORY chart, labels, table and accessibility agree on measurement validity", () => {
  const panel = new SIGridMonitorPanel();
  panel._historyBlock = "2";
  const common = {tariff_block: 2, contractual_target_kw: 3.9, measured_peak_kw: null,
    confirmed_exceeded: null, export_kwh: 0, coverage_pct: 0};
  const html = panel._historyQuarterReport({items: [
    {...common, start_utc: "2026-10-19T09:00:00Z", end_utc: "2026-10-19T09:15:00Z",
      measured_valid: true, import_demand_kw: 0, import_kwh: 0,
      coverage_seconds: 900, coverage_pct: 100, quality: "measured_aligned"},
    {...common, start_utc: "2026-10-19T08:45:00Z", end_utc: "2026-10-19T09:00:00Z",
      measured_valid: false, import_demand_kw: 7.8, import_kwh: .1,
      coverage_seconds: 300, coverage_pct: 33.33, quality: "incomplete"},
    {...common, start_utc: "2026-10-19T08:30:00Z", end_utc: "2026-10-19T08:45:00Z",
      measured_valid: false, import_demand_kw: 8.4, import_kwh: null,
      coverage_seconds: 0, quality: "unavailable"},
    {...common, start_utc: "2026-10-19T08:15:00Z", end_utc: "2026-10-19T08:30:00Z",
      archive_present: false, status: "missing", measured_valid: false,
      import_demand_kw: 9.1, import_kwh: null, coverage_seconds: 0, quality: "missing"},
  ]});
  assert.equal((html.match(/class="history-demand"/g) || []).length, 1);
  assert.match(html, /0\.000 kW/);
  assert.match(html, /Partial observation: 0\.100 kWh import; contractual demand unavailable/);
  assert.match(html, /Measurement unavailable/);
  assert.match(html, /Archive record missing/);
  assert.doesNotMatch(html, /7\.800 kW|8\.400 kW|9\.100 kW/);
  assert.match(html, /state-valid_zero/);
  assert.match(html, /state-partial/);
  assert.match(html, /state-unavailable/);
  assert.match(html, /state-missing/);
});

test("HISTORY long chart is responsive with aligned axis track and no fixed mobile width", () => {
  const panel = new SIGridMonitorPanel();
  panel._historyBlock = "1";
  const items = Array.from({length: 120}, (_unused, index) => ({
    start_utc: new Date(Date.UTC(2026, 0, 2, 0, -15 * index)).toISOString(),
    end_utc: new Date(Date.UTC(2026, 0, 2, 0, 15 - 15 * index)).toISOString(),
    tariff_block: 1, measured_valid: true, import_demand_kw: index % 5,
    contractual_target_kw: 4.2, measured_peak_kw: null, coverage_seconds: 900,
    coverage_pct: 100, quality: "measured_aligned", import_kwh: 0, export_kwh: 0,
  }));
  const html = panel._historyQuarterReport({items});
  const css = panel._legendStyles();
  assert.equal((html.match(/class="history-chart-row/g) || []).length, 120);
  assert.equal((html.match(/class="history-report-scroll"/g) || []).length, 1);
  assert.match(html, /class="history-axis-track"/);
  assert.match(css, /history-axis-track\{position:relative/);
  assert.match(css, /history-demand\{position:absolute;inset-block:4px;inset-inline-start:0/);
  assert.match(css, /history-report-scroll\{max-width:100%;min-width:0;overflow:hidden/);
  assert.match(css, /history-chart-row\{width:100%;min-width:0/);
  assert.match(html, /class="history-quarter-chart"[^>]*><div class="history-axis">/);
  assert.doesNotMatch(css, /min-width:760px/);
});

test("HISTORY all-block mode renders chronological B1-B5 records instead of summary only", () => {
  const panel = new SIGridMonitorPanel();
  panel._historyBlock = "all";
  const older = {...quarter(START_A), tariff_block: 1, measured_valid: true,
    import_demand_kw: 1.5, contractual_target_kw: 3.5, coverage_pct: 100,
    import_kwh: .375, export_kwh: 0, quality: "measured_aligned"};
  const newer = {...quarter(START_B), tariff_block: 5, measured_valid: true,
    import_demand_kw: 2.5, contractual_target_kw: 4.2, coverage_pct: 100,
    import_kwh: .625, export_kwh: 0, quality: "measured_aligned"};
  const html = panel._historyQuarterReport({items: [newer, older]});
  assert.match(html, /history-quarter-report all-blocks/);
  assert.match(html, /All archived quarters/);
  assert.match(html, /class="chip b1">B1/);
  assert.match(html, /class="chip b5">B5/);
  assert.ok(html.indexOf(START_B) < html.indexOf(START_A));
  assert.doesNotMatch(html, /history-quarter-chart/);
  assert.match(html, /history-desktop-table/);
  assert.match(html, /history-mobile-cards/);
});

test("HISTORY mobile cards expose a complete quarter without horizontal table dependence", () => {
  const panel = new SIGridMonitorPanel();
  panel._historyBlock = "2";
  const html = panel._historyQuarterReport({items: [{
    ...quarter(START_B), tariff_block: 2, measured_valid: true,
    import_demand_kw: 3.4, contractual_target_kw: 3.9, confirmed_exceeded: false,
    import_kwh: .85, export_kwh: .1, coverage_pct: 100, source_id: "sensor.long_entity_id",
    source_epoch: 7, quality: "measured_aligned", tariff_rule_version: "si-2026-v1",
    tariff_rule_status: "official",
  }]});
  assert.match(html, /<details class="history-mobile-card state-valid">/);
  assert.match(html, /Quarter-average import demand/);
  assert.match(html, /Historical contracted-power limit/);
  assert.match(html, /Import \/ export/);
  assert.match(html, /Quality \/ measurement coverage \(%\)/);
  assert.match(html, /Measurement coverage: 100\.00%/);
  assert.match(html, /sensor\.long_entity_id \/ 7/);
  assert.match(html, /si-2026-v1 · official/);
  assert.match(html, /Open quarter details/);
});

test("HISTORY labels measured, net-inferred, and unknown export without zero fabrication", () => {
  const panel = new SIGridMonitorPanel();
  panel._historyBlock = "all";
  const base = {...quarter(START_A), measured_valid: true, import_demand_kw: 1,
    contractual_target_kw: 3.5, import_kwh: .25, coverage_pct: 100,
    quality: "counter_derived"};
  const html = panel._historyQuarterReport({items: [
    {...base, start_utc: START_A, export_kwh: .1,
      export_provenance: "directly_measured", export_known: true},
    {...base, start_utc: START_B, export_kwh: .2,
      export_provenance: "inferred_from_net", export_known: true},
    {...base, start_utc: "2026-10-19T10:30:00+00:00", export_kwh: 0,
      export_provenance: "unknown", export_known: false},
  ]});
  assert.match(html, /0\.100 kWh · directly measured export/);
  assert.match(html, /0\.200 kWh · export inferred from net counter/);
  assert.match(html, /export unknown/);
  assert.doesNotMatch(html, /0\.000 kWh · directly measured export/);
});

test("HISTORY marks partially known export without presenting a quarter-wide measured zero", () => {
  const panel = new SIGridMonitorPanel();
  panel._historyBlock = "all";
  const html = panel._historyQuarterReport({items: [{
    ...quarter(START_A), measured_valid: true, import_demand_kw: 1.2,
    contractual_target_kw: 3.5, import_kwh: .3, export_kwh: 0,
    export_provenance: "mixed_known_unknown", export_known: false,
    export_coverage_seconds: 600, export_unknown_seconds: 300,
    coverage_pct: 100, quality: "counter_derived",
  }]});
  assert.match(html, /0\.000 kWh · partially measured export; unknown intervals present/);
  assert.match(html, /600s known \/ 300s unknown/);
  assert.doesNotMatch(html, /0\.000 kWh · directly measured export/);
});

test("mobile HISTORY CSS stacks header and controls at Android widths", () => {
  const panel = new SIGridMonitorPanel();
  const css = panel._mobileHistoryStyles();
  assert.match(css, /header\{min-width:0\}/);
  assert.match(css, /overflow-wrap:anywhere/);
  assert.match(css, /history-controls\{display:grid/);
  assert.match(css, /@media\(max-width:700px\)\{header\{align-items:flex-start;flex-direction:column\}/);
  assert.match(css, /history-controls\{grid-template-columns:minmax\(0,1fr\)\}/);
});

test("BLOCKS uses measurement colors independent of B1-B5 identity colors", () => {
  const panel = new SIGridMonitorPanel();
  const html = panel._blockCharts([
    {block: 1, active: true, import_kwh: 4, maximum_import_demand_kw: 3.5,
      average_import_demand_kw: 1.2, exceeded_count: 0, targets_kw: [3.9]},
  ]);
  assert.match(html, /class="block-primary-demand"[^>]+fill="#dc2626"/);
  assert.match(html, /class="block-average"[^>]+fill="#38bdf8"/);
  assert.match(html, /class="block-target"/);
  assert.match(html, /swatch import/);
  assert.match(html, /swatch smooth/);
  assert.match(html, /swatch contract/);
  assert.match(html, /Tariff-block identity/);
});

test("PERIOD panel drills missing quarter and repeated hour by canonical UTC identity", async () => {
  const panel = new SIGridMonitorPanel();
  panel._render = () => {};
  panel._loadTab = async () => {};
  panel._periodType = "week";
  panel._period = {
    period: {resolution: "hour"},
    bins: [{
      bin_key: "2026-10-25T02|3600|1",
      expected_start_utc: "2026-10-25T01:00:00+00:00",
      status: "missing",
    }],
  };
  await panel._drillPeriod(0);
  assert.equal(panel._periodType, "hour");
  assert.equal(panel._periodAnchor, "2026-10-25T01:00:00+00:00");

  panel._periodType = "day";
  panel._period = {
    period: {resolution: "quarter"},
    bins: [{
      bin_key: START_A, expected_start_utc: START_A, status: "missing",
    }],
  };
  await panel._drillPeriod(0);
  assert.equal(panel._tab, "today");
  assert.equal(panel._selectedTodayQuarterUtc, START_A);
});

test("HISTORY distinguishes range totals and exposes source epoch filtering", () => {
  const panel = new SIGridMonitorPanel();
  panel._hass = {language: "sl-SI"};
  panel._language = "sl";
  panel._historyPage = {
    items: [],
    pagination: {page: 1, pages: 1, total: 3},
    summary: {
      total: 20,
      matching_filtered_count: 3,
      completed_expected_count: 16,
      future_or_uncompleted_count: 4,
      missing_count: 2,
      incomplete_measurement_count: 1,
      unavailable_measurement_count: 1,
      source_epochs: [{source_epoch: 4, source_id: "sensor.grid", count: 12}],
      quality_distribution: {},
      provenance_distribution: {},
    },
    storage: {schema_version: 6, retention: "forever"},
  };
  const html = panel._historyView();
  assert.match(html, /data-history-source-epoch/);
  assert.match(html, /sensor\.grid · obdobje 4 \(12\)/);
  assert.match(html, /celotno izbrano časovno obdobje/);
  assert.match(html, /Pričakovani zaključeni intervali/);
  assert.match(html, /Manjkajoči zaključeni intervali/);
  assert.match(html, /Prihodnji \/ nezaključeni intervali/);
  assert.match(html, /Nepopolne arhivirane meritve/);
  assert.match(html, /Nedostopne arhivirane meritve/);
  assert.match(html, /Stran 1 od 1 · 3 ustreznih četrtin/);
});

test("HISTORY sends the selected source epoch without leaking another namespace", async () => {
  const panel = new SIGridMonitorPanel();
  panel._render = () => {};
  panel._entryId = "meter-a";
  panel._gate.switchEntry("meter-a");
  panel._tab = "history";
  panel._historySourceEpoch = "4";
  let captured;
  panel._call = async (type, request, entryId) => {
    captured = {type, request, entryId};
    return {items: [], pagination: {page: 1, pages: 0, total: 0}, summary: {}};
  };
  await panel._loadTab();
  assert.equal(captured.type, "history");
  assert.equal(captured.entryId, "meter-a");
  assert.equal(captured.request.source_epoch, 4);
});

test("HISTORY block requests lock chronology across alternative sort and pagination", async () => {
  const panel = new SIGridMonitorPanel();
  panel._render = () => {};
  panel._entryId = "meter-a";
  panel._gate.switchEntry("meter-a");
  panel._tab = "history";
  panel._historyBlock = "3";
  panel._historySort = "quality";
  panel._historyDirection = "asc";
  panel._historyPageNumber = 4;
  let captured;
  panel._call = async (_type, request) => {
    captured = request;
    return {items: [], pagination: {page: 4, pages: 4, total: 200}, summary: {}};
  };
  await panel._loadTab();
  assert.equal(captured.tariff_block, 3);
  assert.equal(captured.sort_by, "start_utc");
  assert.equal(captured.direction, "desc");
  assert.equal(captured.page, 4);
});

test("HISTORY all-block requests preserve optional server sorting across pagination", async () => {
  const panel = new SIGridMonitorPanel();
  panel._render = () => {};
  panel._entryId = "meter-a";
  panel._gate.switchEntry("meter-a");
  panel._tab = "history";
  panel._historyBlock = "all";
  panel._historySort = "import_kwh";
  panel._historyDirection = "asc";
  panel._historyPageNumber = 2;
  let captured;
  panel._call = async (_type, request) => {
    captured = request;
    return {items: [], pagination: {page: 2, pages: 3, total: 120}, summary: {}};
  };
  await panel._loadTab();
  assert.equal(captured.tariff_block, undefined);
  assert.equal(captured.sort_by, "import_kwh");
  assert.equal(captured.direction, "asc");
  assert.equal(captured.page, 2);
});

test("dashboard language switching preserves meter and HISTORY selection", () => {
  const panel = new SIGridMonitorPanel();
  panel._loaded = true;
  panel._hass = {language: "en"};
  panel._language = "en";
  panel._entryId = "meter-a";
  panel._tab = "history";
  panel._historySourceEpoch = "4";
  panel._historyPageNumber = 3;
  let renders = 0;
  panel._render = () => { renders += 1; };
  panel._selectLanguage("sl");
  assert.equal(renders, 1);
  assert.equal(panel._language, "sl");
  assert.equal(panel._entryId, "meter-a");
  assert.equal(panel._tab, "history");
  assert.equal(panel._historySourceEpoch, "4");
  assert.equal(panel._historyPageNumber, 3);
});

test("CONTRACTS loads only the selected meter and exposes safe management navigation", async () => {
  const panel = new SIGridMonitorPanel();
  panel._language = "en";
  panel._render = () => {};
  panel._entryId = "meter-b";
  panel._gate.switchEntry("meter-b");
  panel._tab = "contracts";
  let captured;
  panel._call = async (type, request, entryId) => {
    captured = {type, request, entryId};
    return {
      meter_name: "Workshop",
      today: "2026-10-24",
      is_admin: true,
      health: {level: "warning", reason: "uncovered_expiry", days_remaining: 30},
      current_tariff_block: 2,
      applicable_target_kw: 3.9,
      current_schedule: [],
      audit_events: [],
    };
  };
  await panel._loadTab();
  assert.deepEqual(captured, {
    type: "contracts", request: {audit_page: 1, audit_page_size: 50}, entryId: "meter-b",
  });
  const html = panel._contractsView();
  assert.match(html, /Current contract status/);
  assert.match(html, /Open integration settings/);
  assert.match(html, /No configured contracted-power assignment/);
  assert.equal((html.match(/data-manage-contracts/g) || []).length, 1);
});

test("CONTRACTS timeline is responsive and keeps three-decimal comparison values", () => {
  const panel = new SIGridMonitorPanel();
  panel._language = "en";
  panel._contracts = {
    today: "2026-10-25",
    is_admin: true,
    contract_status: "ACTIVE",
    health: {
      level: "ok",
      reason: "active_assignment",
      days_remaining: 67,
      active: {effective_from: "2026-10-25", effective_to: "2026-12-31", provenance: "fixture"},
    },
    current_tariff_block: 1,
    applicable_target_kw: 2,
    current_schedule: [
      {effective_from: "2026-01-01", effective_to: "2026-10-24", block_targets_kw: [1,1.1,1.2,1.3,1.4], provenance: "fixture"},
      {effective_from: "2026-10-25", effective_to: "2026-12-31", block_targets_kw: [2,2.1,2.2,2.3,2.4], provenance: "fixture"},
    ],
    timeline: [
      {kind: "assignment", assignment_index: 0},
      {kind: "assignment", assignment_index: 1},
      {kind: "gap", effective_from: "2027-01-01", effective_to: "2027-12-31"},
    ],
    audit_events: [{event_utc: "2026-10-24T20:00:00Z", event_type: "SCHEDULED_CHANGE",
      effective_from: "2026-10-25", effective_to: "2026-12-31", provenance: "fixture",
      origin: "user_action", old_schedule_json: "[]", new_schedule_json: "[]",
      configuration_revision: "revision"}],
    audit_pagination: {page: 1, pages: 3, total: 101},
    historical_configuration: [{epoch: 1, effective_utc: "2026-01-01T00:00:00+00:00",
      source_id: "sensor.grid", block_targets_kw: [1,1.1,1.2,1.3,1.4],
      contracted_power_periods: null}],
    archived_target_evidence: [{first_start_utc: "2026-01-01T00:00:00+00:00",
      last_start_utc: "2026-06-30T23:45:00+00:00", tariff_block: 2,
      contractual_target_kw: 1.1, target_provenance: "fixture",
      contractual_status: "confirmed", quarter_count: 120}],
    management: {instruction: "Configure the selected meter.", route: "/config/integrations/integration/si_grid_monitor"},
  };
  const html = panel._contractsView();
  assert.match(html, /1\.000/);
  assert.match(html, /2\.000/);
  assert.match(html, /\+1\.000/);
  assert.match(html, /Not configured/);
  assert.match(html, /Scheduled change/);
  assert.match(html, /Schedules/);
  assert.match(html, /Historical configuration snapshots/);
  assert.match(html, /Immutable archived-quarter target evidence/);
  assert.match(html, /sensor\.grid/);
  assert.match(html, /Page 1 of 3 · 101 events/);
  const css = panel._contractStyles();
  assert.match(css, /@media\(max-width:700px\)/);
  assert.match(css, /grid-template-columns:1fr/);
  panel._contractSelection = [0, 1];
  const selectedHtml = panel._contractsView();
  assert.equal((selectedHtml.match(/aria-pressed="true"/g) || []).length, 2);
  assert.match(selectedHtml, /\+1\.000/);
});

test("Tariff Calendar labels as-recorded evidence separately from current configuration", () => {
  const panel = new SIGridMonitorPanel();
  panel._language = "en";
  const html = panel._calendarDetails({
    local_datetime: "2026-10-25T02:00:00+02:00",
    start_utc: "2026-10-25T00:00:00+00:00",
    block: 3,
    as_recorded_target_kw: 1.2,
    as_recorded_source: "archived_quarter",
    historical_configuration_target_kw: 1.3,
    current_configuration_target_kw: 2.2,
    utc_offset_seconds: 7200,
    fold: 0,
  });
  assert.match(html, /As recorded target/);
  assert.match(html, /Current configuration target/);
  assert.match(html, /Historical configuration inference/);
  assert.match(html, /1\.200/);
  assert.match(html, /2\.200/);
  assert.match(html, /Open Contracts/);
});

test("historical calendar cells never replace unknown recorded targets with current values", () => {
  const panel = new SIGridMonitorPanel();
  panel._language = "en";
  panel._selectedDate = "2026-01-02";
  panel._calendar = {
    date: "2026-01-02", day_classification: "working_day", season: "higher",
    hours: [{start_utc: "2026-01-02T00:00:00+00:00", local_datetime: "2026-01-02T01:00:00+01:00",
      block: 1, display_target_kw: null, current_configuration_target_kw: 4.2,
      as_recorded_target_kw: null, as_recorded_source: "archived_quarter_unknown",
      historical_configuration_target_kw: 3.5, is_historical: true,
      utc_offset_seconds: 3600, fold: 0}],
  };
  const html = panel._calendarView();
  assert.match(html, /As recorded: — kW/);
  assert.match(html, /Current configuration: 4\.200 kW/);
  assert.doesNotMatch(html, /As recorded: 4\.200 kW/);
});
