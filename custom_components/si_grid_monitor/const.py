"""Constants for SI Grid Monitor."""

from __future__ import annotations

DOMAIN = "si_grid_monitor"

CONF_SOURCE_MODE = "source_mode"
CONF_POWER_ENTITY = "power_entity"
CONF_POSITIVE_MEANS_IMPORT = "positive_means_import"
CONF_TARGET_KW = "target_kw"
CONF_SAFETY_MARGIN_KW = "safety_margin_kw"
CONF_SMOOTHING_SECONDS = "smoothing_seconds"

SOURCE_SIGNED_POWER = "signed_power"
SOURCE_SEPARATE_POWER = "separate_power"
SOURCE_IMPORT_ONLY = "import_only"
SOURCE_CUMULATIVE_ENERGY = "cumulative_energy"
SOURCE_ALIGNED_QUARTER = "aligned_quarter"

DEFAULT_TARGET_KW = 4.8
DEFAULT_SAFETY_MARGIN_KW = 0.0
DEFAULT_SMOOTHING_SECONDS = 30
DEFAULT_STALE_AFTER_SECONDS = 60

MIN_SMOOTHING_SECONDS = 5
MAX_SMOOTHING_SECONDS = 120

ATTR_BUDGET_HEADROOM_WARNING = (
    "15-minute budget headroom is not breaker, phase, wiring, or inverter capacity"
)
