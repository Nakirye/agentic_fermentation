"""Fit YEAST_K, YEAST_EXPONENT and Q10_COLD to data/yeast_reference.json.

Grid search minimising the squared log error. Copy the printed values into
fermentation_agent/config.py by hand.

    python scripts/calibrate_yeast.py
"""

import json
import math
from itertools import product
from pathlib import Path

from fermentation_agent.models import FermentationPhase
from fermentation_agent.tools.yeast import equivalent_hours, fresh_yeast_pct

REFERENCE_FILE = Path(__file__).resolve().parent.parent / "data" / "yeast_reference.json"


def load_references() -> list[tuple[str, list[FermentationPhase], float]]:
    doughs = json.loads(REFERENCE_FILE.read_text())["doughs"]
    return [
        (d["name"], [FermentationPhase(**p) for p in d["phases"]], d["fresh_yeast_pct"])
        for d in doughs
    ]


def loss(refs, k: float, exponent: float, q10_cold: float) -> float:
    return sum(
        math.log(fresh_yeast_pct(equivalent_hours(phases, q10_cold), k, exponent) / target) ** 2
        for _, phases, target in refs
    )


def frange(start: float, stop: float, step: float) -> list[float]:
    return [round(start + i * step, 4) for i in range(int(round((stop - start) / step)) + 1)]


def main() -> None:
    refs = load_references()
    grid = product(frange(0.5, 100.0, 0.5), frange(0.5, 4.0, 0.05), frange(2.0, 12.0, 0.25))
    k, exponent, q10_cold = min(grid, key=lambda params: loss(refs, *params))

    print(f"Q10_COLD = {q10_cold}")
    print(f"YEAST_K = {k}")
    print(f"YEAST_EXPONENT = {exponent}\n")
    print(f"{'reference':<24}{'eq_h':>7}{'target %':>10}{'model %':>9}{'error':>8}")
    for name, phases, target in refs:
        eq_h = equivalent_hours(phases, q10_cold)
        pct = fresh_yeast_pct(eq_h, k, exponent)
        print(f"{name:<24}{eq_h:>7.1f}{target:>10.2f}{pct:>9.2f}{(pct / target - 1):>8.0%}")


if __name__ == "__main__":
    main()
