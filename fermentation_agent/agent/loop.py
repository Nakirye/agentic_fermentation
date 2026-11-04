"""Agent loop: model ↔ tools, bounded by MAX_AGENT_TURNS and MAX_SCHEDULE_RETRIES."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from fermentation_agent.agent.model import ModelClient
from fermentation_agent.models import Ingredients, Timeline


@dataclass
class AgentResult:
    summary: str
    ingredients: Ingredients | None = None
    timeline: Timeline | None = None
    trace: list[dict] = field(default_factory=list)  # every tool call + result, for the demo


def run_agent(
    user_text: str,
    client: ModelClient,
    now: datetime,
    confirm: Callable[[Timeline], bool],
) -> AgentResult:
    raise NotImplementedError
