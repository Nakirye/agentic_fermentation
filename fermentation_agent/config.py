"""Central constants. Every guardrail limit lives here so it is documented in one place.

Yeast model values marked FITTED come from scripts/calibrate_yeast.py.
"""

from datetime import time

from fermentation_agent.models import FlourType, Mixing, YeastType

TIMEZONE = "Europe/Vienna"

# --- Input guardrails -------------------------------------------------------
PIZZA_COUNT_RANGE = (1, 30)
BALL_WEIGHT_G_RANGE = (180, 350)
SALT_PCT_RANGE = (2.0, 3.5)
ROOM_TEMP_C_RANGE = (10.0, 35.0)
FRIDGE_TEMP_C_RANGE = (1.0, 8.0)

# Upper hydration limit per flour; above this the result is no longer a workable dough.
MAX_HYDRATION_PCT: dict[FlourType, float] = {
    FlourType.TIPO_00: 75.0,
    FlourType.TYPE_550: 72.0,
    FlourType.MANITOBA: 85.0,
    FlourType.WHOLE_WHEAT: 90.0,
}
MIN_HYDRATION_PCT = 55.0

# --- Dough handling ---------------------------------------------------------
DOUGH_WASTE_PCT = 2.5  # dough left on bowl and hands
FRICTION_FACTOR_C: dict[Mixing, float] = {Mixing.HAND: 2.0, Mixing.STAND_MIXER: 8.0}
TARGET_DOUGH_TEMP_C = 23.0

# --- Yeast model ------------------------------------------------------------
# rate(T) relative to REFERENCE_TEMP_C, with a steeper Q10 below Q10_BREAK_C.
# pct_fresh = YEAST_K * equivalent_hours ** -YEAST_EXPONENT
REFERENCE_TEMP_C = 24.0
Q10_WARM = 2.0
Q10_BREAK_C = 15.0
Q10_COLD = 6.75  # FITTED
YEAST_K = 41.0  # FITTED
YEAST_EXPONENT = 2.55  # FITTED
YEAST_PCT_RANGE_FRESH = (0.02, 3.0)
YEAST_CONVERSION_FROM_FRESH: dict[YeastType, float] = {
    YeastType.FRESH: 1.0,
    YeastType.ACTIVE_DRY: 0.4,
    YeastType.INSTANT_DRY: 0.33,
}

# --- Schedule guardrails ----------------------------------------------------
SLEEP_WINDOW = (time(23, 0), time(7, 0))  # no active steps in [start, end)
MIN_LEAD_TIME_MIN = 15  # first step must start at least this long after "now"

# --- Agent loop guardrails --------------------------------------------------
MAX_AGENT_TURNS = 12
MAX_SCHEDULE_RETRIES = 3
