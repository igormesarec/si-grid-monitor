"""Shared Python/JavaScript smoothing-contract regression fixtures."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from custom_components.si_grid_monitor.engine import PowerSample, TimeWeightedBuffer

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "smoothing_parity.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", FIXTURES, ids=lambda case: case["name"])
def test_python_time_weighted_smoothing_contract(case: dict[str, object]) -> None:
    buffer = TimeWeightedBuffer(stale_after_seconds=float(case["stale_seconds"]))
    for timestamp, signed_kw in case["samples"]:
        buffer.add(PowerSample(datetime.fromisoformat(timestamp.replace("Z", "+00:00")), signed_kw))

    _signed, imported = buffer.averages(
        end=datetime.fromisoformat(str(case["end"]).replace("Z", "+00:00")),
        window_seconds=int(case["window_seconds"]),
    )

    assert imported.value_kw == pytest.approx(case["expected_import_kw"], abs=1e-9)
    assert imported.coverage_seconds == pytest.approx(case["expected_coverage_seconds"], abs=1e-9)
    assert imported.complete is case["expected_complete"]
