"""WebSocket history regression tests with genuine SQLite rows."""

from __future__ import annotations

import json
import sqlite3
import sys
import types
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from custom_components.si_grid_monitor.archive import ArchiveRecord, QuarterArchive
from custom_components.si_grid_monitor.engine import quarter_starts_for_local_day
from custom_components.si_grid_monitor.tariffs import SlovenianTariffCalendar


def _install_dashboard_import_stubs() -> None:
    """Extend the lightweight HA stubs used by runtime tests."""

    homeassistant = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    homeassistant.__path__ = []  # type: ignore[attr-defined]
    core = sys.modules.setdefault("homeassistant.core", types.ModuleType("homeassistant.core"))
    core.HomeAssistant = object  # type: ignore[attr-defined]
    core.callback = lambda function: function  # type: ignore[attr-defined]
    components = types.ModuleType("homeassistant.components")
    components.__path__ = []  # type: ignore[attr-defined]
    frontend = types.ModuleType("homeassistant.components.frontend")
    frontend.async_panel_exists = lambda *_args: False  # type: ignore[attr-defined]
    frontend.async_remove_panel = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]
    panel_custom = types.ModuleType("homeassistant.components.panel_custom")

    async def async_register_panel(*_args: Any, **_kwargs: Any) -> None:
        return None

    panel_custom.async_register_panel = async_register_panel  # type: ignore[attr-defined]
    websocket_api = types.ModuleType("homeassistant.components.websocket_api")
    websocket_api.websocket_command = lambda _schema: lambda function: function  # type: ignore[attr-defined]
    websocket_api.async_response = lambda function: function  # type: ignore[attr-defined]
    http = types.ModuleType("homeassistant.components.http")
    http.StaticPathConfig = lambda *args: args  # type: ignore[attr-defined]
    components.frontend = frontend  # type: ignore[attr-defined]
    components.panel_custom = panel_custom  # type: ignore[attr-defined]
    components.websocket_api = websocket_api  # type: ignore[attr-defined]
    voluptuous = types.ModuleType("voluptuous")
    voluptuous.Required = lambda key: key  # type: ignore[attr-defined]
    voluptuous.Optional = lambda key: key  # type: ignore[attr-defined]
    sys.modules.update(
        {
            "homeassistant.components": components,
            "homeassistant.components.frontend": frontend,
            "homeassistant.components.panel_custom": panel_custom,
            "homeassistant.components.websocket_api": websocket_api,
            "homeassistant.components.http": http,
            "homeassistant.core": core,
            "voluptuous": voluptuous,
        }
    )


_install_dashboard_import_stubs()

from custom_components.si_grid_monitor import dashboard  # noqa: E402
from custom_components.si_grid_monitor.const import DOMAIN  # noqa: E402


class _Hass:
    def __init__(self, runtime: Any) -> None:
        self.data = {DOMAIN: {dashboard.DATA_RUNTIMES: {runtime.entry.entry_id: runtime}}}

    async def async_add_executor_job(self, function: Any, *args: Any) -> Any:
        return function(*args)


class _SnapshotOrderingHass(_Hass):
    def __init__(self, runtime: Any, calls: dict[str, int]) -> None:
        super().__init__(runtime)
        self.calls = calls
        self.executor_invocations = 0

    async def async_add_executor_job(self, function: Any, *args: Any) -> Any:
        self.executor_invocations += 1
        assert self.calls["dashboard_current"] == 1
        return function(*args)


class _Connection:
    def __init__(self) -> None:
        self.result: Any = None
        self.error: tuple[int, str, str] | None = None

    def send_result(self, _message_id: int, result: Any) -> None:
        self.result = result

    def send_error(self, message_id: int, code: str, message: str) -> None:
        self.error = (message_id, code, message)


def _run(coroutine: Any) -> Any:
    """Drive these synchronous test coroutines without a Windows event-loop socketpair."""

    try:
        while True:
            coroutine.send(None)
    except StopIteration as completed:
        return completed.value


