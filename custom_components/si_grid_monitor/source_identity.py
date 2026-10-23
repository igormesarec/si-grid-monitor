"""Stable source identities shared by setup and reconfiguration flows."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .const import (
    CONF_EXPORT_POWER_ENTITY,
    CONF_IMPORT_POWER_ENTITY,
    CONF_POWER_ENTITY,
    CONF_SOURCE_MODE,
    SOURCE_IMPORT_ONLY,
    SOURCE_SEPARATE_POWER,
    SOURCE_SIGNED_POWER,
)


def source_unique_id(mode: str, configured: Mapping[str, Any]) -> str:
    """Return the canonical config-entry identity for one supported source."""

    if mode == SOURCE_SIGNED_POWER:
        entity = _required_entity(configured, CONF_POWER_ENTITY)
        return f"signed:{entity}"
    if mode == SOURCE_SEPARATE_POWER:
        imported = _required_entity(configured, CONF_IMPORT_POWER_ENTITY)
        exported = _required_entity(configured, CONF_EXPORT_POWER_ENTITY)
        return f"{SOURCE_SEPARATE_POWER}:{imported}|{exported}"
    if mode == SOURCE_IMPORT_ONLY:
        imported = _required_entity(configured, CONF_IMPORT_POWER_ENTITY)
        return f"{SOURCE_IMPORT_ONLY}:{imported}"
    raise ValueError(f"unsupported source mode: {mode}")


def configured_entry_source_unique_id(entry: Any) -> str | None:
    """Derive an entry identity even when an older entry has no unique_id."""

    configured = {**dict(entry.data), **dict(entry.options)}
    mode = str(configured.get(CONF_SOURCE_MODE, SOURCE_SIGNED_POWER))
    try:
        return source_unique_id(mode, configured)
    except (KeyError, TypeError, ValueError):
        return None


def find_duplicate_source_entry(
    entries: Iterable[Any], *, current_entry_id: str, target_unique_id: str
) -> Any | None:
    """Find another entry owning the target source identity."""

    for candidate in entries:
        if str(candidate.entry_id) == current_entry_id:
            continue
        stored_unique_id = getattr(candidate, "unique_id", None)
        derived_unique_id = configured_entry_source_unique_id(candidate)
        if target_unique_id in {stored_unique_id, derived_unique_id}:
            return candidate
    return None


def _required_entity(configured: Mapping[str, Any], key: str) -> str:
    value = str(configured.get(key) or "").strip()
    if not value:
        raise ValueError(f"missing source entity: {key}")
    return value
