"""Release metadata, documentation and non-publishing safeguards."""

import json
from pathlib import Path

from custom_components.si_grid_monitor.archive import SCHEMA_VERSION
from custom_components.si_grid_monitor.const import VERSION

ROOT = Path(__file__).parents[1]


def test_v08_versions_and_frontend_cache_keys_are_consistent() -> None:
    manifest = json.loads(
        (ROOT / "custom_components/si_grid_monitor/manifest.json").read_text(encoding="utf-8")
    )
    dashboard = (ROOT / "custom_components/si_grid_monitor/frontend/dashboard.js").read_text(
        encoding="utf-8"
    )
    assert manifest["version"] == VERSION == "0.8.0"
    assert "dashboard-model.mjs?v=0.8.0" in dashboard
    assert "dashboard-i18n.mjs?v=0.8.0" in dashboard
    assert SCHEMA_VERSION == 6


def test_pages_workflow_builds_preview_but_cannot_deploy() -> None:
    workflow = (ROOT / ".github/workflows/pages-preview.yml").read_text(encoding="utf-8")
    site = (ROOT / "docs/index.html").read_text(encoding="utf-8")
    assert "upload-pages-artifact" in workflow
    assert "deploy-pages" not in workflow
    assert "pages: write" not in workflow
    for section in (
        "features",
        "install",
        "dashboard",
        "tariffs",
        "history",
        "quality",
        "faq",
        "development",
    ):
        assert f'id="{section}"' in site
    assert "unofficial" in site.lower()


def test_master_specification_is_not_replaced_by_v08_documentation() -> None:
    master = (ROOT / "SPECIFICATION.md").read_text(encoding="utf-8")
    assert "MASTER PRODUCT SPECIFICATION" in master
    assert "V1.1" in master
    assert "V0.8_IMPLEMENTATION_STATUS.md" in (ROOT / "README.md").read_text(encoding="utf-8")
