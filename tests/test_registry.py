import json
from datetime import timedelta

import pytest
from pydantic import ValidationError

from fermentation_agent.agent.registry import TOOL_SPECS, SubmitRequestArgs, tool_schemas


def test_allowlist_has_no_side_effect_tools():
    names = {schema["name"] for schema in tool_schemas()}
    assert names == {"submit_request", "build_timeline", "calculate_yeast_percentage",
                     "calculate_water_temperature", "calculate_bakers_math", "finish_plan"}
    assert "create_calendar_events" not in names


def test_schemas_are_self_contained():
    dumped = json.dumps(tool_schemas())
    assert "$ref" not in dumped and "$defs" not in dumped
    build = next(s for s in tool_schemas() if s["name"] == "build_timeline")
    assert build["parameters"]["properties"]["phases"]["items"]["properties"]["temp_c"]["type"] == "number"


def test_extra_arguments_rejected():
    with pytest.raises(ValidationError):
        TOOL_SPECS["calculate_water_temperature"][0].model_validate(
            {"room_temp_c": 22, "mixing": "hand", "rm_rf": True})


def test_naive_times_are_local():
    args = SubmitRequestArgs(pizza_count=4, room_temp_c=22, mixing="hand", target_time="2026-11-07T19:00")
    assert args.target_time.utcoffset() == timedelta(hours=1)


def test_prompt_contains_current_time_and_mixing_rule():
    from conftest import NOW
    from fermentation_agent.agent.prompts import build_instructions

    text = build_instructions(NOW)
    assert "Thursday, 2026-11-05 18:00 (Europe/Vienna)" in text
    assert "never assume it" in text
