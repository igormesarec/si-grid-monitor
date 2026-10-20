import assert from "node:assert/strict";
import test from "node:test";

import {
  DASHBOARD_TRANSLATIONS,
  dashboardLanguage,
} from "../custom_components/si_grid_monitor/frontend/dashboard-i18n.mjs";

test("dashboard language follows Home Assistant with English fallback", () => {
  assert.equal(dashboardLanguage({language: "sl-SI"}), "sl");
  assert.equal(dashboardLanguage({locale: {language: "en-GB"}}), "en");
  assert.equal(dashboardLanguage(null), "en");
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
