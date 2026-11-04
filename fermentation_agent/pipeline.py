"""Offline mode: the same tools in a fixed order, without an LLM. Baseline for tests and demo."""

from datetime import datetime

from fermentation_agent.agent.loop import AgentResult
from fermentation_agent.models import DoughRequest


def plan_offline(request: DoughRequest, now: datetime) -> AgentResult:
    raise NotImplementedError
