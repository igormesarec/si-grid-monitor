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
