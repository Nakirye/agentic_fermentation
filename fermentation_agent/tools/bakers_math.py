from fermentation_agent import config
from fermentation_agent.models import Ingredients


def calculate_bakers_math(
    pizza_count: int,
    ball_weight_g: float,
    hydration_pct: float,
    salt_pct: float,
    yeast_pct: float,
) -> Ingredients:
    """Exact gram amounts from baker's percentages (flour = 100 %), including the waste factor.

    flour = total_dough / (1 + hydration + salt + yeast), all as fractions.
    """
    if pizza_count <= 0 or ball_weight_g <= 0:
        raise ValueError("pizza_count and ball_weight_g must be positive")
    if min(hydration_pct, salt_pct, yeast_pct) < 0:
        raise ValueError("Percentages must not be negative")

    total = pizza_count * ball_weight_g * (1 + config.DOUGH_WASTE_PCT / 100)
    flour = total / (1 + (hydration_pct + salt_pct + yeast_pct) / 100)
    return Ingredients(
        flour_g=round(flour),
        water_g=round(flour * hydration_pct / 100),
        salt_g=round(flour * salt_pct / 100),
        yeast_g=round(flour * yeast_pct / 100, 1),
        total_dough_g=round(total),
    )
