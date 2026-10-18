"""Authenticated dashboard API and automatic Home Assistant sidebar panel."""

from __future__ import annotations

import asyncio
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
from .engine import quarter_starts_for_local_day

DATA_RUNTIMES = "runtimes"
DATA_FRONTEND_READY = "frontend_ready"
DATA_COMMANDS_READY = "commands_ready"


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
    return {key: row[key] for key in row}


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
        start = datetime.fromisoformat(msg["start_utc"]).astimezone(UTC)
    except ValueError:
        connection.send_error(msg["id"], "invalid_date", "Invalid UTC quarter timestamp")
        return
    rows = await hass.async_add_executor_job(
        runtime.archive.list_quarters, runtime.namespace, start, start + timedelta(minutes=15)
    )
    connection.send_result(
        msg["id"],
        {"quarter": _row(rows[0]) if rows else None, "detailed_trace_available": False},
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
    except ValueError:
        connection.send_error(msg["id"], "invalid_date", "Invalid local date")
        return
    starts = quarter_starts_for_local_day(local_date)
    start, end = starts[0], starts[-1] + timedelta(minutes=15)
    rows, summary = await asyncio.gather(
        hass.async_add_executor_job(runtime.archive.list_quarters, runtime.namespace, start, end),
        hass.async_add_executor_job(runtime.archive.summarize, runtime.namespace, start, end),
    )
    by_start = {str(row["start_utc"]): _row(row) for row in rows}
    quarters: list[dict[str, Any]] = []
    for quarter_start in starts:
        key = quarter_start.isoformat()
        stored = by_start.get(key)
        tariff = runtime.tariff_calendar.classify(quarter_start)
        quarters.append(
            stored
            or {
                "start_utc": key,
                "end_utc": (quarter_start + timedelta(minutes=15)).isoformat(),
                "quality": "missing",
                "tariff_block": tariff.block,
                "contractual_target_kw": runtime.target_for_tariff(tariff),
            }
        )
    calendar_hours = runtime.tariff_calendar.daily_view(local_date)
    block_summary: list[dict[str, Any]] = []
    for block in range(1, 6):
        block_rows = [row for row in rows if row["tariff_block"] == block]
        valid = [row for row in block_rows if row["quality"] not in {"incomplete", "unavailable"}]
        block_start = next(
            (item for item in starts if runtime.tariff_calendar.classify(item).block == block),
            None,
        )
        periods = [
            item["local_datetime"].strftime("%H:%M")
            for item in calendar_hours
            if item["block"] == block
        ]
        block_summary.append(
            {
                "block": block,
                "active": block_start is not None,
                "periods": periods,
                "target_kw": (
                    runtime.target_for_tariff(runtime.tariff_calendar.classify(block_start))
                    if block_start is not None
                    else None
                ),
                "valid_count": len(valid),
                "maximum_import_demand_kw": max(
                    (float(row["import_demand_kw"]) for row in valid), default=None
                ),
                "average_import_demand_kw": (
                    sum(float(row["import_demand_kw"]) for row in valid) / len(valid)
                    if valid
                    else None
                ),
                "import_kwh": sum(float(row["import_kwh"]) for row in valid),
                "export_kwh": sum(float(row["export_kwh"]) for row in valid),
                "confirmed_exceedances": sum(row["confirmed_exceeded"] == 1 for row in valid),
            }
        )
    connection.send_result(
        msg["id"],
        {
            "date": local_date.isoformat(),
            "expected_quarters": len(starts),
            "quarters": quarters,
            "summary": {**_json(summary), "missing_count": len(starts) - len(rows)},
            "blocks": block_summary,
        },
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
    except ValueError:
        connection.send_error(msg["id"], "invalid_date", "Invalid local date")
        return
    if not 2026 <= selected.year <= 2030:
        connection.send_error(msg["id"], "out_of_range", "Calendar supports 2026 through 2030")
        return
    rows = []
    for item in runtime.tariff_calendar.daily_view(selected):
        tariff = runtime.tariff_calendar.classify(item["start_utc"])
        rows.append({**_json(item), "target_kw": runtime.target_for_tariff(tariff)})
    connection.send_result(msg["id"], {"date": selected.isoformat(), "hours": rows})


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
