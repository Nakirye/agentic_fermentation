from fermentation_agent import config
from fermentation_agent.models import FermentationPhase, YeastResult, YeastType


def rate(temp_c: float, q10_cold: float = config.Q10_COLD) -> float:
    """Fermentation speed relative to REFERENCE_TEMP_C (= 1.0).

    Above Q10_BREAK_C the speed doubles every 10 °C; below it drops off faster,
    because yeast activity collapses in the fridge.
    """
    warm = config.Q10_WARM ** ((max(temp_c, config.Q10_BREAK_C) - config.REFERENCE_TEMP_C) / 10)
    if temp_c >= config.Q10_BREAK_C:
        return warm
    return warm * q10_cold ** ((temp_c - config.Q10_BREAK_C) / 10)


def equivalent_hours(phases: list[FermentationPhase], q10_cold: float = config.Q10_COLD) -> float:
    """Total fermentation time normalised to REFERENCE_TEMP_C: Σ hours · rate(T)."""
    return sum(phase.hours * rate(phase.temp_c, q10_cold) for phase in phases)


def fresh_yeast_pct(
    eq_hours: float,
    k: float = config.YEAST_K,
    exponent: float = config.YEAST_EXPONENT,
) -> float:
    """Unclamped fresh yeast in % of flour for the given equivalent hours."""
    return k * eq_hours**-exponent


def calculate_yeast_percentage(phases: list[FermentationPhase], yeast_type: YeastType) -> YeastResult:
    """Yeast amount so the dough is ripe at the end of the last phase."""
    if not phases:
        raise ValueError("At least one fermentation phase is required")
    eq_hours = equivalent_hours(phases)
    pct = fresh_yeast_pct(eq_hours)

    low, high = config.YEAST_PCT_RANGE_FRESH
    warnings = []
    clamped = not low <= pct <= high
    if pct < low:
        warnings.append(
            f"Fermentation is very long ({eq_hours:.1f} equivalent hours); yeast set to the minimum "
            f"of {low} % fresh. The dough may over-ferment – consider a shorter or colder plan."
        )
    elif pct > high:
        warnings.append(
            f"Fermentation is very short ({eq_hours:.1f} equivalent hours); yeast capped at "
            f"{high} % fresh. The dough may be under-fermented – consider more time or warmth."
        )
    pct = min(max(pct, low), high)

    return YeastResult(
        yeast_pct=round(pct * config.YEAST_CONVERSION_FROM_FRESH[yeast_type], 3),
        yeast_type=yeast_type,
        equivalent_hours=round(eq_hours, 2),
        clamped=clamped,
        warnings=warnings,
    )
