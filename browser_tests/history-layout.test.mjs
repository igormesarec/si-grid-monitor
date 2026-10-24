import assert from "node:assert/strict";
import {createServer} from "node:http";
import {readFile} from "node:fs/promises";
import {fileURLToPath} from "node:url";
import test, {before, after} from "node:test";

// CI uses installed Playwright/Chromium; local runs can use the bundled runtime
// and an existing Edge executable without changing a Home Assistant instance.
const {chromium} = await import(process.env.SI_PLAYWRIGHT_MODULE || "playwright");
let browser;
let server;
let origin;
before(async () => {
  server = createServer(async (request, response) => {
    try {
      const url = new URL(request.url, "http://localhost");
      if (url.pathname === "/") {
        response.setHeader("Content-Type", "text/html");
        response.end('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0}</style>');
        return;
      }
      if (!url.pathname.startsWith("/custom_components/si_grid_monitor/frontend/")) {
        response.writeHead(404).end();
        return;
      }
      response.setHeader("Content-Type", "text/javascript");
      response.end(await readFile(fileURLToPath(new URL(`..${url.pathname}`, import.meta.url))));
    } catch {
      response.writeHead(404).end();
    }
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  origin = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({headless: true,
    ...(process.env.SI_CHROMIUM_PATH ? {executablePath: process.env.SI_CHROMIUM_PATH} : {}),
  });
});
after(async () => {
  await browser?.close();
  if (server) await new Promise(resolve => server.close(resolve));
});

async function fixture(page, {width, dark = false, enlarged = false, all = false, multiple = false}) {
  await page.setViewportSize({width, height: 900});
  await page.goto(origin);
  await page.evaluate(async ({dark, enlarged, all, multiple}) => {
    await import("/custom_components/si_grid_monitor/frontend/dashboard.js");
    document.documentElement.style.cssText = `font-size:${enlarged ? 24 : 16}px;--primary-text-color:${dark ? "#eee" : "#222"};--secondary-text-color:${dark ? "#ccc" : "#555"};--card-background-color:${dark ? "#222" : "#fff"};--primary-background-color:${dark ? "#111" : "#fafafa"}`;
    const panel = document.createElement("si-grid-monitor-panel");
    panel._loaded = true;
    panel._hass = {language: "en"};
    panel._entries = multiple ? [
      {entry_id: "meter", title: "House main meter with a very long friendly name"},
      {entry_id: "garage", title: "Garage photovoltaic meter"},
    ] : [{entry_id: "meter", title: "sensor.solaredge_m1_ac_power_with_a_very_long_meter_name"}];
    panel._entryId = "meter";
    if (multiple) panel._loadTab = async () => {};
    panel._tab = "history";
    panel._historyBlock = all ? "all" : "2";
    const items = Array.from({length: 80}, (_, index) => ({
      start_utc: new Date(Date.UTC(2026, 9, 25, 20, -15 * index)).toISOString(),
      end_utc: new Date(Date.UTC(2026, 9, 25, 20, 15 - 15 * index)).toISOString(),
      tariff_block: 2, measured_valid: index !== 1, import_demand_kw: index === 1 ? 19 : 2,
      contractual_target_kw: 4, measured_peak_kw: null, confirmed_exceeded: null,
      quality: index === 1 ? "incomplete" : "measured_aligned", coverage_seconds: index === 1 ? 300 : 900,
      coverage_pct: index === 1 ? 33.33 : 100, import_kwh: index === 1 ? .1 : .5, export_kwh: 0,
    }));
    panel._historyPage = {items, pagination: {page: 1, pages: 2, total: 100}, summary: {}, storage: {schema_version: 6}};
    document.body.append(panel);
    window.testPanel = panel;
  }, {dark, enlarged, all, multiple});
}

async function contractsFixture(page, {width, dark = false}) {
  await page.setViewportSize({width, height: 900});
  await page.goto(origin);
  await page.evaluate(async darkMode => {
    await import("/custom_components/si_grid_monitor/frontend/dashboard.js");
    document.documentElement.style.cssText = `font-size:18px;--primary-text-color:${darkMode ? "#eee" : "#222"};--secondary-text-color:${darkMode ? "#ccc" : "#555"};--card-background-color:${darkMode ? "#222" : "#fff"};--primary-background-color:${darkMode ? "#111" : "#fafafa"}`;
    const panel = document.createElement("si-grid-monitor-panel");
    panel._loaded = true;
    panel._hass = {language: "en"};
    panel._entries = [{entry_id: "meter", title: "House main contractual meter"}];
    panel._entryId = "meter";
    panel._tab = "contracts";
    panel._contracts = {
      today: "2026-10-25", is_admin: true, contract_status: "ACTIVE",
      current_tariff_block: 2, applicable_target_kw: 2.1,
      health: {level: "warning", reason: "uncovered_expiry", days_remaining: 67,
        active: {effective_from: "2026-10-25", effective_to: "2026-12-31", provenance: "fixture"}},
      current_schedule: [
        {effective_from: "2026-01-01", effective_to: "2026-10-24", block_targets_kw: [1, 1.1, 1.2, 1.3, 1.4], provenance: "fixture"},
        {effective_from: "2026-10-25", effective_to: "2026-12-31", block_targets_kw: [2, 2.1, 2.2, 2.3, 2.4], provenance: "fixture"},
      ],
      timeline: [
        {kind: "assignment", assignment_index: 0}, {kind: "assignment", assignment_index: 1},
        {kind: "gap", effective_from: "2027-01-01", effective_to: "2027-12-31"},
      ],
      audit_events: [{event_utc: "2026-10-24T18:00:00Z", event_type: "SCHEDULED_CHANGE",
        effective_from: "2026-10-25", effective_to: "2026-12-31", provenance: "fixture",
        origin: "user_action", old_schedule_json: "[]", new_schedule_json: "[]",
        configuration_revision: "revision"}],
      audit_pagination: {page: 1, pages: 2, total: 51},
      historical_configuration: [{epoch: 1, effective_utc: "2026-01-01T00:00:00+00:00",
        source_id: "sensor.grid", block_targets_kw: [1, 1.1, 1.2, 1.3, 1.4],
        contracted_power_periods: null}],
      archived_target_evidence: [{first_start_utc: "2026-01-01T00:00:00+00:00",
        last_start_utc: "2026-06-30T23:45:00+00:00", tariff_block: 2,
        contractual_target_kw: 1.1, target_provenance: "fixture",
        contractual_status: "confirmed", quarter_count: 50}],
      management: {route: "/config/integrations/integration/si_grid_monitor",
        instruction: "Configure House main contractual meter in Devices & services."},
    };
    document.body.append(panel);
    window.testPanel = panel;
  }, dark);
}

for (const width of [320, 360, 390, 430, 768, 1280]) {
  for (const dark of [false, true]) {
    test(`rendered HISTORY geometry at ${width}px, ${dark ? "dark" : "light"}`, async () => {
      const page = await browser.newPage();
      try {
        await fixture(page, {width, dark});
        const geometry = await page.evaluate(() => {
          const root = window.testPanel.shadowRoot;
          const axis = root.querySelector(".history-axis-track").getBoundingClientRect();
          const rows = [...root.querySelectorAll(".history-chart-row")];
          const first = rows[0];
          const bar = first.querySelector(".history-bar").getBoundingClientRect();
          const ticks = [...root.querySelectorAll(".history-axis-tick")].map(node => node.getBoundingClientRect().x);
          const grids = [...first.querySelectorAll(".history-grid")].map(node => node.getBoundingClientRect().x);
          const partial = rows[1];
          const text = partial.querySelector(".history-row-value b");
          const header = root.querySelector(".brand").getBoundingClientRect();
          const language = root.querySelector(".language-switcher").getBoundingClientRect();
          const meter = root.querySelector(".meter").getBoundingClientRect();
          return {axis: {x: axis.x, width: axis.width}, bar: {x: bar.x, width: bar.width},
            demandWidth: first.querySelector(".history-demand").getBoundingClientRect().width,
            tickCount: ticks.length, gridCount: grids.length,
            tickPositions: [...root.querySelectorAll(".history-axis-tick")].map(node => node.offsetLeft),
            gridPositions: [...first.querySelectorAll(".history-grid")].map(node => node.offsetLeft),
            partialText: text.textContent, partialHeight: text.getBoundingClientRect().height,
            partialScrollHeight: text.scrollHeight, partialDemand: partial.querySelector(".history-demand") !== null,
            textInsideBar: partial.querySelector(".history-bar").textContent,
            pageWidth: document.documentElement.scrollWidth, viewport: innerWidth,
            headerOverlap: header.right > meter.left && header.bottom > meter.top && header.top < meter.bottom,
            languageVisible: language.width > 0 && language.height >= 40,
            languageWithinViewport: language.right <= innerWidth && language.left >= 0,
          };
        });
        assert.ok(Math.abs(geometry.axis.x - geometry.bar.x) < 1, JSON.stringify(geometry));
        assert.ok(Math.abs(geometry.axis.width - geometry.bar.width) < 1, JSON.stringify(geometry));
        assert.equal(geometry.tickCount, geometry.gridCount);
        for (let index = 0; index < geometry.tickCount; index++) {
          assert.ok(Math.abs(geometry.tickPositions[index] - geometry.gridPositions[index]) <= 1);
        }
        assert.ok(Math.abs(geometry.demandWidth - geometry.bar.width / 2) < 1);
        assert.match(geometry.partialText, /Partial observation: 0.100 kWh import; contractual demand unavailable/);
        assert.ok(geometry.partialScrollHeight <= Math.ceil(geometry.partialHeight));
        assert.equal(geometry.partialDemand, false);
        assert.equal(geometry.textInsideBar, "");
        assert.ok(geometry.pageWidth <= geometry.viewport);
        assert.equal(geometry.headerOverlap, false);
        assert.equal(geometry.languageVisible, true);
        assert.equal(geometry.languageWithinViewport, true);
        if (width > 700) {
          const scrolled = await page.evaluate(() => {
            const root = window.testPanel.shadowRoot;
            const scrollport = root.querySelector(".history-quarter-chart");
            scrollport.scrollTop = 700;
            const axis = root.querySelector(".history-axis-track").getBoundingClientRect();
            const bar = root.querySelectorAll(".history-bar")[10].getBoundingClientRect();
            return {scroll: scrollport.scrollTop, difference: Math.abs(axis.x - bar.x) + Math.abs(axis.width - bar.width)};
          });
          assert.ok(scrolled.scroll > 0);
          assert.ok(scrolled.difference < 1);
        }
        // Native keyboard activation expands the actual responsive record card.
        if (width <= 700) {
          const summary = page.locator("si-grid-monitor-panel .history-mobile-card summary").first();
          await summary.focus();
          await summary.press("Enter");
          assert.equal(await page.locator("si-grid-monitor-panel .history-mobile-card").first().getAttribute("open"), "");
        }
      } finally { await page.close(); }
    });
  }
}

test("enlarged mobile text remains readable and All-block sort controls are labelled", async () => {
  const page = await browser.newPage();
  try {
    await fixture(page, {width: 320, enlarged: true, all: true});
    await page.getByLabel("Sort by", {exact: true}).selectOption("quality");
    await page.getByLabel("Order", {exact: true}).selectOption("asc");
    const bounds = await page.evaluate(() => ({page: document.documentElement.scrollWidth, viewport: innerWidth,
      labels: [...window.testPanel.shadowRoot.querySelectorAll(".history-controls label")].map(node => {
        const rect = node.getBoundingClientRect(); return {top: rect.top, bottom: rect.bottom};
      })}));
    assert.ok(bounds.page <= bounds.viewport);
    for (let index = 1; index < bounds.labels.length; index++) assert.ok(bounds.labels[index].top >= bounds.labels[index - 1].bottom);
  } finally { await page.close(); }
});

test("partial status wraps fully with enlarged phone text", async () => {
  const page = await browser.newPage();
  try {
    await fixture(page, {width: 320, enlarged: true});
    const status = await page.evaluate(() => {
      const row = window.testPanel.shadowRoot.querySelector(".state-partial.history-chart-row");
      const text = row.querySelector(".history-row-value b");
      const bar = row.querySelector(".history-bar").getBoundingClientRect();
      return {textBottom: text.getBoundingClientRect().bottom, barTop: bar.top,
        visibleHeight: text.clientHeight, fullHeight: text.scrollHeight,
        page: document.documentElement.scrollWidth, viewport: innerWidth};
    });
    assert.ok(status.textBottom <= status.barTop);
    assert.equal(status.visibleHeight, status.fullHeight);
    assert.ok(status.page <= status.viewport);
  } finally { await page.close(); }
});

for (const {width, dark} of [{width: 360, dark: true}, {width: 1280, dark: false}]) {
  test(`multi-meter toolbar remains accessible at ${width}px`, async () => {
    const page = await browser.newPage();
    try {
      await fixture(page, {width, dark, multiple: true});
      const selector = page.locator("si-grid-monitor-panel select[data-entry]");
      assert.equal(await selector.isVisible(), true);
      await selector.selectOption("garage");
      const state = await page.evaluate(() => {
        window.scrollTo(0, 700);
        const root = window.testPanel.shadowRoot;
        const toolbar = root.querySelector(".meter-toolbar").getBoundingClientRect();
        return {
          active: root.querySelector("[data-active-meter-name]").textContent,
          selected: root.querySelector("select[data-entry]").value,
          stickyTop: toolbar.top,
          toolbarWidth: toolbar.width,
          pageWidth: document.documentElement.scrollWidth,
          viewport: innerWidth,
        };
      });
      assert.equal(state.active, "Garage photovoltaic meter");
      assert.equal(state.selected, "garage");
      assert.ok(state.stickyTop >= -1);
      assert.ok(state.toolbarWidth <= state.viewport);
      assert.ok(state.pageWidth <= state.viewport);
    } finally { await page.close(); }
  });
}

for (const width of [320, 360, 390, 430, 768, 1280]) {
  test(`CONTRACTS remains readable without page overflow at ${width}px`, async () => {
    const page = await browser.newPage();
    try {
      await contractsFixture(page, {width, dark: width === 360});
      const layout = await page.evaluate(() => {
        const root = window.testPanel.shadowRoot;
        const periods = [...root.querySelectorAll(".contract-period")];
        return {
          pageWidth: document.documentElement.scrollWidth,
          viewport: innerWidth,
          periods: periods.length,
          managementButtons: root.querySelectorAll("[data-manage-contracts]").length,
          historicalEvidence: root.querySelector(".contract-evidence")?.textContent,
          clipped: periods.some(node => node.scrollWidth > node.clientWidth + 1),
          gap: root.querySelector(".contract-gap")?.textContent,
          tabsScrollable: root.querySelector("nav").scrollWidth >= root.querySelector("nav").clientWidth,
        };
      });
      assert.ok(layout.pageWidth <= layout.viewport, JSON.stringify(layout));
      assert.equal(layout.periods, 3);
      assert.equal(layout.managementButtons, 1);
      assert.match(layout.historicalEvidence, /sensor\.grid/);
      assert.equal(layout.clipped, false);
      assert.match(layout.gap, /Not configured/);
      assert.equal(layout.tabsScrollable, true);
    } finally { await page.close(); }
  });
}

for (const width of [320, 768, 1280]) {
  test(`EN/SL switch remains accessible and meter-stable at ${width}px`, async () => {
    const page = await browser.newPage();
    try {
      await fixture(page, {width, multiple: true});
      const sl = page.locator('si-grid-monitor-panel [data-dashboard-language="sl"]');
      await sl.focus();
      await sl.press("Enter");
      assert.equal(await sl.getAttribute("aria-pressed"), "true");
      assert.ok(await sl.isFocused());
      assert.equal(await page.locator("si-grid-monitor-panel nav button").first().textContent(), "PREGLED");
      await page.locator("si-grid-monitor-panel select[data-entry]").selectOption("garage");
      assert.equal(await page.locator("si-grid-monitor-panel nav button").first().textContent(), "PREGLED");
      assert.equal(await page.evaluate(() => localStorage.getItem("si_grid_monitor.dashboard_language.v1")), "sl");
    } finally { await page.close(); }
  });
}
