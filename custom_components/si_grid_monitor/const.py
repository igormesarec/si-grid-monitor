"""Constants for SI Grid Monitor."""

from __future__ import annotations

DOMAIN = "si_grid_monitor"

CONF_SOURCE_MODE = "source_mode"
CONF_POWER_ENTITY = "power_entity"
CONF_POSITIVE_MEANS_IMPORT = "positive_means_import"
CONF_TARGET_KW = "target_kw"
CONF_TARGET_MODE = "target_mode"
CONF_TARGET_B1_KW = "target_b1_kw"
CONF_TARGET_B2_KW = "target_b2_kw"
CONF_TARGET_B3_KW = "target_b3_kw"
CONF_TARGET_B4_KW = "target_b4_kw"
CONF_TARGET_B5_KW = "target_b5_kw"
CONF_CONTRACTED_POWER_PERIODS = "contracted_power_periods"
CONF_ASSIGNMENT_START_DATE = "assignment_start_date"
CONF_ASSIGNMENT_END_DATE = "assignment_end_date"
CONF_ALLOW_PROVISIONAL_TARIFF = "allow_provisional_tariff"
CONF_SAFETY_MARGIN_KW = "safety_margin_kw"
CONF_SMOOTHING_SECONDS = "smoothing_seconds"
CONF_RETENTION = "retention"
CONF_SIMULATION_ENABLED = "simulation_enabled"
CONF_SIMULATION_TARGET_KW = "simulation_target_kw"
CONF_SUSTAINED_HORIZON_MINUTES = "sustained_horizon_minutes"

SOURCE_SIGNED_POWER = "signed_power"
SOURCE_SEPARATE_POWER = "separate_power"
SOURCE_IMPORT_ONLY = "import_only"
SOURCE_CUMULATIVE_ENERGY = "cumulative_energy"
SOURCE_ALIGNED_QUARTER = "aligned_quarter"

DEFAULT_TARGET_KW = 4.8
DEFAULT_SAFETY_MARGIN_KW = 0.0
DEFAULT_SMOOTHING_SECONDS = 120
DEFAULT_STALE_AFTER_SECONDS = 60
DEFAULT_RETENTION = "forever"
DEFAULT_SUSTAINED_HORIZON_MINUTES = 60
DEFAULT_TARGET_MODE = "shared"
TARGET_MODE_SHARED = "shared"
TARGET_MODE_PER_BLOCK = "per_block"
TARGET_KEYS = (
    CONF_TARGET_B1_KW,
    CONF_TARGET_B2_KW,
    CONF_TARGET_B3_KW,
    CONF_TARGET_B4_KW,
    CONF_TARGET_B5_KW,
)

SMOOTHING_PRESETS = (30, 60, 90, 120, 180)
SUSTAINED_HORIZON_PRESETS = (15, 30, 60, 120)
MIN_SMOOTHING_SECONDS = 30
MAX_SMOOTHING_SECONDS = 180

ATTR_BUDGET_HEADROOM_WARNING = (
    "15-minute budget headroom is not breaker, phase, wiring, or inverter capacity"
)
