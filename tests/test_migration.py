"""Configuration-entry migration tests."""

from custom_components.si_grid_monitor import migrated_v3_settings
from custom_components.si_grid_monitor.const import (
    CONF_ALLOW_PROVISIONAL_TARIFF,
    CONF_POWER_ENTITY,
    CONF_TARGET_KW,
    TARGET_KEYS,
)


def test_v02_target_is_copied_to_all_five_blocks_without_losing_settings() -> None:
    data = {CONF_POWER_ENTITY: "sensor.grid", CONF_TARGET_KW: 4.8, "custom": "keep"}
    options = {CONF_TARGET_KW: 5.2, "smoothing_seconds": 120}
    migrated_data, migrated_options = migrated_v3_settings(data, options)

    assert all(migrated_options[key] == 5.2 for key in TARGET_KEYS)
    assert migrated_options[CONF_ALLOW_PROVISIONAL_TARIFF] is False
    assert migrated_data["custom"] == "keep"
    assert migrated_options["smoothing_seconds"] == 120


def test_existing_v03_block_values_are_never_overwritten() -> None:
    data = {CONF_TARGET_KW: 4.8, **dict(zip(TARGET_KEYS, (1, 2, 3, 4, 5), strict=True))}
    migrated_data, _ = migrated_v3_settings(data, {})
    assert tuple(migrated_data[key] for key in TARGET_KEYS) == (1, 2, 3, 4, 5)
