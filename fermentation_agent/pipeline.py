"""Offline mode: the same tools in a fixed order, without an LLM. Baseline for tests and demo.

Instead of an LLM adjusting the plan, a simple search tries cold-retard durations close
to 24 h, then same-day doughs, until the schedule guardrails pass. The final calls go
through the same dispatcher, so trace and guardrails are identical to LLM mode.
"""

import json
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

from fermentation_agent.agent.loop import AgentResult, export_if_confirmed, result_from_session
from fermentation_agent.agent.model import ToolCall
from fermentation_agent.agent.session import AgentSession
from fermentation_agent.agent.summary import render_template_summary
from fermentation_agent.models import DoughRequest, FermentationPhase
from fermentation_agent.tools.schedule_check import validate_schedule
from fermentation_agent.tools.timeline import build_timeline

DEFAULT_FRIDGE_HOURS = 24
FRIDGE_HOURS_RANGE = (8, 48)
SAME_DAY_FINAL_PROOF_HOURS = range(4, 11)


def candidate_plans(request: DoughRequest) -> Iterator[list[FermentationPhase]]:
    """Cold retards ordered by distance from 24 h (24, 23, 25, 22, …), then same-day doughs."""
    low, high = FRIDGE_HOURS_RANGE
    for delta in range(0, high - low + 1):
        for hours in ((DEFAULT_FRIDGE_HOURS - delta, DEFAULT_FRIDGE_HOURS + delta) if delta else (DEFAULT_FRIDGE_HOURS,)):
            if low <= hours <= high:
                yield [
                    FermentationPhase(name="bulk", temp_c=request.room_temp_c, hours=2),
                    FermentationPhase(name="cold retard", temp_c=request.fridge_temp_c, hours=hours),
                    FermentationPhase(name="final proof", temp_c=request.room_temp_c, hours=4),
                ]
    for hours in SAME_DAY_FINAL_PROOF_HOURS:
        yield [
            FermentationPhase(name="bulk", temp_c=request.room_temp_c, hours=2),
            FermentationPhase(name="final proof", temp_c=request.room_temp_c, hours=hours),
        ]


def _call(session: AgentSession, name: str, **arguments) -> dict:
    result = session.dispatch(ToolCall(name, json.dumps(arguments, default=str), f"offline-{len(session.trace)}"))
    return result.result


def plan_offline(request: DoughRequest, now: datetime, confirm: Callable[[AgentResult], bool] = lambda _: False,
                 output_path: Path = Path("out/plan.ics")) -> AgentResult:
    session = AgentSession(now=now)
    submitted = _call(session, "submit_request", **request.model_dump(mode="json"))
    if "error" in submitted:
        return result_from_session(session, "rejected", f"{submitted['message']} {submitted['hint']}")

    phases = last_violation = None
    for candidate in candidate_plans(request):
        validation = validate_schedule(build_timeline(request.target_time, candidate), now)
        if validation.ok:
            phases = candidate
            break
        last_violation = validation.violations[0].message
    if phases is None:
        return result_from_session(session, "failed", f"No plan fits the schedule rules. {last_violation}")

    phase_args = [phase.model_dump() for phase in phases]
    _call(session, "build_timeline", target_time=request.target_time.isoformat(), phases=phase_args)
    yeast = _call(session, "calculate_yeast_percentage", phases=phase_args, yeast_type=request.yeast_type)
    _call(session, "calculate_water_temperature", room_temp_c=request.room_temp_c, mixing=request.mixing)
    _call(session, "calculate_bakers_math", pizza_count=request.pizza_count, ball_weight_g=request.ball_weight_g,
          hydration_pct=request.hydration_pct, salt_pct=request.salt_pct, yeast_pct=yeast["yeast_pct"])
    _call(session, "finish_plan", summary=render_template_summary(session))

    result = result_from_session(session, "planned", session.summary)
    return export_if_confirmed(result, session, confirm, output_path)
