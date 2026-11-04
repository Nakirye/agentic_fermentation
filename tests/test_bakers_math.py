import pytest

from fermentation_agent.tools.bakers_math import calculate_bakers_math


def test_reference_example():
    result = calculate_bakers_math(4, 250, hydration_pct=65, salt_pct=2.8, yeast_pct=0.2)
    assert result.total_dough_g == 1025  # 1000 g + 2.5 % waste
    assert (result.flour_g, result.water_g, result.salt_g, result.yeast_g) == (610, 397, 17, 1.2)


@pytest.mark.parametrize("count,weight,hydration", [(1, 180, 55), (6, 270, 70), (30, 350, 75)])
def test_parts_sum_to_total(count, weight, hydration):
    r = calculate_bakers_math(count, weight, hydration_pct=hydration, salt_pct=3, yeast_pct=0.3)
    assert abs(r.flour_g + r.water_g + r.salt_g + r.yeast_g - r.total_dough_g) <= 2


def test_zero_yeast():
    assert calculate_bakers_math(4, 250, 65, 2.8, 0).yeast_g == 0


@pytest.mark.parametrize("count,weight", [(0, 250), (4, 0), (-1, 250)])
def test_rejects_non_positive_amounts(count, weight):
    with pytest.raises(ValueError):
        calculate_bakers_math(count, weight, 65, 2.8, 0.2)


def test_rejects_negative_percentage():
    with pytest.raises(ValueError):
        calculate_bakers_math(4, 250, 65, -1, 0.2)
