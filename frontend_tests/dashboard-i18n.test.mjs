import assert from "node:assert/strict";
import test from "node:test";

import {
  DASHBOARD_TRANSLATIONS,
  dashboardLanguage,
  translateDashboard,
} from "../custom_components/si_grid_monitor/frontend/dashboard-i18n.mjs";

test("dashboard language follows Home Assistant with English fallback", () => {
  assert.equal(dashboardLanguage({language: "sl-SI"}), "sl");
  assert.equal(dashboardLanguage({locale: {language: "en-GB"}}), "en");
  assert.equal(dashboardLanguage(null), "en");
});

test("parameterized translations keep values and use English fallback", () => {
  assert.equal(
    translateDashboard("history.page", "sl", {page: 2, pages: 4, count: 75}),
    "Stran 2 od 4 · 75 ustreznih četrtin",
  );
  assert.equal(
    translateDashboard("error.connection", "en", {message: "timeout"}),
    "Connection error: timeout. The panel will retry automatically.",
  );
  assert.equal(translateDashboard("unknown.explicit.key", "sl"), "unknown.explicit.key");
});

test("meter persistence and fallback messages are localized", () => {
  assert.equal(translateDashboard("meter.active", "en"), "Active meter");
  assert.equal(translateDashboard("meter.select", "sl"), "Izberite merilnik");
  assert.equal(
    translateDashboard("meter.fallback", "sl", {meter: "Hiša"}),
    "Prej izbrani merilnik ni dostopen. Izbran je merilnik Hiša.",
  );
});

test("language switching translates dynamic audit and all navigation keys", () => {
  for (const page of ["overview", "today", "period", "blocks", "exceedances", "history", "calendar"]) {
    assert.notEqual(translateDashboard(`nav.${page}`, "sl"), `nav.${page}`);
    assert.notEqual(translateDashboard(`nav.${page}`, "en"), `nav.${page}`);
  }
  assert.match(translateDashboard("audit.preview_limited", "sl"), /1\.000/);
  assert.match(translateDashboard("audit.preview_limited", "en"), /1,000/);
  assert.equal(
    translateDashboard("history.quarter_report", "sl", {block: "B2"}),
    "Kronološko poročilo četrtin B2",
  );
  assert.match(translateDashboard("period.maximum_demand", "sl"), /Največja/);
  assert.match(translateDashboard("blocks.average_legend", "sl"), /Povprečna/);
});

test("HISTORY filter states retain distinct null semantics in both languages", () => {
  for (const key of ["confirmed_yes", "confirmed_no", "unconfirmed", "all"]) {
    assert.notEqual(translateDashboard(`history.${key}`, "en"), `history.${key}`);
    assert.notEqual(translateDashboard(`history.${key}`, "sl"), `history.${key}`);
  }
  assert.notEqual(
    translateDashboard("history.confirmed_no", "sl"),
    translateDashboard("history.unconfirmed", "sl"),
  );
});

test("Slovenian dictionary covers every navigation and safety workflow", () => {
  const sl = DASHBOARD_TRANSLATIONS.sl;
  for (const key of [
    "OVERVIEW", "TODAY", "PERIOD", "BLOCKS", "EXCEEDANCES", "HISTORY",
    "TARIFF CALENDAR", "Data quality", "Confirmed exceedance",
    "CAN ADD THIS QUARTER", "SUSTAINED CAN ADD", "Forecast unavailable",
  ]) {
    assert.ok(sl[key], `missing Slovenian dashboard translation for ${key}`);
  }
});

test("Slovenian localization covers static content and accessibility on every tab", () => {
  const sl = DASHBOARD_TRANSLATIONS.sl;
  for (const text of [
    "CURRENT FIXED 15-MINUTE INTERVAL",
    "Live and projected values are separate from completed-quarter statistics.",
    "Average valid demand is the arithmetic mean of import-only demand across the contributing valid completed 15-minute quarters, not a whole-day or instantaneous average. Partial observed and live energy are excluded from valid totals. Confirmed exceedances use eligible completed quarters only; zero confirmed exceedances does not prove incomplete quarters stayed below their limits.",
    "Open this range in HISTORY",
    "All five blocks remain visible. Values use each archived quarter's original target and provenance; provisional and simulation results never enter confirmed exceedances.",
    "No confirmed exceeded quarters were found. This does not prove incomplete or missing intervals stayed below their limits.",
    "Home Assistant Recorder audit",
    "Tariff-rule status",
    "Scrollable live power chart",
    "Scrollable quarter energy chart",
  ]) {
    assert.ok(sl[text], `missing Slovenian dashboard translation for ${text}`);
    assert.notEqual(sl[text], text);
  }
});
