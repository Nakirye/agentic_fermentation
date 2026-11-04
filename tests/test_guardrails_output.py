import pytest

from conftest import SAT_19
from fermentation_agent.guardrails.output import check_summary_numbers, collect_facts
from fermentation_agent.models import YeastType
from fermentation_agent.tools.bakers_math import calculate_bakers_math
from fermentation_agent.tools.timeline import build_timeline
from fermentation_agent.tools.yeast import calculate_yeast_percentage


@pytest.fixture
def facts(cold_plan):
    phases = cold_plan()
    yeast = calculate_yeast_percentage(phases, YeastType.FRESH)  # 0.309 %
    ingredients = calculate_bakers_math(4, 250, 65, 2.8, yeast.yeast_pct)  # 610 / 396 / 17 / 1.9 / 1025
    timeline = build_timeline(SAT_19, phases)  # starts Fri 11:55
    return collect_facts([{"phases": phases, "hydration_pct": 65, "ball_weight_g": 250}, yeast, ingredients, timeline])


def test_consistent_summary_passes(facts):
    summary = (
        "Am Freitag um 11:55 geht's los: 610 g Mehl, 396 g Wasser (65 %), 17 g Salz und 1,9 g "
        "Frischhefe (0,31 %). Danach 24 h bei 4 °C in den Kühlschrank. Samstag 19:00 Uhr wird "
        "gebacken – insgesamt rund 31 Stunden für 4 Pizzen à 250 g."
    )
    assert check_summary_numbers(summary, facts) == []


@pytest.mark.parametrize("snippet", ["600 g", "3 g", "48 h", "12:15", "7.30 Uhr", "1,1 kg", "70 %", "18 °C"])
def test_wrong_numbers_are_flagged(facts, snippet):
    assert check_summary_numbers(f"Note: {snippet} for the dough.", facts) == [snippet]


@pytest.mark.parametrize("snippet", ["2 g", "1.025 g", "1,025 kg", "19.00 Uhr", "120 min", "0.5 h", "30 minutes"])
def test_valid_roundings_and_formats(facts, snippet):
    assert check_summary_numbers(f"Note: {snippet}.", facts) == []


def test_bare_numbers_are_ignored(facts):
    assert check_summary_numbers("Make 7 pizzas and fold 5 times.", facts) == []
