from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from fermentation_agent import config
from fermentation_agent.errors import GuardrailError
from fermentation_agent.models import FermentationPhase, StepKind
from fermentation_agent.tools.timeline import build_timeline

VIENNA = ZoneInfo("Europe/Vienna")
SAT_19 = datetime(2026, 11, 7, 19, tzinfo=VIENNA)


def cold_plan(fridge_hours: float = 24) -> list[FermentationPhase]:
    return [
        FermentationPhase(name="bulk", temp_c=22, hours=2),
        FermentationPhase(name="cold retard", temp_c=4, hours=fridge_hours),
        FermentationPhase(name="final proof", temp_c=22, hours=4),
    ]


def by_name(timeline):
    return {step.name: step for step in timeline.steps}


def test_bake_starts_at_target():
    steps = by_name(build_timeline(SAT_19, cold_plan()))
    assert steps["Bake"].start == SAT_19


def test_chain_duration_matches_inputs():
    timeline = build_timeline(SAT_19, cold_plan())
    first = timeline.steps[0]
    assert first.name == "Mix flour and water"
    chain_min = config.MIX_MIN + 30 + 15 + (2 + 24 + 4) * 60 + config.BALLING_MIN
    assert SAT_19 - first.start == timedelta(minutes=chain_min)


def test_steps_sorted_and_timezone_kept():
    timeline = build_timeline(SAT_19, cold_plan())
    starts = [step.start for step in timeline.steps]
    assert starts == sorted(starts)
    assert all(step.start.tzinfo is VIENNA for step in timeline.steps)


def test_stretch_folds_inside_first_phase():
    steps = by_name(build_timeline(SAT_19, cold_plan()))
    folds = [s for name, s in steps.items() if name.startswith("Stretch & fold")]
    assert len(folds) == 3
    assert all(steps["Bulk"].start < f.start and f.end <= steps["Bulk"].end for f in folds)
    assert all(f.kind is StepKind.ACTIVE for f in folds)


def test_fridge_moves_at_cold_phase_boundaries():
    steps = by_name(build_timeline(SAT_19, cold_plan()))
    assert steps["Put dough in the fridge"].start == steps["Cold retard"].start
    assert steps["Take dough out of the fridge"].start == steps["Cold retard"].end


def test_balling_defaults_to_before_last_phase_and_after_fridge():
    timeline = build_timeline(SAT_19, cold_plan())
    names = [step.name for step in timeline.steps]
    assert names.index("Take dough out of the fridge") < names.index("Ball the dough") < names.index("Final proof")
    assert by_name(timeline)["Ball the dough"].end == by_name(timeline)["Final proof"].start


def test_ball_before_cold_retard():
    timeline = build_timeline(SAT_19, cold_plan(), ball_before_phase=1)
    names = [step.name for step in timeline.steps]
    assert names.index("Ball the dough") < names.index("Put dough in the fridge")


def test_without_autolyse():
    timeline = build_timeline(SAT_19, cold_plan(), autolyse_min=0)
    assert timeline.steps[0].name == "Knead"
    assert "Autolyse" not in by_name(timeline)


def test_preheat_ends_at_bake():
    steps = by_name(build_timeline(SAT_19, cold_plan(), preheat_min=60))
    assert steps["Preheat oven"].end == SAT_19
    assert steps["Preheat oven"].start == SAT_19 - timedelta(hours=1)


def test_dst_switch_keeps_real_durations():
    # Austria switches back on 2026-10-25 at 03:00 → 02:00; the 24 h retard spans it.
    target = datetime(2026, 10, 25, 19, tzinfo=VIENNA)
    steps = by_name(build_timeline(target, cold_plan()))
    retard = steps["Cold retard"]
    assert retard.end.astimezone(UTC) - retard.start.astimezone(UTC) == timedelta(hours=24)
    assert retard.start.utcoffset() == timedelta(hours=2)
    assert retard.end.utcoffset() == timedelta(hours=1)


def test_duplicate_phase_names_are_numbered():
    phases = [FermentationPhase(name="rest", temp_c=22, hours=2), FermentationPhase(name="rest", temp_c=22, hours=3)]
    names = [step.name for step in build_timeline(SAT_19, phases).steps]
    assert "Rest (1)" in names and "Rest (2)" in names
    assert len(names) == len(set(names))


def test_requires_aware_target():
    with pytest.raises(ValueError):
        build_timeline(datetime(2026, 11, 7, 19), cold_plan())


def test_requires_two_phases():
    with pytest.raises(GuardrailError) as exc:
        build_timeline(SAT_19, [FermentationPhase(name="bulk", temp_c=22, hours=8)])
    assert exc.value.rule == "invalid_plan"


@pytest.mark.parametrize("index", [0, 3])
def test_rejects_invalid_ball_index(index):
    with pytest.raises(GuardrailError):
        build_timeline(SAT_19, cold_plan(), ball_before_phase=index)


def test_rejects_folds_that_do_not_fit():
    with pytest.raises(GuardrailError) as exc:
        build_timeline(SAT_19, cold_plan(), stretch_fold_count=4, stretch_fold_interval_min=30)
    assert "Lengthen the first phase" in exc.value.hint
