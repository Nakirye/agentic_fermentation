"""Pydantic schemas shared by tools, guardrails and the agent loop."""

from datetime import datetime
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, Field


class FlourType(StrEnum):
    TIPO_00 = "tipo_00"
    TYPE_550 = "type_550"
    MANITOBA = "manitoba"
    WHOLE_WHEAT = "whole_wheat"


class YeastType(StrEnum):
    FRESH = "fresh"
    ACTIVE_DRY = "active_dry"
    INSTANT_DRY = "instant_dry"


class Mixing(StrEnum):
    HAND = "hand"
    STAND_MIXER = "stand_mixer"


class StepKind(StrEnum):
    ACTIVE = "active"  # needs a person (knead, fold, ball, bake)
    PASSIVE = "passive"  # dough rests (autolyse, bulk, cold retard)


class DoughRequest(BaseModel):
    """Parameters the LLM extracts from the user's text."""

    pizza_count: int
    ball_weight_g: float = 250.0
    hydration_pct: float = 65.0
    salt_pct: float = 2.8
    flour_type: FlourType = FlourType.TIPO_00
    yeast_type: YeastType = YeastType.FRESH
    room_temp_c: float
    fridge_temp_c: float = 4.0
    mixing: Mixing  # no default: the agent must ask, it changes the water temperature
    target_time: AwareDatetime


class Ingredients(BaseModel):
    flour_g: float
    water_g: float
    salt_g: float
    yeast_g: float
    total_dough_g: float


class FermentationPhase(BaseModel):
    name: str
    temp_c: float
    hours: float = Field(gt=0)


class YeastResult(BaseModel):
    yeast_pct: float  # in the requested yeast type, relative to flour
    yeast_type: YeastType
    equivalent_hours: float  # total time normalised to REFERENCE_TEMP_C
    clamped: bool = False  # True if the model result hit the min/max limit
    warnings: list[str] = []


class WaterTempResult(BaseModel):
    water_temp_c: float
    warnings: list[str] = []


class TimelineStep(BaseModel):
    name: str
    kind: StepKind
    start: datetime
    end: datetime
    description: str = ""


class Timeline(BaseModel):
    target_time: datetime
    steps: list[TimelineStep]


class ScheduleViolation(BaseModel):
    step: str
    at: datetime
    rule: str  # e.g. "sleep_window", "in_past"
    message: str


class ScheduleValidation(BaseModel):
    ok: bool
    violations: list[ScheduleViolation] = []