def _record(start: datetime, index: int, *, incomplete: bool = False) -> ArchiveRecord:
    target = 3.5
    import_kwh = 0.2 + index * 0.01
    demand = import_kwh / 0.25
    quality = "incomplete" if incomplete else "reconstructed"
    confirmed = None if incomplete else demand > target
    return ArchiveRecord(
        namespace="meter-a",
        start_utc=start,
        end_utc=start + timedelta(minutes=15),
        import_kwh=import_kwh,
        export_kwh=0.03 if index % 2 else 0.0,
        signed_average_kw=(import_kwh - (0.03 if index % 2 else 0.0)) / 0.25,
        import_demand_kw=demand,
        coverage_seconds=450 if incomplete else 900,
        gap_seconds=450 if incomplete else 0,
        quality=quality,
        provenance="live_reconstructed",
        source_id="sensor.grid",
        source_epoch=1,
        configuration_status="known",
        contractual_target_kw=target,
        safety_margin_kw=0.0,
        operational_target_kw=target,
        utilization_pct=None if incomplete else 100 * demand / target,
        exceeded=confirmed,
        excess_kw=None if incomplete else max(0.0, demand - target),
        tariff_block=1,
        tariff_rule_version="si-2026-verified",
        tariff_calendar_year=2026,
        tariff_season="higher",
        tariff_day_type="working_day",
        tariff_rule_status="official",
        tariff_source_url="https://www.uro.si/",
        tariff_policy="official_only",
        contractual_status="confirmed" if not incomplete else "measurement_incomplete",
        confirmed_exceeded=confirmed,
        target_effective_from="2026-01-01",
        target_effective_to="2026-12-31",
        target_provenance="distributor_record",
        target_recorded_on="2025-10-17",
    )


def _runtime(archive: QuarterArchive) -> Any:
    calendar = SlovenianTariffCalendar()
    return SimpleNamespace(
        entry=SimpleNamespace(entry_id="entry-a", title="Meter A"),
        archive=archive,
        namespace="meter-a",
        tariff_calendar=calendar,
        target_for_tariff=lambda tariff: 3.5 if tariff.block is not None else None,
        dashboard_current=lambda: {"available": False, "now_utc": "2026-01-02T12:00:00+00:00"},
    )


