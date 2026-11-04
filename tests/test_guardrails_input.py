from datetime import datetime, timedelta

import pytest

from conftest import SAT_19, VIENNA
from fermentation_agent.errors import GuardrailError
from fermentation_agent.guardrails.input import check_user_text, validate_request
from fermentation_agent.models import DoughRequest, FlourType, Mixing

NOW = datetime(2026, 11, 5, 18, tzinfo=VIENNA)


def request(**overrides) -> DoughRequest:
    values = dict(pizza_count=4, room_temp_c=22, mixing=Mixing.HAND, target_time=SAT_19)
    return DoughRequest(**values | overrides)


def rejected(req: DoughRequest) -> GuardrailError:
    with pytest.raises(GuardrailError) as exc:
        validate_request(req, NOW)
    return exc.value


def test_valid_request_passes():
    validate_request(request(), NOW)


def test_hydration_above_flour_limit():
    error = rejected(request(hydration_pct=92))
    assert error.rule == "hydration_out_of_range"
    assert "batter" in str(error)
    assert "75 %" in error.hint


def test_strong_flour_allows_higher_hydration():
    validate_request(request(hydration_pct=80, flour_type=FlourType.MANITOBA), NOW)


def test_hydration_too_dry():
    assert rejected(request(hydration_pct=50)).rule == "hydration_out_of_range"


@pytest.mark.parametrize("field,value", [
    ("pizza_count", 0), ("pizza_count", 100), ("ball_weight_g", 1000), ("salt_pct", 8),
    ("room_temp_c", 45), ("fridge_temp_c", 12),
])
def test_values_out_of_range(field, value):
    assert rejected(request(**{field: value})).rule == "value_out_of_range"


def test_target_in_past():
    assert rejected(request(target_time=NOW - timedelta(hours=1))).rule == "invalid_target_time"


def test_target_too_far_ahead():
    assert rejected(request(target_time=NOW + timedelta(days=20))).rule == "invalid_target_time"


def test_collects_all_problems():
    error = rejected(request(hydration_pct=95, room_temp_c=40))
    assert error.rule == "invalid_input"
    assert "hydration" in str(error) and "Room temperature" in str(error)


def test_user_text_is_cleaned():
    assert check_user_text("  4 Pizzen\x00 am Samstag\x1b  ") == "4 Pizzen am Samstag"


@pytest.mark.parametrize("text,rule", [("", "empty_input"), ("  \n ", "empty_input"), ("x" * 2001, "input_too_long")])
def test_user_text_rejected(text, rule):
    with pytest.raises(GuardrailError) as exc:
        check_user_text(text)
    assert exc.value.rule == rule
