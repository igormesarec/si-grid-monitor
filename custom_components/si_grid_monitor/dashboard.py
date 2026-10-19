"""Authenticated dashboard API and automatic Home Assistant sidebar panel."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback

from .const import (
    DOMAIN,
    FRONTEND_URL,
    PANEL_ICON,
    PANEL_TITLE,
    PANEL_URL_PATH,
    VERSION,
)
from .dashboard_models import build_day_view
from .engine import quarter_starts_for_local_day

DATA_RUNTIMES = "runtimes"
DATA_FRONTEND_READY = "frontend_ready"
DATA_COMMANDS_READY = "commands_ready"

_LOGGER = logging.getLogger(__name__)


def _json(value: Any) -> Any:
    """Convert domain objects into WebSocket-safe values."""

    if is_dataclass(value):
        return _json(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def _runtime(hass: HomeAssistant, msg: dict[str, Any]) -> Any:
    runtimes = hass.data.get(DOMAIN, {}).get(DATA_RUNTIMES, {})
    entry_id = msg.get("entry_id")
    if entry_id is not None:
        return runtimes.get(entry_id)
    return next(iter(runtimes.values()), None)


def _entry_list(hass: HomeAssistant) -> list[dict[str, str]]:
    runtimes = hass.data.get(DOMAIN, {}).get(DATA_RUNTIMES, {})
    return [
        {"entry_id": entry_id, "title": runtime.entry.title}
        for entry_id, runtime in runtimes.items()
    ]


def _row(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}  # noqa: SIM118 - sqlite3.Row values differ


def _history_error(
    connection: Any,
    msg: dict[str, Any],
    *,
    operation: str,
    requested: str,
    code: str,
    message: str,
) -> None:
    """Log full diagnostics while returning a privacy-safe WebSocket error."""

    _LOGGER.exception(
        "SI Grid Monitor historical API failed: operation=%s entry_id=%s request=%s",
        operation,
        msg.get("entry_id"),
        requested,
    )
    connection.send_error(msg["id"], code, message)


async def async_setup_dashboard(hass: HomeAssistant) -> None:
    """Register assets and authenticated commands exactly once."""

    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data.setdefault(DATA_RUNTIMES, {})
    if not domain_data.get(DATA_COMMANDS_READY):
        for handler in (
            ws_entries,
            ws_current,
            ws_quarter,
            ws_day,
            ws_calendar,
            ws_transitions,
            ws_archive_status,
        ):
            websocket_api.async_register_command(hass, handler)
        domain_data[DATA_COMMANDS_READY] = True
    if not domain_data.get(DATA_FRONTEND_READY):
        frontend_dir = Path(__file__).parent / "frontend"
        await hass.http.async_register_static_paths(
            [StaticPathConfig(FRONTEND_URL, str(frontend_dir), True)]
        )
        domain_data[DATA_FRONTEND_READY] = True


async def async_register_panel(hass: HomeAssistant) -> None:
    """Create the branded sidebar entry when the first config entry loads."""

    if frontend.async_panel_exists(hass, PANEL_URL_PATH):
        return
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="si-grid-monitor-panel",
        frontend_url_path=PANEL_URL_PATH,
        module_url=f"{FRONTEND_URL}/dashboard.js?v={VERSION}",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        require_admin=False,
        config={"version": VERSION},
        config_panel_domain=DOMAIN,
        handle_safe_area=True,
    )


def async_unregister_panel(hass: HomeAssistant) -> None:
    """Remove only the panel owned by this integration."""

    frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/entries"})
@callback
def ws_entries(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    connection.send_result(msg["id"], {"entries": _entry_list(hass), "version": VERSION})


_ENTRY_SCHEMA = {vol.Optional("entry_id"): str}


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/current", **_ENTRY_SCHEMA})
@websocket_api.async_response
async def ws_current(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    runtime = _runtime(hass, msg)
    if runtime is None:
        connection.send_error(msg["id"], "entry_not_found", "SI Grid Monitor entry not found")
        return
    connection.send_result(msg["id"], runtime.dashboard_current())


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/quarter",
        vol.Required("start_utc"): str,
        **_ENTRY_SCHEMA,
    }
)
@websocket_api.async_response
async def ws_quarter(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    runtime = _runtime(hass, msg)
    if runtime is None:
        connection.send_error(msg["id"], "entry_not_found", "SI Grid Monitor entry not found")
        return
    try:
        parsed = datetime.fromisoformat(msg["start_utc"])
        if parsed.tzinfo is None:
            raise ValueError("UTC quarter timestamp must include an offset")
        start = parsed.astimezone(UTC)
    except (TypeError, ValueError):
        connection.send_error(msg["id"], "invalid_date", "Invalid UTC quarter timestamp")
        return
    try:
        rows = await hass.async_add_executor_job(
            runtime.archive.list_quarters,
            runtime.namespace,
            start,
            start + timedelta(minutes=15),
        )
        quarter = _row(rows[0]) if rows else None
    except sqlite3.Error:
        _history_error(
            connection,
            msg,
            operation="quarter",
            requested=start.isoformat(),
            code="archive_unavailable",
            message="Historical archive is temporarily unavailable",
        )
        return
    except Exception:
        _history_error(
            connection,
            msg,
            operation="quarter",
            requested=start.isoformat(),
            code="quarter_query_failed",
            message="Could not retrieve the selected quarter",
        )
        return
    status = (
        "not_found"
        if quarter is None
        else "unavailable"
        if quarter.get("quality") in {"incomplete", "unavailable"}
        else "found"
    )
    connection.send_result(
        msg["id"],
        {
            "status": status,
            "quarter": quarter,
            "detailed_trace_available": False,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/day",
        vol.Required("date"): str,
        **_ENTRY_SCHEMA,
    }
)
@websocket_api.async_response
async def ws_day(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    runtime = _runtime(hass, msg)
    if runtime is None:
        connection.send_error(msg["id"], "entry_not_found", "SI Grid Monitor entry not found")
        return
    try:
        local_date = date.fromisoformat(msg["date"])
    except (TypeError, ValueError):
        connection.send_error(msg["id"], "invalid_date", "Invalid local date")
        return
    try:
        starts = quarter_starts_for_local_day(local_date)
        start, end = starts[0], starts[-1] + timedelta(minutes=15)
        stored = await hass.async_add_executor_job(
            runtime.archive.list_quarters, runtime.namespace, start, end
        )
        rows = [_row(row) for row in stored]
        live = runtime.dashboard_current()
        now = datetime.fromisoformat(str(live.get("now_utc"))).astimezone(UTC) if live.get(
            "now_utc"
        ) else datetime.now(UTC)
        response = build_day_view(
            runtime=runtime,
            local_date=local_date,
            rows=rows,
            now_utc=now,
            live=live,
        )
    except sqlite3.Error:
        _history_error(
            connection,
            msg,
            operation="day",
            requested=local_date.isoformat(),
            code="archive_unavailable",
            message="Historical archive is temporarily unavailable",
        )
        return
    except Exception:
        _history_error(
            connection,
            msg,
            operation="day",
            requested=local_date.isoformat(),
            code="day_query_failed",
            message="Could not load the selected day's measurements",
        )
        return
    connection.send_result(
        msg["id"],
        {"status": "ok", **response},
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/calendar",
        vol.Required("date"): str,
        **_ENTRY_SCHEMA,
    }
)
@websocket_api.async_response
async def ws_calendar(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    runtime = _runtime(hass, msg)
    if runtime is None:
        connection.send_error(msg["id"], "entry_not_found", "SI Grid Monitor entry not found")
        return
    try:
        selected = date.fromisoformat(msg["date"])
    except (TypeError, ValueError):
        connection.send_error(msg["id"], "invalid_date", "Invalid local date")
        return
    if not 2026 <= selected.year <= 2030:
        connection.send_error(msg["id"], "out_of_range", "Calendar supports 2026 through 2030")
        return
    rows = []
    for item in runtime.tariff_calendar.daily_view(selected):
        tariff = runtime.tariff_calendar.classify(item["start_utc"])
        rows.append({**_json(item), "target_kw": runtime.target_for_tariff(tariff)})
    first = rows[0] if rows else {}
    day_classification = (
        "public_holiday"
        if first.get("holiday_name")
        else "weekend"
        if selected.weekday() >= 5
        else "working_day"
    )
    connection.send_result(
        msg["id"],
        {
            "date": selected.isoformat(),
            "hours": rows,
            "day_classification": day_classification,
            "season": first.get("season"),
            "holiday_name": first.get("holiday_name"),
        },
    )


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/transitions", **_ENTRY_SCHEMA})
@websocket_api.async_response
async def ws_transitions(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    runtime = _runtime(hass, msg)
    if runtime is None:
        connection.send_error(msg["id"], "entry_not_found", "SI Grid Monitor entry not found")
        return
    connection.send_result(msg["id"], runtime.dashboard_transitions())


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/archive_status", **_ENTRY_SCHEMA}
)
@websocket_api.async_response
async def ws_archive_status(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    runtime = _runtime(hass, msg)
    if runtime is None:
        connection.send_error(msg["id"], "entry_not_found", "SI Grid Monitor entry not found")
        return
    latest, schema_version = await asyncio.gather(
        hass.async_add_executor_job(runtime.archive.latest_quarter_end, runtime.namespace),
        hass.async_add_executor_job(lambda: runtime.archive.schema_version),
    )
    connection.send_result(
        msg["id"],
        {
            "schema_version": schema_version,
            "latest_quarter_end_utc": _json(latest),
            "namespace": runtime.namespace,
            "retention": runtime.settings["retention"],
        },
    )