def test_history_commands_use_real_sqlite_rows_and_preserve_archive(tmp_path: Path) -> None:
    archive = QuarterArchive(tmp_path / "history.db")
    archive.open()
    starts = quarter_starts_for_local_day(date(2026, 1, 2))
    archive.register_configuration_epoch(
        namespace="meter-a",
        source_id="sensor.grid",
        positive_means_import=True,
        contractual_target_kw=3.5,
        safety_margin_kw=0.0,
        effective_utc=starts[0],
    )
    for index, start in enumerate(starts[:8]):
        archive.upsert_quarter(_record(start, index, incomplete=index == 7))

    raw_rows = archive.list_quarters("meter-a", starts[0], starts[8])
    assert len(raw_rows) == 8
    assert isinstance(raw_rows[0], sqlite3.Row)
    assert dashboard._row(raw_rows[0])["namespace"] == "meter-a"
    before = [dict(row) for row in raw_rows]

    runtime = _runtime(archive)
    hass = _Hass(runtime)
    quarter_connection = _Connection()
    _run(
        dashboard.ws_quarter(
            hass,
            quarter_connection,
            {"id": 1, "entry_id": "entry-a", "start_utc": starts[0].isoformat()},
        )
    )
    assert quarter_connection.error is None
    assert quarter_connection.result["status"] == "found"
    assert quarter_connection.result["quarter"]["target_provenance"] == "distributor_record"
    json.dumps(quarter_connection.result)

    incomplete_connection = _Connection()
    _run(
        dashboard.ws_quarter(
            hass,
            incomplete_connection,
            {"id": 2, "entry_id": "entry-a", "start_utc": starts[7].isoformat()},
        )
    )
    assert incomplete_connection.result["status"] == "unavailable"
    assert incomplete_connection.result["quarter"]["quality"] == "incomplete"

    empty_connection = _Connection()
    _run(
        dashboard.ws_quarter(
            hass,
            empty_connection,
            {"id": 3, "entry_id": "entry-a", "start_utc": starts[20].isoformat()},
        )
    )
    assert empty_connection.result == {
        "status": "not_found",
        "quarter": None,
        "detailed_trace_available": False,
    }

    day_connection = _Connection()
    _run(
        dashboard.ws_day(
            hass,
            day_connection,
            {"id": 4, "entry_id": "entry-a", "date": "2026-01-02"},
        )
    )
    assert day_connection.error is None
    assert day_connection.result["status"] == "ok"
    assert day_connection.result["summary"]["valid_count"] == 7
    assert day_connection.result["summary"]["incomplete_count"] == 1
    assert len(day_connection.result["quarters"]) == 96
    json.dumps(day_connection.result)

    period_connection = _Connection()
    _run(
        dashboard.ws_period(
            hass,
            period_connection,
            {
                "id": 40,
                "entry_id": "entry-a",
                "period_type": "day",
                "anchor": "2026-01-02",
            },
        )
    )
    assert period_connection.error is None
    assert period_connection.result["summary"]["valid_count"] == 7
    assert period_connection.result["summary"]["incomplete_count"] == 1
    assert period_connection.result["summary"]["expected_completed_count"] == 52
    assert period_connection.result["summary"]["missing_count"] == 44
    assert period_connection.result["period"]["resolution"] == "quarter"
    json.dumps(period_connection.result)

    blocks_connection = _Connection()
    _run(
        dashboard.ws_blocks(
            hass,
            blocks_connection,
            {
                "id": 41,
                "entry_id": "entry-a",
                "period_type": "day",
                "anchor": "2026-01-02",
            },
        )
    )
    assert blocks_connection.error is None
    assert len(blocks_connection.result["blocks"]) == 5
    assert sum(row["valid_count"] for row in blocks_connection.result["blocks"]) == 7
    json.dumps(blocks_connection.result)

    exceedance_connection = _Connection()
    _run(
        dashboard.ws_exceedances(
            hass,
            exceedance_connection,
            {
                "id": 42,
                "entry_id": "entry-a",
                "period_type": "day",
                "anchor": "2026-01-02",
                "sort_by": "date",
                "direction": "desc",
                "page": 1,
                "page_size": 25,
            },
        )
    )
    assert exceedance_connection.error is None
    assert exceedance_connection.result["status"] == "empty"
    assert exceedance_connection.result["pagination"]["total"] == 0
    json.dumps(exceedance_connection.result)

    empty_day = _Connection()
    _run(
        dashboard.ws_day(
            hass,
            empty_day,
            {"id": 5, "entry_id": "entry-a", "date": "2026-01-01"},
        )
    )
    assert empty_day.result["status"] == "ok"
    assert empty_day.result["summary"]["valid_count"] == 0
    assert empty_day.result["summary"]["missing_count"] == 96

    after = [dict(row) for row in archive.list_quarters("meter-a", starts[0], starts[8])]
    assert after == before
    assert archive.schema_version == 6
    archive.close()


def test_exceedances_snapshots_live_time_once_before_executor(tmp_path: Path) -> None:
    archive = QuarterArchive(tmp_path / "exceedance-snapshot.db")
    archive.open()
    runtime = _runtime(archive)
    calls = {"dashboard_current": 0}

    def dashboard_current() -> dict[str, object]:
        calls["dashboard_current"] += 1
        return {"available": False, "now_utc": "2026-01-02T12:00:00+00:00"}

    runtime.dashboard_current = dashboard_current
    hass = _SnapshotOrderingHass(runtime, calls)
    connection = _Connection()
    _run(
        dashboard.ws_exceedances(
            hass,
            connection,
            {
                "id": 43,
                "entry_id": "entry-a",
                "period_type": "day",
                "anchor": "2026-01-02",
            },
        )
    )
    assert connection.error is None
    assert connection.result["period"]["completed_end_utc"] == "2026-01-02T12:00:00+00:00"
    assert calls["dashboard_current"] == 1
    assert hass.executor_invocations == 1
    archive.close()


class _BrokenArchive:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def list_quarters(self, *_args: Any) -> list[Any]:
        raise self.error


