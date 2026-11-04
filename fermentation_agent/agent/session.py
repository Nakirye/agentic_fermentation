"""State of one planning run and the dispatcher that executes allowlisted tool calls.

Every tool result is stored, so finish_plan can check that ingredients, yeast, water
and timeline all belong to the same plan before anything reaches the user.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from fermentation_agent import config
from fermentation_agent.agent.model import ToolCall, ToolResult
from fermentation_agent.agent.registry import (
    TOOL_SPECS, BakersMathArgs, BuildTimelineArgs, FinishPlanArgs, SubmitRequestArgs, ToolArgs, WaterTempArgs,
    YeastArgs,
)
from fermentation_agent.agent.summary import render_template_summary
from fermentation_agent.errors import GuardrailError
from fermentation_agent.guardrails.input import validate_request
from fermentation_agent.guardrails.output import check_summary_numbers, collect_facts
from fermentation_agent.models import DoughRequest, Ingredients, Timeline, WaterTempResult, YeastResult
from fermentation_agent.tools.bakers_math import calculate_bakers_math
from fermentation_agent.tools.schedule_check import validate_schedule
from fermentation_agent.tools.timeline import build_timeline
from fermentation_agent.tools.water_temp import calculate_water_temperature
from fermentation_agent.tools.yeast import calculate_yeast_percentage


def _kwargs(args: ToolArgs) -> dict:
    """Field values as they are (nested models stay models, unlike model_dump)."""
    return {name: getattr(args, name) for name in type(args).model_fields}


def _validation_message(error: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, e['loc'])) or 'arguments'}: {e['msg']}" for e in error.errors()[:5])


@dataclass
class AgentSession:
    now: datetime
    request: DoughRequest | None = None
    timeline: Timeline | None = None
    timeline_args: BuildTimelineArgs | None = None
    yeast: YeastResult | None = None
    yeast_args: YeastArgs | None = None
    water: WaterTempResult | None = None
    water_args: WaterTempArgs | None = None
    ingredients: Ingredients | None = None
    bakers_args: BakersMathArgs | None = None
    schedule_failures: int = 0
    summary_failures: int = 0
    summary: str | None = None
    summary_replaced: bool = False  # True if the LLM summary failed the output guardrail
    finished: bool = False
    trace: list[dict] = field(default_factory=list)

    @property
    def schedule_budget_exhausted(self) -> bool:
        return self.schedule_failures >= config.MAX_SCHEDULE_RETRIES

    # --- dispatcher -------------------------------------------------------

    def dispatch(self, call: ToolCall) -> ToolResult:
        """Validate and run one tool call. Never raises: failures become error results for the LLM."""
        started = perf_counter()
        arguments: Any = call.arguments
        try:
            spec = TOOL_SPECS.get(call.name)
            if spec is None:
                raise GuardrailError("unknown_tool", f"There is no tool named '{call.name}'.",
                                     hint=f"Available tools: {', '.join(TOOL_SPECS)}.")
            try:
                arguments = json.loads(call.arguments or "{}")
            except json.JSONDecodeError as error:
                raise GuardrailError("invalid_arguments", f"Arguments are not valid JSON: {error.msg}.") from None
            try:
                args = spec[0].model_validate(arguments)
            except ValidationError as error:
                raise GuardrailError("invalid_arguments", _validation_message(error),
                                     hint="Fix the arguments to match the tool schema.") from None
            result = getattr(self, f"_tool_{call.name}")(args)
            ok = True
        except GuardrailError as error:
            result, ok = error.to_dict(), False
        except ValueError as error:  # tool-level input errors
            result, ok = {"error": "invalid_arguments", "message": str(error), "hint": ""}, False
        self.trace.append({
            "tool": call.name,
            "arguments": arguments,
            "ok": ok,
            "result": result,
            "ms": round((perf_counter() - started) * 1000, 1),
        })
        return ToolResult(call.call_id, result)

    def _require_request(self) -> DoughRequest:
        if self.request is None:
            raise GuardrailError("missing_request", "No validated request yet.", hint="Call submit_request first.")
        return self.request

    # --- tool handlers ----------------------------------------------------

    def _tool_submit_request(self, args: SubmitRequestArgs) -> dict:
        given = args.model_dump(exclude_none=True)
        request = DoughRequest(**given)
        validate_request(request, self.now)
        self.request = request
        defaults = {name: getattr(request, name) for name in DoughRequest.model_fields if name not in given}
        return {"request": request.model_dump(mode="json"), "defaults_used": list(defaults)}

    def _tool_build_timeline(self, args: BuildTimelineArgs) -> dict:
        self._require_request()
        if self.schedule_budget_exhausted:
            raise GuardrailError(
                "retry_budget_exhausted",
                f"No valid schedule after {config.MAX_SCHEDULE_RETRIES} attempts.",
                hint="Stop planning. Explain the conflict to the user and suggest another bake time.",
            )
        timeline = build_timeline(**_kwargs(args))
        validation = validate_schedule(timeline, self.now)
        if not validation.ok:
            self.schedule_failures += 1
            left = config.MAX_SCHEDULE_RETRIES - self.schedule_failures
            raise GuardrailError(
                "schedule_violation",
                " ".join(v.message for v in validation.violations),
                hint=(f"Change the phase durations (usually the cold retard) to move the steps, "
                      f"not the bake time. Attempts left: {left}."),
            )
        self.timeline, self.timeline_args = timeline, args
        return {"timeline": [
            {"step": s.name, "kind": s.kind, "start": f"{s.start:%a %Y-%m-%d %H:%M}", "end": f"{s.end:%a %H:%M}"}
            for s in timeline.steps
        ]}

    def _tool_calculate_yeast_percentage(self, args: YeastArgs) -> dict:
        self._require_request()
        self.yeast = calculate_yeast_percentage(args.phases, args.yeast_type)
        self.yeast_args = args
        return self.yeast.model_dump(mode="json")

    def _tool_calculate_water_temperature(self, args: WaterTempArgs) -> dict:
        self._require_request()
        self.water = calculate_water_temperature(**_kwargs(args))
        self.water_args = args
        return self.water.model_dump(mode="json")

    def _tool_calculate_bakers_math(self, args: BakersMathArgs) -> dict:
        self._require_request()
        self.ingredients = calculate_bakers_math(**_kwargs(args))
        self.bakers_args = args
        return self.ingredients.model_dump(mode="json")

    def _tool_finish_plan(self, args: FinishPlanArgs) -> dict:
        problems = self._consistency_problems()
        if problems:
            raise GuardrailError("inconsistent_plan", " ".join(problems),
                                 hint="Recalculate the listed parts, then call finish_plan again.")
        mismatches = check_summary_numbers(args.summary, self.facts())
        if mismatches:
            self.summary_failures += 1
            if self.summary_failures <= config.MAX_SUMMARY_RETRIES:
                raise GuardrailError(
                    "summary_mismatch",
                    f"These numbers in the summary do not match any tool result: {', '.join(mismatches)}.",
                    hint="Use only numbers from the tool results, rounded at most to whole units.",
                )
            self.summary, self.summary_replaced = render_template_summary(self), True
        else:
            self.summary = args.summary
        self.finished = True
        return {"status": "accepted_with_template" if self.summary_replaced else "accepted"}

    # --- final checks -----------------------------------------------------

    def _consistency_problems(self) -> list[str]:
        """Cross-tool guardrail: every part of the plan must be computed for the same inputs."""
        request = self.request
        if request is None:
            return ["No request was submitted."]
        problems = []
        if self.timeline is None:
            problems.append("No valid timeline was built.")
        elif self.timeline_args.target_time != request.target_time:
            problems.append("The timeline uses a different bake time than the request.")
        if self.yeast is None:
            problems.append("Yeast was not calculated.")
        else:
            if self.timeline_args and self.yeast_args.phases != self.timeline_args.phases:
                problems.append("Yeast was calculated for different phases than the accepted timeline.")
            if self.yeast_args.yeast_type != request.yeast_type:
                problems.append(f"Yeast was calculated for {self.yeast_args.yeast_type}, "
                                f"but the request uses {request.yeast_type}.")
        if self.water is None:
            problems.append("Water temperature was not calculated.")
        elif (self.water_args.room_temp_c, self.water_args.mixing) != (request.room_temp_c, request.mixing):
            problems.append("Water temperature was calculated for a different room temperature or mixing method.")
        if self.ingredients is None:
            problems.append("Ingredient amounts were not calculated.")
        else:
            b = self.bakers_args
            if (b.pizza_count, b.ball_weight_g, b.hydration_pct, b.salt_pct) != (
                    request.pizza_count, request.ball_weight_g, request.hydration_pct, request.salt_pct):
                problems.append("Ingredient amounts were calculated with different values than the request.")
            if self.yeast is not None and b.yeast_pct != self.yeast.yeast_pct:
                problems.append("Ingredient amounts use a different yeast percentage than the yeast calculation.")
        return problems

    def facts(self):
        """Facts of the accepted plan only – numbers from discarded attempts are not allowed."""
        return collect_facts([
            self.request, self.timeline, self.timeline_args, self.yeast, self.yeast_args,
            self.water, self.water_args, self.ingredients, self.bakers_args,
        ])
