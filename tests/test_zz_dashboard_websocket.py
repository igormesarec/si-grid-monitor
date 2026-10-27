"""WebSocket history regression tests with genuine SQLite rows."""

from __future__ import annotations

import json
import sqlite3
import sys
import types
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from custom_components.si_grid_monitor.archive import (
    ArchiveRecord,
    ContractAuditEvent,
    QuarterArchive,
)
from custom_components.si_grid_monitor.contracted_power import (
    ContractedPowerPeriod,
    ContractedPowerSchedule,
)
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
    voluptuous.Required = lambda key, **_kwargs: key  # type: ignore[attr-defined]
    voluptuous.Optional = lambda key, **_kwargs: key  # type: ignore[attr-defined]
    voluptuous.In = lambda values: values  # type: ignore[attr-defined]
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
    def __init__(self, *, is_admin: bool = True) -> None:
        self.result: Any = None
        self.error: tuple[int, str, str] | None = None
        self.user = SimpleNamespace(is_admin=is_admin)

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


def test_multiple_meters_share_one_sidebar_panel(monkeypatch: Any) -> None:
    """Panel registration remains global rather than one panel per meter entry."""

    exists = False
    registrations: list[dict[str, Any]] = []

    def panel_exists(_hass: Any, _path: str) -> bool:
        return exists

    async def register(_hass: Any, **kwargs: Any) -> None:
        nonlocal exists
        registrations.append(kwargs)
        exists = True

    monkeypatch.setattr(dashboard.frontend, "async_panel_exists", panel_exists)
    monkeypatch.setattr(dashboard.panel_custom, "async_register_panel", register)
    hass = SimpleNamespace(
        data={DOMAIN: {dashboard.DATA_RUNTIMES: {"meter-a": object(), "meter-b": object()}}}
    )

    assert _run(dashboard.async_register_panel(hass)) is True
    assert _run(dashboard.async_register_panel(hass)) is False
    assert len(registrations) == 1
    assert registrations[0]["frontend_url_path"] == "si-grid-monitor"
    assert "config_panel_domain" not in registrations[0]
    assert registrations[0]["config"] == {"version": dashboard.VERSION}


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
    schedule = ContractedPowerSchedule(
        (
            ContractedPowerPeriod(
                date(2026, 1, 1),
                date(2026, 12, 31),
                (3.5, 3.5, 3.5, 3.5, 3.5),
                "test_fixture",
            ),
        )
    )
    return SimpleNamespace(
        entry=SimpleNamespace(entry_id="entry-a", title="Meter A"),
        archive=archive,
        namespace="meter-a",
        tariff_calendar=calendar,
        contracted_power_schedule=schedule,
        _contracted_power_configuration_error=None,
        target_for_tariff=lambda tariff: 3.5 if tariff.block is not None else None,
        dashboard_current=lambda: {"available": False, "now_utc": "2026-01-02T12:00:00+00:00"},
    )


def test_entries_command_exposes_each_meter_installation_language() -> None:
    runtimes = {
        "entry-a": SimpleNamespace(
            entry=SimpleNamespace(title="Meter A", data={"preferred_language": "sl"}, options={})
        ),
        "entry-b": SimpleNamespace(entry=SimpleNamespace(title="Meter B", data={}, options={})),
    }
    hass = SimpleNamespace(data={DOMAIN: {dashboard.DATA_RUNTIMES: runtimes}})
    connection = SimpleNamespace(
        send_result=lambda _id, result: setattr(connection, "result", result)
    )
    dashboard.ws_entries(hass, connection, {"id": 1})
    assert connection.result["entries"] == [
        {"entry_id": "entry-a", "title": "Meter A", "preferred_language": "sl"},
        {"entry_id": "entry-b", "title": "Meter B", "preferred_language": "en"},
    ]