def test_history_commands_return_safe_errors_for_archive_and_bad_rows() -> None:
    for operation, error, expected in (
        ("quarter", sqlite3.OperationalError("private database detail"), "archive_unavailable"),
        ("quarter", RuntimeError("malformed record"), "quarter_query_failed"),
        ("day", sqlite3.OperationalError("private database detail"), "archive_unavailable"),
        ("day", RuntimeError("malformed record"), "day_query_failed"),
    ):
        runtime = _runtime(_BrokenArchive(error))  # type: ignore[arg-type]
        connection = _Connection()
        message = {"id": 8, "entry_id": "entry-a"}
        if operation == "quarter":
            message["start_utc"] = "2026-01-02T00:00:00+00:00"
            _run(dashboard.ws_quarter(_Hass(runtime), connection, message))
        else:
            message["date"] = "2026-01-02"
            _run(dashboard.ws_day(_Hass(runtime), connection, message))
        assert connection.error is not None
        assert connection.error[1] == expected
        assert "private database detail" not in connection.error[2]
        assert "malformed record" not in connection.error[2]

    for operation, handler, expected in (
        ("period", dashboard.ws_period, "period_query_failed"),
        ("blocks", dashboard.ws_blocks, "blocks_query_failed"),
        ("exceedances", dashboard.ws_exceedances, "exceedances_query_failed"),
    ):
        runtime = _runtime(_BrokenArchive(RuntimeError("private archive detail")))  # type: ignore[arg-type]
        connection = _Connection()
        _run(
            handler(
                _Hass(runtime),
                connection,
                {
                    "id": 9,
                    "entry_id": "entry-a",
                    "period_type": "day",
                    "anchor": "2026-01-02",
                },
            )
        )
        assert connection.error is not None, operation
        assert connection.error[1] == expected
        assert "private archive detail" not in connection.error[2]


def test_period_command_rejects_invalid_ranges_and_blocks(tmp_path: Path) -> None:
    archive = QuarterArchive(tmp_path / "period-validation.db")
    archive.open()
    runtime = _runtime(archive)
    for message in (
        {
            "period_type": "custom",
            "anchor": "2026-01-01",
            "custom_start": "2026-01-02",
            "custom_end": "2026-01-01",
        },
        {"period_type": "day", "anchor": "not-a-date"},
        {"period_type": "month", "anchor": "2026-01-01", "tariff_block": 6},
    ):
        connection = _Connection()
        _run(
            dashboard.ws_period(
                _Hass(runtime),
                connection,
                {"id": 50, "entry_id": "entry-a", **message},
            )
        )
        assert connection.error is not None
        assert connection.error[1] == "invalid_period"
    archive.close()


def test_exceedance_command_rejects_unsafe_sort_and_pagination(tmp_path: Path) -> None:
    archive = QuarterArchive(tmp_path / "exceedance-validation.db")
    archive.open()
    runtime = _runtime(archive)
    for extra in (
        {"sort_by": "start_utc; DROP TABLE quarters"},
        {"direction": "sideways"},
        {"page": 0},
        {"page": 1_000_001},
        {"page_size": 101},
    ):
        connection = _Connection()
        _run(
            dashboard.ws_exceedances(
                _Hass(runtime),
                connection,
                {
                    "id": 60,
                    "entry_id": "entry-a",
                    "period_type": "day",
                    "anchor": "2026-01-02",
                    **extra,
                },
            )
        )
        assert connection.error is not None
        assert connection.error[1] == "invalid_query"
    archive.close()


def test_history_command_pages_real_rows_and_serializes_storage(tmp_path: Path) -> None:
    archive = QuarterArchive(tmp_path / "history-page.db")
    archive.open()
    starts = quarter_starts_for_local_day(date(2026, 1, 2))
    for index, start in enumerate(starts[:7]):
        archive.upsert_quarter(_record(start, index, incomplete=index == 6))
    runtime = _runtime(archive)
    connection = _Connection()
    _run(
        dashboard.ws_history(
            _Hass(runtime),
            connection,
            {
                "id": 70,
                "entry_id": "entry-a",
                "start_date": "2026-01-02",
                "end_date": "2026-01-02",
                "page": 1,
                "page_size": 3,
                "direction": "asc",
            },
        )
    )
    assert connection.error is None
    assert len(connection.result["items"]) == 3
    assert connection.result["pagination"]["total"] == 7
    assert connection.result["summary"]["missing_count"] == 89
    assert connection.result["storage"]["schema_version"] == 6
    json.dumps(connection.result)
    archive.close()
