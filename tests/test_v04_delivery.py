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
    assert manifest["version"] == VERSION == "0.4.0"
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
    assert "localStorage" not in bundle
    assert "setInterval(()=>this._tick(),1000)" in bundle


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
    bundle = (
        ROOT / "custom_components/si_grid_monitor/frontend/dashboard.js"
    ).read_text(encoding="utf-8")
    # Bind date/hour and quarter selection to a visible detail view.
    assert 'data-quarter=' in bundle
    assert "Selected 15-minute interval" in bundle
    assert "this._historicalCard()" in bundle
    assert 'data-hour=' in bundle
    assert "Selected hour" in bundle
    assert "this._selectedHourUtc=x.dataset.hour" in bundle
    # Same B1..B5 CSS convention for all daily intervals, with a stepped
    # contractual limit reference computed from each individual quarter.
    assert 'class="bar b${esc(q.tariff_block||0)}' in bundle
    assert 'class="target-segment"' in bundle
    assert "q.contractual_target_kw" in bundle
    assert "No archived summary for this interval" in bundle


def test_future_limit_message_distinguishes_forecast_horizon() -> None:
    bundle = (
        ROOT / "custom_components/si_grid_monitor/frontend/dashboard.js"
    ).read_text(encoding="utf-8")
    assert "lower.inside_sustained_horizon" in bundle
    assert "Horizon-wide sustained MUST REDUCE" in bundle
    assert "outside the sustained forecast horizon" in bundle
    assert "forecast advice unavailable" in bundle