def test_publishing_command_aggregates_selected_meter_without_recorder_scan() -> None:
    metrics = {
        "publishing_evaluations_per_minute": 62.0,
        "internal_timer_ticks_per_minute": 60.0,
        "publications_per_minute": 1.5,
        "publications_in_window": 90,
        "suppressed_unchanged": 1000,
        "suppressed_policy": 200,
        "suppressed_attribute_only": 25,
        "critical_publications": 2,
        "processing_failures": 1,
        "effective_current_measurement_interval_seconds": 900,
        "effective_quarter_accumulation_interval_seconds": 180,
        "last_successful_publication_utc": "2026-10-25T12:00:00+00:00",
        "estimated_total_bytes_per_year": 320_000_000,
        "estimate_status": "ready",
        "event_history_truncated": False,
    }
    runtimes = {
        "entry-a": SimpleNamespace(
            entry=SimpleNamespace(title="Meter A"),
            publishing=SimpleNamespace(diagnostics=lambda _now, _window: dict(metrics)),
        ),
        "entry-b": SimpleNamespace(
            entry=SimpleNamespace(title="Meter B"),
            publishing=SimpleNamespace(diagnostics=lambda _now, _window: dict(metrics)),
        ),
    }
    hass = SimpleNamespace(data={DOMAIN: {dashboard.DATA_RUNTIMES: runtimes}})
    connection = _Connection()
    dashboard.ws_publishing(
        hass,
        connection,
        {"id": 2, "entry_id": "entry-b", "window_seconds": 86400},
    )

    assert connection.result["meter_count"] == 1
    assert connection.result["meters"][0]["title"] == "Meter B"
    assert connection.result["totals"]["publications_in_window"] == 90
    assert connection.result["totals"]["budget_utilization_pct"] == 32.0
    assert connection.result["totals"]["publishing_evaluations_per_minute"] == 62.0
    assert connection.result["totals"]["internal_timer_ticks_per_minute"] == 60.0
    assert connection.result["totals"]["influxdb_physical_storage_verified"] is False
    assert connection.result["totals"]["processing_failures"] == 1
    assert connection.result["totals"]["effective_quarter_accumulation_interval_seconds"] == 180


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
    assert archive.schema_version == 7
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
    assert connection.result["summary"]["completed_expected_count"] == 52
    assert connection.result["summary"]["future_or_uncompleted_count"] == 44
    assert connection.result["summary"]["missing_count"] == 45
    assert connection.result["storage"]["schema_version"] == 7
    json.dumps(connection.result)
    archive.close()


def test_history_command_preserves_confirmed_false_and_null_filters(tmp_path: Path) -> None:
    archive = QuarterArchive(tmp_path / "history-status.db")
    archive.open()
    starts = quarter_starts_for_local_day(date(2026, 1, 2))
    yes = replace(_record(starts[0], 300), confirmed_exceeded=True, exceeded=True)
    no = replace(_record(starts[1], 0), confirmed_exceeded=False, exceeded=False)
    unknown = replace(
        _record(starts[2], 0, incomplete=True),
        confirmed_exceeded=None,
        exceeded=None,
    )
    for record in (yes, no, unknown):
        archive.upsert_quarter(record)
    runtime = _runtime(archive)
    expected = {
        "confirmed_yes": [True],
        "confirmed_no": [False],
        "unconfirmed": [None],
        "all": [True, False, None],
    }
    for status, values in expected.items():
        connection = _Connection()
        _run(
            dashboard.ws_history(
                _Hass(runtime),
                connection,
                {
                    "id": 71,
                    "entry_id": "entry-a",
                    "start_date": "2026-01-02",
                    "end_date": "2026-01-02",
                    "exceedance_status": status,
                    "direction": "asc",
                },
            )
        )
        assert connection.error is None
        assert [item["confirmed_exceeded"] for item in connection.result["items"]] == values
    archive.close()


def test_historical_calendar_never_fills_unknown_archived_target_from_epoch(
    tmp_path: Path,
) -> None:
    archive = QuarterArchive(tmp_path / "calendar-evidence.db")
    archive.open()
    starts = quarter_starts_for_local_day(date(2026, 1, 2))
    schedule = ContractedPowerSchedule(
        (
            ContractedPowerPeriod(
                date(2026, 1, 1),
                date(2026, 12, 31),
                (3.5, 3.5, 3.5, 3.5, 3.5),
                "historical_fixture",
            ),
        )
    )
    archive.register_configuration_epoch(
        namespace="meter-a",
        source_id="sensor.grid",
        positive_means_import=True,
        contractual_target_kw=3.5,
        safety_margin_kw=0.0,
        block_targets_kw=(3.5, 3.5, 3.5, 3.5, 3.5),
        allow_provisional_tariff=False,
        contracted_power_schedule=schedule,
        effective_utc=starts[0],
    )
    archive.upsert_quarter(
        replace(
            _record(starts[0], 0, incomplete=True),
            contractual_target_kw=None,
            target_provenance=None,
            contractual_status="target_unknown",
        )
    )
    archive.upsert_quarter(_record(starts[8], 0, incomplete=True))

    connection = _Connection()
    _run(
        dashboard.ws_calendar(
            _Hass(_runtime(archive)),
            connection,
            {"id": 80, "entry_id": "entry-a", "date": "2026-01-02"},
        )
    )
    assert connection.error is None
    first, missing, evidenced = connection.result["hours"][:3]
    assert first["archived_quarter_present"] is True
    assert first["as_recorded_target_kw"] is None
    assert first["display_target_kw"] is None
    assert first["as_recorded_source"] == "archived_quarter_unknown"
    assert first["historical_configuration_target_kw"] == 3.5
    assert missing["archived_quarter_present"] is False
    assert missing["as_recorded_target_kw"] is None
    assert missing["display_target_kw"] is None
    assert missing["historical_configuration_target_kw"] == 3.5
    assert evidenced["as_recorded_target_kw"] == 3.5
    assert evidenced["display_target_kw"] == 3.5
    assert evidenced["as_recorded_source"] == "archived_quarter"
    json.dumps(connection.result)
    archive.close()


