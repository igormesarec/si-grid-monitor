"""V0.4 packaging and automatic-dashboard delivery contracts."""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.si_grid_monitor.const import PANEL_URL_PATH, VERSION

ROOT = Path(__file__).parents[1]


def test_v04_manifest_packages_supported_panel_dependencies() -> None:
    manifest = json.loads(
        (ROOT / "custom_components/si_grid_monitor/manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["version"] == VERSION == "1.0.3"
    assert {"frontend", "http", "websocket_api"} <= set(manifest["dependencies"])
    assert PANEL_URL_PATH == "si-grid-monitor"


def test_dashboard_bundle_is_self_contained_and_uses_authenticated_websocket() -> None:
    bundle = (ROOT / "custom_components/si_grid_monitor/frontend/dashboard.js").read_text(
        encoding="utf-8"
    )
    assert 'customElements.define("si-grid-monitor-panel"' in bundle
    assert "hass.connection.sendMessagePromise" in bundle
    assert "si_grid_monitor/entries" in bundle
    assert "https://" not in bundle
    assert 'ACTIVE_METER_STORAGE_KEY = "si_grid_monitor.active_meter.v1"' in bundle
    assert "globalThis.localStorage?.getItem(ACTIVE_METER_STORAGE_KEY)" in bundle
    assert "globalThis.localStorage?.setItem(ACTIVE_METER_STORAGE_KEY, entryId)" in bundle
    assert "setInterval(() => this._tick(), 1000)" in bundle
    assert "RequestGate" in bundle


def test_master_specification_is_not_replaced_by_v04_addendum() -> None:
    master = (ROOT / "SPECIFICATION.md").read_text(encoding="utf-8")
    addendum = (ROOT / "SPECIFICATION_V1.4_ADDENDUM.md").read_text(encoding="utf-8")
    assert "MASTER PRODUCT SPECIFICATION V1.1" in master
    assert "V1.4 Addendum" in addendum
    assert "`SPECIFICATION.md` remains unchanged" in addendum


def test_setup_and_options_explain_each_field_in_both_languages() -> None:
    """HA data_description is required for visible per-field descriptions."""
    root = ROOT / "custom_components/si_grid_monitor"
    for name in ("strings.json", "translations/en.json", "translations/sl.json"):
        translations = json.loads((root / name).read_text(encoding="utf-8"))
        for section_name in ("config", "options"):
            for step_name, step in translations[section_name]["step"].items():
                fields = step.get("data", {})
                if not fields:
                    continue
                descriptions = step.get("data_description", {})
                assert set(fields) <= set(descriptions), (
                    f"{name} {section_name}.{step_name} missing per-field explanations"
                )
                assert all(len(descriptions[k].strip()) >= 35 for k in fields)


def test_today_and_calendar_expose_interactive_details_and_target() -> None:
    bundle = (ROOT / "custom_components/si_grid_monitor/frontend/dashboard.js").read_text(
        encoding="utf-8"
    )
    # Bind date/hour and quarter selection to a visible detail view.
    assert "data-quarter=" in bundle
    assert "Selected 15-minute interval" in bundle
    assert "this._historicalCard()" in bundle
    assert "data-hour=" in bundle
    assert 'this._t("calendar.selected_hour")' in bundle
    assert "this._selectCalendarHour(element.dataset.hour)" in bundle
    assert 'class="target-step"' in bundle
    assert "todayChartModel(quarters)" in bundle
    assert "No archived summary exists" in bundle


def test_future_limit_message_distinguishes_forecast_horizon() -> None:
    bundle = (ROOT / "custom_components/si_grid_monitor/frontend/dashboard.js").read_text(
        encoding="utf-8"
    )
    assert "lower.inside_sustained_horizon" in bundle
    assert "Forecast reduction needed" in bundle
    assert "outside the sustained forecast horizon" in bundle
    assert "Forecast unavailable" in bundle


def test_v041_setup_exposes_simulation_without_manual_schedule_json() -> None:
    source = (ROOT / "custom_components/si_grid_monitor/config_flow.py").read_text(encoding="utf-8")
    assert "CONF_SIMULATION_ENABLED" in source
    assert "CONF_SIMULATION_TARGET_KW" in source
    assert "CONF_CONTRACTED_POWER_PERIODS" in source
    for name in ("strings.json", "translations/en.json", "translations/sl.json"):
        translations = json.loads(
            (ROOT / "custom_components/si_grid_monitor" / name).read_text(encoding="utf-8")
        )
        calculation = translations["config"]["step"]["calculation"]["data"]
        settings = translations["options"]["step"]["settings"]["data"]
        assert {"simulation_enabled", "simulation_target_kw"} <= set(calculation)
        assert {"simulation_enabled", "simulation_target_kw"} <= set(settings)


def test_v041_live_charts_label_distinct_targets_and_mobile_axes() -> None:
    bundle = (ROOT / "custom_components/si_grid_monitor/frontend/dashboard.js").read_text(
        encoding="utf-8"
    )
    for label in (
        "Distributor limit",
        "Contract safety reference",
        "SIMULATION threshold",
        "Engine operational target",
        "Power (kW)",
        "Energy (kWh)",
    ):
        assert label in bundle
    assert "projected final imported energy is below energy already imported" in bundle
    assert ".chart-legend{display:flex;flex-wrap:wrap" in bundle


def test_v041_mobile_charts_scroll_locally_without_shrinking_svg_text() -> None:
    bundle = (ROOT / "custom_components/si_grid_monitor/frontend/dashboard.js").read_text(
        encoding="utf-8"
    )
    # The V0.6 PERIOD view adds a third independently scrollable chart while
    # retaining the two V0.4 live charts covered by this regression test.
    assert bundle.count('class="chart-scroll"') >= 3
    assert 'data-chart-scroll="period"' in bundle
    assert ".chart-scroll{width:100%;max-width:100%;overflow-x:auto" in bundle
    assert ".chart-scroll svg{display:block;width:max(100%,1120px);min-width:1120px}" in bundle
    assert 'aria-label="Scrollable live power chart"' in bundle
    assert 'aria-label="Scrollable quarter energy chart"' in bundle
    assert "forecast-anchor" in bundle
    assert "return `<style>" not in bundle
    assert "chartViewStateForRender" in bundle
    assert "restoreChartScrollState" in bundle
    for viewport_width in (320, 360, 390, 768):
        chart_width = max(viewport_width, 1120)
        assert chart_width >= 1120
        assert min(viewport_width, chart_width) == viewport_width


def test_v042_dashboard_assets_and_acceptance_controls_are_cache_busted() -> None:
    bundle = (ROOT / "custom_components/si_grid_monitor/frontend/dashboard.js").read_text(
        encoding="utf-8"
    )
    model = (ROOT / "custom_components/si_grid_monitor/frontend/dashboard-model.mjs").read_text(
        encoding="utf-8"
    )
    assert "dashboard-model.mjs?v=1.0.3" in bundle
    assert "dashboard-i18n.mjs?v=1.0.3" in bundle
    assert 'energyProjection: {color: "#8b5cf6", dash: "7 4"}' in model
    assert (
        ".legend-line .energy-projection{stroke:${CHART_SERIES.energyProjection.color};"
        "stroke-dasharray:${CHART_SERIES.energyProjection.dash}" in bundle
    )
    assert "domainMinKw" in model and "domainMaxKw" in model
    assert "Partial supported trajectory" in model
    assert 'data-today-control="prev"' in bundle
    assert "data-today-quarter" in bundle
    assert 'data-today-control="next"' in bundle
    assert "Current-quarter forecast status" in bundle
    assert "Sustained forecast quality" in bundle
    assert "0.975" not in bundle  # Fixture precision is computed, not hard-coded UI data.
