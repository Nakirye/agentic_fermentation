from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from fermentation_agent.models import FermentationPhase

VIENNA = ZoneInfo("Europe/Vienna")
SAT_19 = datetime(2026, 11, 7, 19, tzinfo=VIENNA)


@pytest.fixture
def cold_plan():
    def make(fridge_hours: float = 24) -> list[FermentationPhase]:
        return [
            FermentationPhase(name="bulk", temp_c=22, hours=2),
            FermentationPhase(name="cold retard", temp_c=4, hours=fridge_hours),
            FermentationPhase(name="final proof", temp_c=22, hours=4),
        ]
    return make


# --- agent test helpers -----------------------------------------------------

import itertools
import json

from fermentation_agent.agent.model import ModelTurn, ToolCall

NOW = datetime(2026, 11, 5, 18, tzinfo=VIENNA)  # Thursday evening
TARGET = "2026-11-07T19:00:00+01:00"
_ids = itertools.count()


def phase_args(fridge_hours: float = 24) -> list[dict]:
    return [
        {"name": "bulk", "temp_c": 22, "hours": 2},
        {"name": "cold retard", "temp_c": 4, "hours": fridge_hours},
        {"name": "final proof", "temp_c": 22, "hours": 4},
    ]


def call(name: str, **arguments) -> ToolCall:
    return ToolCall(name, json.dumps(arguments), f"call-{next(_ids)}")


def turn(*calls: ToolCall) -> ModelTurn:
    return ModelTurn(calls=calls)


def answer(text: str) -> ModelTurn:
    return ModelTurn(answer=text)


SUBMIT = dict(pizza_count=4, room_temp_c=22, mixing="hand", target_time=TARGET)
GOOD_SUMMARY = (
    "Los geht's am Freitag um 11:55! 610 g Mehl, 396 g Wasser mit 23 °C, 17 g Salz und 1,9 g "
    "Frischhefe. Ab 14:45 für 24 h in den Kühlschrank, Samstag um 14:45 Teiglinge formen und "
    "um 19:00 backen. Standardwerte: 250 g Teiglinge, 65 % Hydration."
)


def happy_turns(summary: str = GOOD_SUMMARY, fridge_hours: float = 24) -> list[ModelTurn]:
    return [
        turn(call("submit_request", **SUBMIT)),
        turn(call("build_timeline", target_time=TARGET, phases=phase_args(fridge_hours))),
        turn(call("calculate_yeast_percentage", phases=phase_args(fridge_hours), yeast_type="fresh"),
             call("calculate_water_temperature", room_temp_c=22, mixing="hand")),
        turn(call("calculate_bakers_math", pizza_count=4, ball_weight_g=250, hydration_pct=65,
                  salt_pct=2.8, yeast_pct=0.309)),
        turn(call("finish_plan", summary=summary)),
    ]
