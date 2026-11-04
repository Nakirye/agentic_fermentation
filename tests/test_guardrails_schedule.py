from datetime import datetime, timedelta

import pytest

from conftest import SAT_19, VIENNA
from fermentation_agent.guardrails.schedule import (
    _ceil_quarter_hour, check_feasibility, check_sleep_window, format_duration,
)
from fermentation_agent.models import StepKind, Timeline, TimelineStep
from fermentation_agent.tools.schedule_check import validate_schedule
from fermentation_agent.tools.timeline import build_timeline

FRI_9 = datetime(2026, 11, 6, 9, tzinfo=VIENNA)


def single_step(start: datetime, minutes: int = 5, kind: StepKind = StepKind.ACTIVE) -> Timeline:
    step = TimelineStep(name="Stretch & fold", kind=kind, start=start, end=start + timedelta(minutes=minutes))
    return Timeline(target_time=SAT_19, steps=[step])


def test_daytime_plan_is_ok(cold_plan):
    assert check_sleep_window(build_timeline(SAT_19, cold_plan())) == []


def test_stretch_and_fold_at_0330_is_caught(cold_plan):
    # Fridge time chosen so the bulk phase starts Fri 03:00 → first fold at 03:30 (proposal example).
    violations = check_sleep_window(build_timeline(SAT_19, cold_plan(33.75)))
    fold = next(v for v in violations if v.step == "Stretch & fold 1/3")
    assert fold.rule == "sleep_window"
    assert "Fri 03:30" in fold.message


def test_message_says_how_far_to_move():
    [violation] = check_sleep_window(single_step(datetime(2026, 11, 6, 3, 30, tzinfo=VIENNA)))
    assert "4 h 35 min earlier" in violation.message
    assert "3 h 30 min later" in violation.message


def test_step_overlapping_window_start():
    assert check_sleep_window(single_step(datetime(2026, 11, 6, 22, 58, tzinfo=VIENNA)))


@pytest.mark.parametrize("hour,minute", [(22, 55), (7, 0)])
def test_steps_just_outside_window(hour, minute):
    assert check_sleep_window(single_step(datetime(2026, 11, 6, hour, minute, tzinfo=VIENNA))) == []


def test_passive_steps_may_run_overnight():
    timeline = single_step(datetime(2026, 11, 6, 2, 0, tzinfo=VIENNA), minutes=600, kind=StepKind.PASSIVE)
    assert check_sleep_window(timeline) == []


def test_late_bake_time_is_users_choice(cold_plan):
    late = datetime(2026, 11, 7, 23, 30, tzinfo=VIENNA)
    assert check_sleep_window(build_timeline(late, cold_plan())) == []


def test_sleep_window_on_dst_night():
    assert check_sleep_window(single_step(datetime(2026, 10, 25, 2, 30, tzinfo=VIENNA)))


def test_feasible_when_enough_time(cold_plan):
    assert check_feasibility(build_timeline(SAT_19, cold_plan()), FRI_9) == []


def test_too_soon_proposes_new_bake_time(cold_plan):
    # Plan starts Fri 11:55; at Sat 10:00 it is 22 h 20 min too late → earliest bake Sun 17:20 → 17:30.
    [violation] = check_feasibility(build_timeline(SAT_19, cold_plan()), datetime(2026, 11, 7, 10, tzinfo=VIENNA))
    assert violation.rule == "too_soon"
    assert "22 h 20 min" in violation.message
    assert "Sun 17:30" in violation.message


def test_lead_time_is_required(cold_plan):
    timeline = build_timeline(SAT_19, cold_plan())
    assert check_feasibility(timeline, timeline.steps[0].start - timedelta(minutes=10))


def test_validate_schedule_combines_checks(cold_plan):
    assert validate_schedule(build_timeline(SAT_19, cold_plan()), FRI_9).ok
    result = validate_schedule(build_timeline(SAT_19, cold_plan(33.75)), datetime(2026, 11, 6, 2, tzinfo=VIENNA))
    assert not result.ok
    assert {v.rule for v in result.violations} == {"too_soon", "sleep_window"}


@pytest.mark.parametrize("minutes,text", [(0, "0 min"), (45, "45 min"), (120, "2 h"), (90.2, "1 h 31 min")])
def test_format_duration(minutes, text):
    assert format_duration(timedelta(minutes=minutes)) == text


@pytest.mark.parametrize("given,expected", [((12, 30, 0), (12, 30)), ((12, 30, 20), (12, 45)), ((12, 31, 0), (12, 45))])
def test_ceil_quarter_hour(given, expected):
    h, m, s = given
    result = _ceil_quarter_hour(datetime(2026, 11, 7, h, m, s, tzinfo=VIENNA))
    assert (result.hour, result.minute, result.second) == (*expected, 0)
