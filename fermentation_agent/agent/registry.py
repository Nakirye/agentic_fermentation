"""Allowlist of tools the LLM may call: name → (Pydantic args model, description).

The handlers live in AgentSession (they need the session state). create_calendar_events
is deliberately NOT registered; the loop calls it after user confirmation.
"""

from copy import deepcopy
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from fermentation_agent import config
from fermentation_agent.models import FermentationPhase, FlourType, Mixing, YeastType


def _localize(value: datetime) -> datetime:
    """Naive times from the model are read as local time."""
    return value.replace(tzinfo=ZoneInfo(config.TIMEZONE)) if value.tzinfo is None else value


LocalDatetime = Annotated[datetime, AfterValidator(_localize)]
Phases = Annotated[list[FermentationPhase], Field(min_length=1, max_length=6)]


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SubmitRequestArgs(ToolArgs):
    pizza_count: int
    room_temp_c: float
    mixing: Mixing
    target_time: LocalDatetime = Field(description="When the pizzas go into the oven, ISO 8601.")
    ball_weight_g: float | None = None
    hydration_pct: float | None = None
    salt_pct: float | None = None
    flour_type: FlourType | None = None
    yeast_type: YeastType | None = None
    fridge_temp_c: float | None = None


class BuildTimelineArgs(ToolArgs):
    target_time: LocalDatetime
    phases: Phases = Field(description="Fermentation phases in order, e.g. bulk → cold retard → final proof.")
    autolyse_min: int = Field(30, ge=0, le=120)
    knead_min: int = Field(15, ge=5, le=30)
    stretch_fold_count: int = Field(3, ge=0, le=6)
    stretch_fold_interval_min: int = Field(30, ge=15, le=60)
    preheat_min: int = Field(45, ge=20, le=90)
    ball_before_phase: int | None = Field(None, description="Index of the phase before which the dough is balled; default: last phase.")


class YeastArgs(ToolArgs):
    phases: Phases
    yeast_type: YeastType


class WaterTempArgs(ToolArgs):
    room_temp_c: float
    mixing: Mixing
    target_dough_temp_c: float = config.TARGET_DOUGH_TEMP_C
    flour_temp_c: float | None = None


class BakersMathArgs(ToolArgs):
    pizza_count: int
    ball_weight_g: float
    hydration_pct: float
    salt_pct: float
    yeast_pct: float


class FinishPlanArgs(ToolArgs):
    summary: str = Field(max_length=config.MAX_SUMMARY_CHARS,
                         description="Final summary for the user, in the user's language.")


TOOL_SPECS: dict[str, tuple[type[ToolArgs], str]] = {
    "submit_request": (SubmitRequestArgs,
        "Validate the user's request. Returns the full request including defaults used. Call first."),
    "build_timeline": (BuildTimelineArgs,
        "Schedule all steps backwards from the bake time and check them against the sleep window "
        "and the current time. Returns the timeline or a schedule_violation error."),
    "calculate_yeast_percentage": (YeastArgs,
        "Yeast in % of flour for the given phases. Use exactly the phases of the accepted timeline."),
    "calculate_water_temperature": (WaterTempArgs,
        "Water temperature needed to reach the target dough temperature."),
    "calculate_bakers_math": (BakersMathArgs,
        "Exact gram amounts for flour, water, salt and yeast."),
    "finish_plan": (FinishPlanArgs,
        "Submit the final summary. Checks that all results belong to one plan and that every "
        "number in the summary matches a tool result."),
}


def _inline_refs(schema: dict) -> dict:
    """Replace $ref/$defs by their definitions, so every provider can read the schema."""
    definitions = schema.pop("$defs", {})

    def resolve(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(deepcopy(definitions[node["$ref"].rsplit("/", 1)[-1]]))
            return {key: resolve(value) for key, value in node.items()}
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    return resolve(schema)


def tool_schemas() -> list[dict]:
    """Function tool definitions (OpenAI Responses API format), generated from the args models."""
    return [
        {
            "type": "function",
            "name": name,
            "description": description,
            "parameters": _inline_refs(args_model.model_json_schema()),
        }
        for name, (args_model, description) in TOOL_SPECS.items()
    ]
