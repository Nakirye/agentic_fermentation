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
