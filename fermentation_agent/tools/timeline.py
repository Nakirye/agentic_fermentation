from collections import Counter
from datetime import UTC, datetime, timedelta

from fermentation_agent import config
from fermentation_agent.errors import GuardrailError
from fermentation_agent.models import FermentationPhase, StepKind, Timeline, TimelineStep


def _is_cold(phase: FermentationPhase) -> bool:
    return phase.temp_c <= config.FRIDGE_MAX_TEMP_C


def _step(name: str, kind: StepKind, start: datetime, minutes: float, description: str) -> TimelineStep:
    return TimelineStep(name=name, kind=kind, start=start, end=start + timedelta(minutes=minutes),
                        description=description)


def _make_names_unique(steps: list[TimelineStep]) -> None:
    """Calendar UIDs are derived from step names, so duplicates get a running number."""
    totals = Counter(step.name for step in steps)
    seen: Counter[str] = Counter()
    for step in steps:
        if totals[step.name] > 1:
            seen[step.name] += 1
            step.name = f"{step.name} ({seen[step.name]})"


def build_timeline(
    target_time: datetime,
    phases: list[FermentationPhase],
    autolyse_min: int = 30,
    knead_min: int = 15,
    stretch_fold_count: int = 3,
    stretch_fold_interval_min: int = 30,
    preheat_min: int = 45,
    ball_before_phase: int | None = None,
) -> Timeline:
    """Schedule backwards from target_time (= pizzas go into the oven).

    Main chain (forwards, contiguous): mix → autolyse → knead → phases[0] … → balling
    → phases[ball_before_phase] … → bake. Balling defaults to before the last phase.
    Overlaid on the chain: stretch & folds inside phases[0], fridge moves at every
    room/fridge boundary, and preheating during the last 45 minutes before baking.

    All arithmetic runs in UTC so DST switches do not distort durations.
    """
    if target_time.tzinfo is None:
        raise ValueError("target_time must be timezone-aware")
    if len(phases) < 2:
        raise GuardrailError(
            "invalid_plan", "A plan needs at least two phases (bulk and final proof).",
            hint="Split the fermentation into a bulk phase and a final proof phase.",
        )
    ball_idx = len(phases) - 1 if ball_before_phase is None else ball_before_phase
    if not 1 <= ball_idx < len(phases):
        raise GuardrailError(
            "invalid_plan", f"ball_before_phase must be between 1 and {len(phases) - 1}.",
            hint="Balling happens after the bulk phase; omit the parameter to ball before the last phase.",
        )
    bulk_min = phases[0].hours * 60
    if stretch_fold_count * stretch_fold_interval_min + config.STRETCH_FOLD_MIN > bulk_min:
        raise GuardrailError(
            "invalid_plan",
            f"{stretch_fold_count} stretch & folds every {stretch_fold_interval_min} min do not fit "
            f"into the first phase ({phases[0].hours} h).",
            hint="Lengthen the first phase, or use fewer folds or a shorter interval.",
        )

    tz = target_time.tzinfo
    target = target_time.astimezone(UTC)

    chain: list[tuple[str, StepKind, float, str]] = []
    if autolyse_min > 0:
        chain.append(("Mix flour and water", StepKind.ACTIVE, config.MIX_MIN,
                      "Combine flour and water until no dry flour is left. Do not add salt or yeast yet."))
        chain.append(("Autolyse", StepKind.PASSIVE, autolyse_min,
                      "Cover and let the flour hydrate."))
        knead_text = "Add yeast and salt, then knead until the dough is smooth and elastic."
    else:
        knead_text = "Mix all ingredients, then knead until the dough is smooth and elastic."
    chain.append(("Knead", StepKind.ACTIVE, knead_min, knead_text))

    phase_chain_index: list[int] = []
    for i, phase in enumerate(phases):
        if i == ball_idx:
            chain.append(("Ball the dough", StepKind.ACTIVE, config.BALLING_MIN,
                          "Divide into equal pieces, shape tight balls and place them in a covered container."))
        place = "in the fridge" if _is_cold(phase) else "at room temperature"
        phase_chain_index.append(len(chain))
        chain.append((phase.name[:1].upper() + phase.name[1:], StepKind.PASSIVE, phase.hours * 60,
                      f"Let the dough rest {place} ({phase.temp_c:g} °C) for {phase.hours:g} h."))

    steps: list[TimelineStep] = []
    cursor = target - timedelta(minutes=sum(minutes for _, _, minutes, _ in chain))
    for name, kind, minutes, text in chain:
        steps.append(_step(name, kind, cursor, minutes, text))
        cursor = steps[-1].end
    phase_steps = [steps[i] for i in phase_chain_index]
    steps.append(_step("Bake", StepKind.ACTIVE, target, config.BAKE_MIN,
                       "Stretch the balls, top them and bake one after another."))

    for k in range(1, stretch_fold_count + 1):
        steps.append(_step(f"Stretch & fold {k}/{stretch_fold_count}", StepKind.ACTIVE,
                           phase_steps[0].start + timedelta(minutes=k * stretch_fold_interval_min),
                           config.STRETCH_FOLD_MIN,
                           "With wet hands, stretch each side of the dough up and fold it over the centre."))

    # Into the fridge when a cold stretch starts, out when it ends – so balling,
    # which sits between phases, always happens at room temperature.
    for i, (phase, phase_step) in enumerate(zip(phases, phase_steps)):
        cold = _is_cold(phase)
        if cold and (i == 0 or not _is_cold(phases[i - 1])):
            steps.append(_step("Put dough in the fridge", StepKind.ACTIVE, phase_step.start,
                               config.FRIDGE_MOVE_MIN, f"Cover tightly and refrigerate at {phase.temp_c:g} °C."))
        if cold and (i == len(phases) - 1 or not _is_cold(phases[i + 1])):
            steps.append(_step("Take dough out of the fridge", StepKind.ACTIVE, phase_step.end,
                               config.FRIDGE_MOVE_MIN, "Leave it covered at room temperature."))

    steps.append(_step("Preheat oven", StepKind.ACTIVE, target - timedelta(minutes=preheat_min), preheat_min,
                       "Heat the oven with stone or steel to maximum temperature."))

    # Same start → shorter step first, e.g. "take out of fridge" before "ball the dough".
    steps.sort(key=lambda step: (step.start, step.end))
    for step in steps:
        step.start = step.start.astimezone(tz)
        step.end = step.end.astimezone(tz)
    _make_names_unique(steps)
    return Timeline(target_time=target_time, steps=steps)
