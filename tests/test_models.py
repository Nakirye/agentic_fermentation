from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from fermentation_agent.models import DoughRequest, FermentationPhase, Mixing


VIENNA_SAT_19 = datetime(2026, 11, 7, 19, tzinfo=ZoneInfo("Europe/Vienna"))


def test_request_defaults():
    req = DoughRequest(
        pizza_count=4,
        room_temp_c=22,
        mixing=Mixing.HAND,
        target_time=VIENNA_SAT_19,
    )
    assert req.hydration_pct == 65.0
    assert req.fridge_temp_c == 4.0


def test_request_requires_timezone():
    with pytest.raises(ValidationError):
        DoughRequest(pizza_count=4, room_temp_c=22, mixing=Mixing.HAND, target_time=datetime(2026, 11, 7, 19))


def test_phase_hours_positive():
    with pytest.raises(ValidationError):
        FermentationPhase(name="bulk", temp_c=22, hours=0)


def test_request_requires_mixing_method():
    with pytest.raises(ValidationError, match="mixing"):
        DoughRequest(pizza_count=4, room_temp_c=22, target_time=VIENNA_SAT_19)
