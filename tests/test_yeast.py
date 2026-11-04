import json
from pathlib import Path

import pytest

from fermentation_agent import config
from fermentation_agent.models import FermentationPhase, YeastType
from fermentation_agent.tools.yeast import calculate_yeast_percentage, equivalent_hours, rate

REFERENCES = json.loads((Path(__file__).parent.parent / "data" / "yeast_reference.json").read_text())["doughs"]


def phases(*spec: tuple[float, float]) -> list[FermentationPhase]:
    return [FermentationPhase(name=f"p{i}", temp_c=t, hours=h) for i, (t, h) in enumerate(spec)]


@pytest.mark.parametrize("ref", REFERENCES, ids=lambda r: r["name"])
def test_reference_doughs_within_25_percent(ref):
    result = calculate_yeast_percentage([FermentationPhase(**p) for p in ref["phases"]], YeastType.FRESH)
    assert result.yeast_pct == pytest.approx(ref["fresh_yeast_pct"], rel=0.25)


def test_rate_is_one_at_reference_temperature():
    assert rate(config.REFERENCE_TEMP_C) == pytest.approx(1.0)


def test_rate_is_continuous_at_break():
    assert rate(config.Q10_BREAK_C - 1e-9) == pytest.approx(rate(config.Q10_BREAK_C))


@pytest.mark.parametrize("cold,warm", [(4, 8), (8, 15), (15, 22), (22, 30)])
def test_colder_means_slower(cold, warm):
    assert rate(cold) < rate(warm)


def test_more_time_means_less_yeast():
    pcts = [calculate_yeast_percentage(phases((22, 1), (4, h), (22, 4)), YeastType.FRESH).yeast_pct
            for h in (12, 24, 48, 72)]
    assert pcts == sorted(pcts, reverse=True)


def test_equivalent_hours_sums_phases():
    assert equivalent_hours(phases((24, 2), (24, 3))) == pytest.approx(5.0)


def test_dry_yeast_conversion():
    plan = phases((22, 8))
    fresh = calculate_yeast_percentage(plan, YeastType.FRESH).yeast_pct
    instant = calculate_yeast_percentage(plan, YeastType.INSTANT_DRY).yeast_pct
    assert instant == pytest.approx(fresh * 0.33, abs=0.001)


def test_clamps_very_short_plan():
    result = calculate_yeast_percentage(phases((22, 1)), YeastType.FRESH)
    assert result.clamped
    assert result.yeast_pct == config.YEAST_PCT_RANGE_FRESH[1]
    assert "under-fermented" in result.warnings[0]


def test_clamps_very_long_plan():
    result = calculate_yeast_percentage(phases((26, 48)), YeastType.FRESH)
    assert result.clamped
    assert result.yeast_pct == config.YEAST_PCT_RANGE_FRESH[0]
    assert "over-ferment" in result.warnings[0]


def test_requires_phases():
    with pytest.raises(ValueError):
        calculate_yeast_percentage([], YeastType.FRESH)
