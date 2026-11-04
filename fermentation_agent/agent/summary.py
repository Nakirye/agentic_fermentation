"""Deterministic texts built only from tool results: calendar notes and the fallback summary."""

from typing import TYPE_CHECKING

from fermentation_agent.models import YeastType

if TYPE_CHECKING:
    from fermentation_agent.agent.session import AgentSession

YEAST_NAMES = {
    YeastType.FRESH: "Fresh yeast",
    YeastType.ACTIVE_DRY: "Active dry yeast",
    YeastType.INSTANT_DRY: "Instant dry yeast",
}


def ingredient_lines(session: "AgentSession") -> list[str]:
    request, ingredients, yeast, water = session.request, session.ingredients, session.yeast, session.water
    return [
        f"Flour ({request.flour_type}): {ingredients.flour_g:g} g",
        f"Water: {ingredients.water_g:g} g at {water.water_temp_c:g} °C",
        f"Salt: {ingredients.salt_g:g} g",
        f"{YEAST_NAMES[yeast.yeast_type]}: {ingredients.yeast_g:g} g ({yeast.yeast_pct:g} %)",
    ]


def _duration(minutes: float) -> str:
    return f"{minutes / 60:g} h" if minutes >= 60 else f"{minutes:g} min"


def render_template_summary(session: "AgentSession") -> str:
    request, timeline = session.request, session.timeline
    lines = [
        f"Plan for {request.pizza_count} pizzas of {request.ball_weight_g:g} g "
        f"({request.hydration_pct:g} % hydration), baking {request.target_time:%a %H:%M}.",
        "",
        "Ingredients:",
        *(f"- {line}" for line in ingredient_lines(session)),
        "",
        "Schedule:",
    ]
    for step in timeline.steps:
        minutes = (step.end - step.start).total_seconds() / 60
        lines.append(f"- {step.start:%a %H:%M}  {step.name} ({_duration(minutes)})")
    warnings = session.yeast.warnings + session.water.warnings
    if warnings:
        lines += ["", "Notes:", *(f"- {warning}" for warning in warnings)]
    return "\n".join(lines)
