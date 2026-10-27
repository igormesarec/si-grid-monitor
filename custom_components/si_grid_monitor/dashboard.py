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

from .analysis import (
    PeriodType,
    block_report,
    exceedance_report,
    period_report,
    resolve_period,
)
from .const import (
    CONF_PREFERRED_LANGUAGE,
    DEFAULT_PREFERRED_LANGUAGE,
    DOMAIN,
    FRONTEND_URL,
    PANEL_ICON,
    PANEL_TITLE,
    PANEL_URL_PATH,
    VERSION,
)
from .contract_health import evaluate_contract_health
from .contracted_power import ContractedPowerSchedule
from .dashboard_models import build_day_view
from .engine import LJUBLJANA, quarter_starts_for_local_day
from .history import HistoryQuery, history_report

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
    entries = []
    for entry_id, runtime in runtimes.items():
        configured = {
            **getattr(runtime.entry, "data", {}),
            **getattr(runtime.entry, "options", {}),
        }
        entries.append(
            {
                "entry_id": entry_id,
                "title": runtime.entry.title,
                "preferred_language": str(
                    configured.get(CONF_PREFERRED_LANGUAGE, DEFAULT_PREFERRED_LANGUAGE)
                ),
            }
        )
    return entries


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
            ws_period,
            ws_blocks,
            ws_exceedances,
            ws_history,
            ws_recorder_audit,
            ws_recorder_reconstruct,
            ws_calendar,
            ws_contracts,
            ws_tariff_status,
            ws_transitions,
            ws_archive_status,
            ws_publishing,
        ):
            websocket_api.async_register_command(hass, handler)
        domain_data[DATA_COMMANDS_READY] = True
    if not domain_data.get(DATA_FRONTEND_READY):
        frontend_dir = Path(__file__).parent / "frontend"
        await hass.http.async_register_static_paths(
            [StaticPathConfig(FRONTEND_URL, str(frontend_dir), True)]
        )
        domain_data[DATA_FRONTEND_READY] = True


async def async_register_panel(hass: HomeAssistant) -> bool:
    """Create the branded sidebar entry when the first config entry loads."""

    if frontend.async_panel_exists(hass, PANEL_URL_PATH):
        return False
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="si-grid-monitor-panel",
        frontend_url_path=PANEL_URL_PATH,
        module_url=f"{FRONTEND_URL}/dashboard.js?v={VERSION}",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        require_admin=False,
        config={"version": VERSION},
        handle_safe_area=True,
    )
    return True


def async_unregister_panel(hass: HomeAssistant) -> None:
    """Remove only the panel owned by this integration."""

    frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/entries"})