def test_contracts_websocket_pages_audit_and_exposes_separate_evidence(tmp_path: Path) -> None:
    archive = QuarterArchive(tmp_path / "contracts-report.db")
    archive.open()
    starts = quarter_starts_for_local_day(date(2026, 1, 2))
    runtime = _runtime(archive)
    archive.register_configuration_epoch(
        namespace="meter-a",
        source_id="sensor.grid",
        positive_means_import=True,
        contractual_target_kw=3.5,
        safety_margin_kw=0.0,
        block_targets_kw=(3.5, 3.5, 3.5, 3.5, 3.5),
        allow_provisional_tariff=False,
        contracted_power_schedule=runtime.contracted_power_schedule,
        effective_utc=starts[0],
    )
    archive.upsert_quarter(_record(starts[0], 0))
    for index in range(55):
        archive.append_contract_audit(
            ContractAuditEvent(
                f"event-{index:02d}",
                "meter-a",
                starts[0] + timedelta(minutes=index),
                "CORRECTED",
                "[]",
                "[]",
                "2026-01-01",
                "2026-12-31",
                "fixture",
                None,
                "user_action",
                None,
                f"revision-{index}",
            )
        )
    connection = _Connection()
    _run(
        dashboard.ws_contracts(
            _Hass(runtime),
            connection,
            {
                "id": 81,
                "entry_id": "entry-a",
                "audit_page": 2,
                "audit_page_size": 50,
            },
        )
    )
    assert connection.error is None
    assert len(connection.result["audit_events"]) == 5
    assert connection.result["audit_pagination"] == {
        "page": 2,
        "page_size": 50,
        "total": 55,
        "pages": 2,
    }
    assert len(connection.result["historical_configuration"]) == 1
    assert len(connection.result["archived_target_evidence"]) == 1
    assert connection.result["management"]["direct_options_supported"] is False
    assert 'meter named "Meter A"' in connection.result["management"]["instruction"]
    json.dumps(connection.result)

    non_admin = _Connection(is_admin=False)
    _run(
        dashboard.ws_contracts(
            _Hass(runtime),
            non_admin,
            {"id": 82, "entry_id": "entry-a", "audit_page": 1, "audit_page_size": 10},
        )
    )
    assert non_admin.error is None
    assert non_admin.result["management"]["supported"] is False
    archive.close()


def test_historical_calendar_dst_fallback_keeps_two_unknown_recorded_hours(
    tmp_path: Path, monkeypatch: Any
) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2026, 10, 26, 12, 0, tzinfo=UTC)
            return value if tz is None else value.astimezone(tz)

    monkeypatch.setattr(dashboard, "datetime", FrozenDateTime)
    archive = QuarterArchive(tmp_path / "calendar-dst.db")
    archive.open()
    connection = _Connection()
    _run(
        dashboard.ws_calendar(
            _Hass(_runtime(archive)),
            connection,
            {"id": 82, "entry_id": "entry-a", "date": "2026-10-25"},
        )
    )
    repeated = [
        item for item in connection.result["hours"] if item["local_datetime"][11:13] == "02"
    ]
    assert len(repeated) == 2
    assert repeated[0]["start_utc"] != repeated[1]["start_utc"]
    assert {item["fold"] for item in repeated} == {0, 1}
    assert all(item["display_target_kw"] is None for item in repeated)
    assert all(item["current_configuration_target_kw"] == 3.5 for item in repeated)
    archive.close()
