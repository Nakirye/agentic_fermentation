from fermentation_agent import config
from fermentation_agent.models import Mixing, WaterTempResult

MIN_WATER_TEMP_C = 2.0
MAX_WATER_TEMP_C = 35.0


def calculate_water_temperature(
    target_dough_temp_c: float,
    room_temp_c: float,
    mixing: Mixing,
    flour_temp_c: float | None = None,
) -> WaterTempResult:
    """Water temp = 3 · target − room − flour − friction. Flour defaults to room temp.

    Warns (does not fail) below 2 °C (ice water) or above 35 °C (yeast stress).
    """
    flour = room_temp_c if flour_temp_c is None else flour_temp_c
    water = 3 * target_dough_temp_c - room_temp_c - flour - config.FRICTION_FACTOR_C[mixing]

    warnings = []
    if water < MIN_WATER_TEMP_C:
        warnings.append(
            f"Required water temperature {water:.1f} °C is below {MIN_WATER_TEMP_C} °C; "
            "use ice water and chill the flour, or accept a warmer dough."
        )
    elif water > MAX_WATER_TEMP_C:
        warnings.append(
            f"Required water temperature {water:.1f} °C is above {MAX_WATER_TEMP_C} °C and "
            "stresses the yeast; use at most that and let the dough rest somewhere warm."
        )
    return WaterTempResult(water_temp_c=round(water, 1), warnings=warnings)