@callback
def ws_entries(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    connection.send_result(msg["id"], {"entries": _entry_list(hass), "version": VERSION})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/publishing",
        vol.Optional("entry_id"): str,
        vol.Optional("window_seconds", default=3600): vol.In((3600, 86400, 604800)),
    }
)
@callback
def ws_publishing(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    """Return bounded in-memory publication diagnostics without scanning Recorder."""

    runtimes = hass.data.get(DOMAIN, {}).get(DATA_RUNTIMES, {})
    selected = msg.get("entry_id")
    if selected is not None:
        runtime = runtimes.get(selected)
        selected_runtimes = [(selected, runtime)] if runtime is not None else []
    else:
        selected_runtimes = list(runtimes.items())
    now_utc = datetime.now(UTC)
    meters: list[dict[str, Any]] = []
    for entry_id, runtime in selected_runtimes:
        publishing = getattr(runtime, "publishing", None)
        if publishing is None:
            continue
        metrics = publishing.diagnostics(now_utc, int(msg["window_seconds"]))
        meters.append(
            {
                "entry_id": entry_id,
                "title": runtime.entry.title,
                **metrics,
            }
        )
    totals = {
        "publishing_evaluations_per_minute": sum(
            item["publishing_evaluations_per_minute"] for item in meters
        ),
        "internal_timer_ticks_per_minute": sum(
            item["internal_timer_ticks_per_minute"] for item in meters
        ),
        "publications_per_minute": sum(item["publications_per_minute"] for item in meters),
        "publications_in_window": sum(item["publications_in_window"] for item in meters),
        "suppressed_unchanged": sum(item["suppressed_unchanged"] for item in meters),
        "suppressed_policy": sum(item["suppressed_policy"] for item in meters),
        "suppressed_attribute_only": sum(item["suppressed_attribute_only"] for item in meters),
        "critical_publications": sum(item["critical_publications"] for item in meters),
        "processing_failures": sum(item.get("processing_failures", 0) for item in meters),
        "faulted_entities": [
            {"meter": item["title"], "entity_key": entity_key}
            for item in meters
            for entity_key in item.get("faulted_entities", [])
        ],
        "effective_current_measurement_interval_seconds": (
            meters[0].get("effective_current_measurement_interval_seconds")
            if meters
            and len({item.get("effective_current_measurement_interval_seconds") for item in meters})
            == 1
            else None
        ),
        "effective_quarter_accumulation_interval_seconds": (
            meters[0].get("effective_quarter_accumulation_interval_seconds")
            if meters
            and len(
                {item.get("effective_quarter_accumulation_interval_seconds") for item in meters}
            )
            == 1
            else None
        ),
        "last_successful_publication_utc": max(
            (
                item["last_successful_publication_utc"]
                for item in meters
                if item.get("last_successful_publication_utc") is not None
            ),
            default=None,
        ),
        "estimated_total_bytes_per_year": (
            sum(item["estimated_total_bytes_per_year"] for item in meters)
            if meters and all(item["estimated_total_bytes_per_year"] is not None for item in meters)
            else None
        ),
        "estimate_status": (
            "truncated"
            if any(item["estimate_status"] == "truncated" for item in meters)
            else "ready"
            if meters and all(item["estimate_status"] == "ready" for item in meters)
            else "warming_up"
        ),
        "event_history_truncated": any(item["event_history_truncated"] for item in meters),
        "influxdb_physical_storage_verified": False,
    }
    totals["budget_bytes_per_year"] = 1_000_000_000
    totals["budget_utilization_pct"] = (
        totals["estimated_total_bytes_per_year"] / totals["budget_bytes_per_year"] * 100
        if totals["estimated_total_bytes_per_year"] is not None
        else None
    )
    connection.send_result(
        msg["id"],
        {
            "window_seconds": int(msg["window_seconds"]),
            "meter_count": len(meters),
            "meters": meters,
            "totals": totals,
            "estimate_notice": (
                "Recorder-like estimate after at least one hour; InfluxDB physical storage is "
                "unverified until measured on an isolated InfluxDB 1.x instance"
            ),
        },
    )


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
        now = (
            datetime.fromisoformat(str(live.get("now_utc"))).astimezone(UTC)
            if live.get("now_utc")
            else datetime.now(UTC)
        )
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


_PERIOD_SCHEMA = {
    vol.Required("period_type"): str,
    vol.Required("anchor"): str,
    vol.Optional("custom_start"): str,
    vol.Optional("custom_end"): str,
    vol.Optional("tariff_block"): int,
}


def _period_request(msg: dict[str, Any]) -> tuple[Any, int | None]:
    """Validate and resolve one dashboard period request."""

    kind = PeriodType(msg["period_type"])
    anchor_value = msg["anchor"]
    if "T" in anchor_value:
        anchor: date | datetime = datetime.fromisoformat(anchor_value)
        if anchor.tzinfo is None:
            raise ValueError("hour anchor requires an explicit UTC offset")
    else:
        anchor = date.fromisoformat(anchor_value)
    custom_start = date.fromisoformat(msg["custom_start"]) if msg.get("custom_start") else None
    custom_end = date.fromisoformat(msg["custom_end"]) if msg.get("custom_end") else None
    tariff_block = msg.get("tariff_block")
    if tariff_block is not None and tariff_block not in range(1, 6):
        raise ValueError("tariff block must be B1 through B5")
    return (
        resolve_period(
            kind,
            anchor,
            custom_start=custom_start,
            custom_end=custom_end,
        ),
        tariff_block,
    )


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/period", **_ENTRY_SCHEMA, **_PERIOD_SCHEMA}
)
@websocket_api.async_response
async def ws_period(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    """Return the shared historical period report."""

    runtime = _runtime(hass, msg)
    if runtime is None:
        connection.send_error(msg["id"], "entry_not_found", "SI Grid Monitor entry not found")
        return
    try:
        bounds, tariff_block = _period_request(msg)
    except (KeyError, TypeError, ValueError):
        connection.send_error(msg["id"], "invalid_period", "Invalid historical period request")
        return
    live = runtime.dashboard_current()
    try:
        now_utc = (
            datetime.fromisoformat(str(live.get("now_utc"))).astimezone(UTC)
            if live.get("now_utc")
            else datetime.now(UTC)
        )
        report = await hass.async_add_executor_job(
            lambda: period_report(
                runtime.archive,
                runtime.namespace,
                bounds,
                now_utc=now_utc,
                tariff_block=tariff_block,
                classifier=runtime.tariff_calendar.classify,
            )
        )
    except sqlite3.Error:
        _history_error(
            connection,
            msg,
            operation="period",
            requested=bounds.label,
            code="archive_unavailable",
            message="Historical archive is temporarily unavailable",
        )
        return
    except Exception:
        _history_error(
            connection,
            msg,
            operation="period",
            requested=bounds.label,
            code="period_query_failed",
            message="Could not load the selected historical period",
        )
        return
    connection.send_result(msg["id"], _json(report))


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/blocks", **_ENTRY_SCHEMA, **_PERIOD_SCHEMA}
)
@websocket_api.async_response
async def ws_blocks(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    """Return five-block historical analysis for one period."""

    runtime = _runtime(hass, msg)
    if runtime is None:
        connection.send_error(msg["id"], "entry_not_found", "SI Grid Monitor entry not found")
        return
    try:
        bounds, selected_block = _period_request(msg)
    except (KeyError, TypeError, ValueError):
        connection.send_error(msg["id"], "invalid_period", "Invalid block-analysis request")
        return
    live = runtime.dashboard_current()
    try:
        now_utc = (
            datetime.fromisoformat(str(live.get("now_utc"))).astimezone(UTC)
            if live.get("now_utc")
            else datetime.now(UTC)
        )
        report = await hass.async_add_executor_job(
            lambda: block_report(
                runtime.archive,
                runtime.namespace,
                bounds,
                now_utc=now_utc,
                classifier=runtime.tariff_calendar.classify,
                selected_block=selected_block,
            )
        )
    except sqlite3.Error:
        _history_error(
            connection,
            msg,
            operation="blocks",
            requested=bounds.label,
            code="archive_unavailable",
            message="Historical archive is temporarily unavailable",
        )
        return
    except Exception:
        _history_error(
            connection,
            msg,
            operation="blocks",
            requested=bounds.label,
            code="blocks_query_failed",
            message="Could not load tariff-block analysis",
        )
        return
    connection.send_result(msg["id"], _json(report))


_EXCEEDANCE_SCHEMA = {
    **_PERIOD_SCHEMA,
    vol.Optional("sort_by"): str,
    vol.Optional("direction"): str,
    vol.Optional("page"): int,
    vol.Optional("page_size"): int,
}


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/exceedances", **_ENTRY_SCHEMA, **_EXCEEDANCE_SCHEMA}
)
@websocket_api.async_response
async def ws_exceedances(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    """Return a safely filtered and paginated confirmed-exceedance report."""

    runtime = _runtime(hass, msg)
    if runtime is None:
        connection.send_error(msg["id"], "entry_not_found", "SI Grid Monitor entry not found")
        return
    try:
        bounds, tariff_block = _period_request(msg)
        live = runtime.dashboard_current()
        now_utc = (
            datetime.fromisoformat(str(live.get("now_utc"))).astimezone(UTC)
            if live.get("now_utc")
            else datetime.now(UTC)
        )
        report = await hass.async_add_executor_job(
            lambda: exceedance_report(
                runtime.archive,
                runtime.namespace,
                bounds,
                now_utc=now_utc,
                tariff_block=tariff_block,
                sort_by=msg.get("sort_by", "date"),
                direction=msg.get("direction", "desc"),
                page=msg.get("page", 1),
                page_size=msg.get("page_size", 50),
                classifier=runtime.tariff_calendar.classify,
            )
        )
    except (KeyError, TypeError, ValueError):
        connection.send_error(msg["id"], "invalid_query", "Invalid exceedance query")
        return
    except sqlite3.Error:
        _history_error(
            connection,
            msg,
            operation="exceedances",
            requested=str(msg.get("anchor")),
            code="archive_unavailable",
            message="Historical archive is temporarily unavailable",
        )
        return
    except Exception:
        _history_error(
            connection,
            msg,
            operation="exceedances",
            requested=str(msg.get("anchor")),
            code="exceedances_query_failed",
            message="Could not load exceedance analysis",
        )
        return
    connection.send_result(msg["id"], _json(report))


_HISTORY_SCHEMA = {
    vol.Required("start_date"): str,
    vol.Required("end_date"): str,
    vol.Optional("tariff_block"): int,
    vol.Optional("qualities"): [str],
    vol.Optional("exceedance_status"): str,
    vol.Optional("source_epoch"): int,
    vol.Optional("page"): int,
    vol.Optional("page_size"): int,
    vol.Optional("sort_by"): str,
    vol.Optional("direction"): str,
}


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/history", **_ENTRY_SCHEMA, **_HISTORY_SCHEMA}
)
@websocket_api.async_response
async def ws_history(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    """Return a bounded, server-side filtered HISTORY archive page."""

    runtime = _runtime(hass, msg)
    if runtime is None:
        connection.send_error(msg["id"], "entry_not_found", "SI Grid Monitor entry not found")
        return
    try:
        start_date = date.fromisoformat(msg["start_date"])
        end_date = date.fromisoformat(msg["end_date"])
        if end_date < start_date:
            raise ValueError("history end date precedes start date")
        start = quarter_starts_for_local_day(start_date)[0]
        following = quarter_starts_for_local_day(end_date + timedelta(days=1))
        end = following[0]
        query = HistoryQuery(
            start_utc=start,
            end_utc=end,
            tariff_block=msg.get("tariff_block"),
            qualities=tuple(msg.get("qualities", [])),
            exceedance_status=msg.get("exceedance_status", "all"),
            source_epoch=msg.get("source_epoch"),
            page=msg.get("page", 1),
            page_size=msg.get("page_size", 50),
            sort_by=msg.get("sort_by", "start_utc"),
            direction=msg.get("direction", "desc"),
        )
        live = runtime.dashboard_current()
        now_utc = (
            datetime.fromisoformat(str(live.get("now_utc"))).astimezone(UTC)
            if live.get("now_utc")
            else datetime.now(UTC)
        )
        report = await hass.async_add_executor_job(
            lambda: history_report(
                runtime.archive,
                runtime.namespace,
                query,
                now_utc=now_utc,
            )
        )
        storage = await hass.async_add_executor_job(runtime.archive.archive_storage_status)
    except (KeyError, TypeError, ValueError):
        connection.send_error(msg["id"], "invalid_query", "Invalid HISTORY archive query")
        return
    except sqlite3.Error:
        _history_error(
            connection,
            msg,
            operation="history",
            requested=f"{msg.get('start_date')}..{msg.get('end_date')}",
            code="archive_unavailable",
            message="Historical archive is temporarily unavailable",
        )
        return
    except Exception:
        _history_error(
            connection,
            msg,
            operation="history",
            requested=f"{msg.get('start_date')}..{msg.get('end_date')}",
            code="history_query_failed",
            message="Could not load the HISTORY archive",
        )
        return
    connection.send_result(msg["id"], _json({**report, "storage": storage}))


_RECORDER_AUDIT_SCHEMA = {
    vol.Required("start_date"): str,
    vol.Required("end_date"): str,
}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/recorder_audit",
        **_ENTRY_SCHEMA,
        **_RECORDER_AUDIT_SCHEMA,
    }
)
@websocket_api.async_response
async def ws_recorder_audit(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    """Run an admin-only, read-only detailed Recorder audit."""

    if not connection.user.is_admin:
        connection.send_error(msg["id"], "unauthorized", "Administrator access is required")
        return
    runtime = _runtime(hass, msg)
    if runtime is None:
        connection.send_error(msg["id"], "entry_not_found", "SI Grid Monitor entry not found")
        return
    try:
        start_date = date.fromisoformat(msg["start_date"])
        end_date = date.fromisoformat(msg["end_date"])
        if end_date < start_date or (end_date - start_date).days > 366:
            raise ValueError("audit range must be between one day and 367 days")
        start = quarter_starts_for_local_day(start_date)[0]
        end = quarter_starts_for_local_day(end_date + timedelta(days=1))[0]
        result = await runtime.async_audit_recorder_history(start, end)
    except (KeyError, TypeError, ValueError) as err:
        connection.send_error(msg["id"], "invalid_audit", str(err))
        return
    except Exception:
        _history_error(
            connection,
            msg,
            operation="recorder_audit",
            requested=f"{msg.get('start_date')}..{msg.get('end_date')}",
            code="recorder_audit_failed",
            message="Recorder audit could not be completed",
        )
        return
    result["candidates"] = result.get("candidates", [])[:1000]
    result["candidates_truncated"] = result["summary"]["candidate_count"] > 1000
    connection.send_result(msg["id"], _json(result))


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/recorder_reconstruct",
        vol.Required("audit_token"): str,
        vol.Required("confirm"): bool,
        **_ENTRY_SCHEMA,
    }
)
@websocket_api.async_response
async def ws_recorder_reconstruct(
    hass: HomeAssistant, connection: Any, msg: dict[str, Any]
) -> None:
    """Apply an explicitly confirmed audit plan after a SQLite backup."""

    if not connection.user.is_admin:
        connection.send_error(msg["id"], "unauthorized", "Administrator access is required")
        return
    if msg.get("confirm") is not True:
        connection.send_error(msg["id"], "confirmation_required", "Explicit confirmation required")
        return
    runtime = _runtime(hass, msg)
    if runtime is None:
        connection.send_error(msg["id"], "entry_not_found", "SI Grid Monitor entry not found")
        return
    try:
        result = await runtime.async_apply_recorder_reconstruction(msg["audit_token"])
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_audit_token", str(err))
        return
    except Exception:
        _history_error(
            connection,
            msg,
            operation="recorder_reconstruct",
            requested=str(msg.get("audit_token"))[:12],
            code="reconstruction_failed",
            message="Controlled reconstruction failed; archive recovery metadata was retained",
        )
        return
    connection.send_result(msg["id"], _json(result))


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
    starts = quarter_starts_for_local_day(selected)
    day_start = starts[0]
    day_end = quarter_starts_for_local_day(selected + timedelta(days=1))[0]
    archived = await hass.async_add_executor_job(
        runtime.archive.list_quarters, runtime.namespace, day_start, day_end
    )
    epochs = await hass.async_add_executor_job(
        runtime.archive.list_configuration_epochs, runtime.namespace
    )
    archived_by_start = {str(row["start_utc"]): row for row in archived}
    local_today = datetime.now(UTC).astimezone(LJUBLJANA).date()
    historical_day = selected < local_today
    rows = []
    for item in runtime.tariff_calendar.daily_view(selected):
        tariff = runtime.tariff_calendar.classify(item["start_utc"])
        current_target = runtime.target_for_tariff(tariff)
        start_iso = item["start_utc"].astimezone(UTC).isoformat()
        archive_row = archived_by_start.get(start_iso)
        recorded_target = None
        recorded_source = "unknown"
        recorded_reason = "No archived quarter proves the contractual target for this hour."
        inferred_target = None
        inferred_epoch = None
        eligible = [epoch for epoch in epochs if epoch.effective_utc <= item["start_utc"]]
        if eligible:
            epoch = eligible[-1]
            if epoch.contracted_power_periods is not None:
                historical = ContractedPowerSchedule(epoch.contracted_power_periods)
                inferred_target = historical.target_for(tariff)
                inferred_epoch = epoch.epoch
        if archive_row is not None:
            if archive_row["contractual_target_kw"] is not None:
                recorded_target = float(archive_row["contractual_target_kw"])
                recorded_source = "archived_quarter"
                recorded_reason = None
            else:
                recorded_source = "archived_quarter_unknown"
                recorded_reason = (
                    "The archived quarter explicitly has no contractual target. "
                    "Historical configuration, when shown, is inference only."
                )
        elif inferred_target is not None:
            recorded_reason = (
                "No archived quarter exists. A historical configuration inference is shown "
                "separately and is not archived measurement evidence."
            )
        display_target = recorded_target if historical_day else current_target
        rows.append(
            {
                **_json(item),
                "target_kw": display_target,
                "display_target_kw": display_target,
                "display_target_source": (
                    recorded_source if historical_day else "current_configuration"
                ),
                "is_historical": historical_day,
                "current_configuration_target_kw": current_target,
                "as_recorded_target_kw": recorded_target,
                "as_recorded_source": recorded_source,
                "as_recorded_reason": recorded_reason,
                "historical_configuration_target_kw": inferred_target,
                "historical_configuration_epoch": inferred_epoch,
                "archived_quarter_present": archive_row is not None,
            }
        )
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


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/contracts",
        vol.Optional("audit_page", default=1): int,
        vol.Optional("audit_page_size", default=50): int,
        **_ENTRY_SCHEMA,
    }
)
@websocket_api.async_response
async def ws_contracts(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    """Return read-only, meter-scoped contract configuration and evidence."""

    runtime = _runtime(hass, msg)
    if runtime is None:
        connection.send_error(msg["id"], "entry_not_found", "SI Grid Monitor entry not found")
        return
    now_utc = datetime.now(UTC)
    local_today = now_utc.astimezone(LJUBLJANA).date()
    audit_page = int(msg.get("audit_page", 1))
    audit_page_size = int(msg.get("audit_page_size", 50))
    if audit_page < 1 or not 1 <= audit_page_size <= 100:
        connection.send_error(msg["id"], "invalid_query", "Invalid contract audit pagination")
        return
    audit_offset = (audit_page - 1) * audit_page_size
    try:
        audits = await hass.async_add_executor_job(
            runtime.archive.list_contract_audit,
            runtime.namespace,
            audit_page_size,
            audit_offset,
        )
        audit_total = await hass.async_add_executor_job(
            runtime.archive.count_contract_audit, runtime.namespace
        )
        epochs = await hass.async_add_executor_job(
            runtime.archive.list_configuration_epochs, runtime.namespace
        )
        evidence = await hass.async_add_executor_job(
            runtime.archive.list_contract_target_evidence, runtime.namespace
        )
    except sqlite3.Error:
        _history_error(
            connection,
            msg,
            operation="contracts",
            requested=runtime.namespace,
            code="archive_unavailable",
            message="Contract history is temporarily unavailable",
        )
        return
    schedule = runtime.contracted_power_schedule
    health = evaluate_contract_health(schedule, local_today)
    active = schedule.period_for(local_today)
    future = [period for period in schedule.periods if period.effective_from > local_today]
    previous = [period for period in schedule.periods if period.effective_to < local_today]
    if active is not None:
        contract_status = "ACTIVE"
    elif future and previous:
        contract_status = "FUTURE_GAP"
    elif future:
        contract_status = "UPCOMING"
    elif schedule.periods:
        contract_status = "EXPIRED"
    elif evidence:
        contract_status = "HISTORICAL_EVIDENCE_ONLY"
    else:
        contract_status = "NO_ASSIGNMENT"
    if schedule.periods:
        timeline_start = min(schedule.periods[0].effective_from, local_today)
        timeline_end = max(schedule.periods[-1].effective_to, local_today + timedelta(days=365))
    else:
        timeline_start = local_today
        timeline_end = local_today + timedelta(days=365)
    timeline = [
        {
            "kind": "assignment",
            "effective_from": period.effective_from,
            "effective_to": period.effective_to,
            "assignment_index": index,
        }
        for index, period in enumerate(schedule.periods)
    ]
    timeline.extend(
        {
            "kind": "gap",
            "effective_from": start,
            "effective_to": end,
            "assignment_index": None,
        }
        for start, end in schedule.gaps(timeline_start, timeline_end)
    )
    timeline.sort(key=lambda item: item["effective_from"])
    health_payload: Any = health
    if runtime._contracted_power_configuration_error is not None:
        contract_status = "CONFIGURATION_ERROR"
        health_payload = {
            "level": "error",
            "reason": "configuration_error",
            "active": None,
            "successor": None,
            "days_remaining": None,
            "gap_start": None,
            "gap_end": None,
        }
    current_tariff = runtime.tariff_calendar.classify(now_utc)
    connection.send_result(
        msg["id"],
        _json(
            {
                "entry_id": runtime.entry.entry_id,
                "meter_name": runtime.entry.title,
                "today": local_today,
                "is_admin": bool(connection.user.is_admin),
                "contract_status": contract_status,
                "health": health_payload,
                "current_tariff_block": current_tariff.block,
                "applicable_target_kw": runtime.target_for_tariff(current_tariff),
                "current_schedule": schedule.periods,
                "timeline": timeline,
                "historical_configuration": epochs[-200:],
                "historical_configuration_total": len(epochs),
                "historical_configuration_truncated": len(epochs) > 200,
                "archived_target_evidence": evidence,
                "audit_events": audits,
                "audit_pagination": {
                    "page": audit_page,
                    "page_size": audit_page_size,
                    "total": audit_total,
                    "pages": max(1, (audit_total + audit_page_size - 1) // audit_page_size),
                },
                "management": {
                    "supported": bool(connection.user.is_admin),
                    "direct_options_supported": False,
                    "route": "/config/integrations/integration/si_grid_monitor",
                    "instruction": (
                        "Open Devices & services, select SI Grid Monitor, then Configure "
                        f'the meter named "{runtime.entry.title}".'
                    ),
                },
            }
        ),
    )


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/tariff_status", **_ENTRY_SCHEMA})
@websocket_api.async_response
async def ws_tariff_status(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    """Expose installed, offline tariff metadata without applying remote rules."""

    runtime = _runtime(hass, msg)
    if runtime is None:
        connection.send_error(msg["id"], "entry_not_found", "SI Grid Monitor entry not found")
        return
    now = runtime.dashboard_current().get("now_utc")
    today = (
        datetime.fromisoformat(str(now)).astimezone(LJUBLJANA).date()
        if now
        else datetime.now(UTC).astimezone(LJUBLJANA).date()
    )
    connection.send_result(
        msg["id"],
        _json(
            {
                **runtime.tariff_calendar.rule_status_report(today),
                "integration_version": VERSION,
            }
        ),
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
