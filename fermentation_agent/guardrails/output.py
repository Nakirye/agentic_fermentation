"""Output guardrail: the LLM summary may only contain numbers that come from tool calls.

Only numbers with a unit (g, kg, %, °C, h, min) and clock times are checked; bare
numbers ("4 pizzas", "3 folds") are too ambiguous to verify and are ignored.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel

_TIME = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b|\b([01]?\d|2[0-3])\.([0-5]\d)\s*Uhr\b")
_QUANTITY = re.compile(
    r"(?<![\d.,])(\d+(?:[.,]\d+)*)\s*"
    r"(kg|g|%|°\s?C|°|h\b|hours?\b|Std\.?|Stunden\b|min\b|minutes?\b|Minuten\b)",
    re.IGNORECASE,
)
_HOUR_UNITS = {"h", "hour", "hours", "std", "std.", "stunden"}
_MINUTE_UNITS = {"min", "minute", "minutes", "minuten"}


@dataclass
class Facts:
    numbers: set[float] = field(default_factory=set)
    times: set[str] = field(default_factory=set)  # "HH:MM", local wall-clock time


def collect_facts(values: Iterable[Any]) -> Facts:
    """Walk tool arguments and results recursively and collect every number and clock time.

    Durations of anything with start/end (timeline steps) and the total plan length are
    added too, because a summary naturally mentions them.
    """
    facts = Facts()

    def walk(value: Any) -> None:
        if isinstance(value, BaseModel):
            value = value.model_dump()
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, int | float):
            facts.numbers.add(float(value))
        elif isinstance(value, datetime):
            facts.times.add(f"{value:%H:%M}")
        elif isinstance(value, dict):
            if isinstance(value.get("start"), datetime) and isinstance(value.get("end"), datetime):
                _add_duration(facts, value["end"] - value["start"])
            steps = value.get("steps")
            if steps and isinstance(value.get("target_time"), datetime):
                _add_duration(facts, value["target_time"] - _as_dict(steps[0])["start"])
            for item in value.values():
                walk(item)
        elif isinstance(value, list | tuple | set):
            for item in value:
                walk(item)

    for value in values:
        walk(value)
    return facts


def _as_dict(value: Any) -> dict:
    return value.model_dump() if isinstance(value, BaseModel) else value


def _add_duration(facts: Facts, delta: timedelta) -> None:
    minutes = delta.total_seconds() / 60
    facts.numbers.update({minutes, minutes / 60})


def _candidates(text: str) -> list[tuple[float, float]]:
    """Possible readings of a written number as (value, rounding tolerance).

    Handles 1.9 / 1,9 (decimal) and 1.025 / 1,025 (German or English thousands).
    """
    readings = []
    for decimal in (".", ","):
        other = "," if decimal == "." else "."
        if text.count(decimal) <= 1:
            plain = text.replace(other, "")
            if re.fullmatch(r"\d+(\.\d+)?", plain.replace(decimal, ".")):
                digits = len(plain.split(decimal)[1]) if decimal in plain else 0
                readings.append((float(plain.replace(decimal, ".")), 0.5 * 10**-digits + 1e-9))
    return readings


def _matches(value: float, tolerance: float, facts: Facts) -> bool:
    return any(abs(value - fact) <= tolerance for fact in facts.numbers)


def check_summary_numbers(summary: str, facts: Facts) -> list[str]:
    """Every quantity and clock time in the summary must match a fact.

    A written number matches if it is a correct rounding of a fact at the precision
    it is written with ("2 g" matches 1.9, "600 g" does not match 610).
    Returns the offending snippets (empty list = summary is consistent).
    """
    mismatches = []
    for match in _TIME.finditer(summary):
        hour, minute = (match.group(1), match.group(2)) if match.group(1) else (match.group(3), match.group(4))
        if f"{int(hour):02d}:{minute}" not in facts.times:
            mismatches.append(match.group(0))
    text = _TIME.sub(" ", summary)  # clock times must not be read as quantities

    for match in _QUANTITY.finditer(text):
        number, unit = match.group(1), match.group(2).lower().replace(" ", "")
        ok = False
        for value, tolerance in _candidates(number):
            if unit == "kg":
                value, tolerance = value * 1000, tolerance * 1000
            ok = _matches(value, tolerance, facts)
            if not ok and unit in _HOUR_UNITS:  # "1.5 h" may also be written for 90 min
                ok = _matches(value * 60, tolerance * 60, facts)
            if not ok and unit in _MINUTE_UNITS:
                ok = _matches(value / 60, tolerance / 60, facts)
            if ok:
                break
        if not ok:
            mismatches.append(match.group(0).strip())
    return mismatches
