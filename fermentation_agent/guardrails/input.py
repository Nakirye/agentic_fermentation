from datetime import datetime, timedelta

from fermentation_agent import config
from fermentation_agent.errors import GuardrailError
from fermentation_agent.models import DoughRequest


def check_user_text(text: str) -> str:
    """Reject empty or oversized input and strip control characters before the LLM sees it."""
    cleaned = "".join(ch for ch in text if ch.isprintable() or ch in "\n\t").strip()
    if not cleaned:
        raise GuardrailError("empty_input", "The request is empty.",
                             hint="Describe when and how many pizzas you want to bake.")
    if len(cleaned) > config.MAX_USER_TEXT_CHARS:
        raise GuardrailError(
            "input_too_long", f"The request is longer than {config.MAX_USER_TEXT_CHARS} characters.",
            hint="Shorten the request to the essentials: bake time, pizza count, temperatures.",
        )
    return cleaned


Problem = tuple[str, str, str]  # (rule, message, hint)


def _check_range(problems: list[Problem], label: str, value: float,
                 limits: tuple[float, float], unit: str) -> None:
    low, high = limits
    if not low <= value <= high:
        problems.append((
            "value_out_of_range",
            f"{label} {value:g}{unit} is outside the plausible range {low:g}–{high:g}{unit}.",
            f"Ask the user to confirm the {label.lower()}.",
        ))


def validate_request(request: DoughRequest, now: datetime) -> None:
    """Plausibility: ranges from config, hydration per flour type, target_time in the future.

    Collects every problem and raises one GuardrailError, so the LLM can fix all at once.
    """
    problems: list[Problem] = []
    _check_range(problems, "Pizza count", request.pizza_count, config.PIZZA_COUNT_RANGE, "")
    _check_range(problems, "Ball weight", request.ball_weight_g, config.BALL_WEIGHT_G_RANGE, " g")
    _check_range(problems, "Salt", request.salt_pct, config.SALT_PCT_RANGE, " %")
    _check_range(problems, "Room temperature", request.room_temp_c, config.ROOM_TEMP_C_RANGE, " °C")
    _check_range(problems, "Fridge temperature", request.fridge_temp_c, config.FRIDGE_TEMP_C_RANGE, " °C")

    max_hydration = config.MAX_HYDRATION_PCT[request.flour_type]
    if request.hydration_pct > max_hydration:
        problems.append((
            "hydration_out_of_range",
            f"{request.hydration_pct:g} % hydration is too wet for {request.flour_type} flour "
            f"(max {max_hydration:g} %): the result would be a batter, not a workable dough.",
            f"Use at most {max_hydration:g} % or a stronger flour (e.g. manitoba).",
        ))
    elif request.hydration_pct < config.MIN_HYDRATION_PCT:
        problems.append((
            "hydration_out_of_range",
            f"{request.hydration_pct:g} % hydration is too dry for pizza dough "
            f"(min {config.MIN_HYDRATION_PCT:g} %).",
            f"Use at least {config.MIN_HYDRATION_PCT:g} % hydration.",
        ))

    if request.target_time <= now:
        problems.append(("invalid_target_time", "The bake time lies in the past.",
                         "Ask the user for a future bake time."))
    elif request.target_time - now > timedelta(days=config.MAX_PLANNING_HORIZON_DAYS):
        problems.append((
            "invalid_target_time",
            f"The bake time is more than {config.MAX_PLANNING_HORIZON_DAYS} days away.",
            "Plan at most two weeks ahead; the dough is made in the last few days anyway.",
        ))

    if problems:
        rule = problems[0][0] if len(problems) == 1 else "invalid_input"
        raise GuardrailError(rule, " ".join(m for _, m, _ in problems), hint=" ".join(h for _, _, h in problems))
