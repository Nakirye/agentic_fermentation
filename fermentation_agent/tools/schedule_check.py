from datetime import datetime

from fermentation_agent.models import ScheduleValidation, Timeline


def validate_schedule(timeline: Timeline, now: datetime) -> ScheduleValidation:
    """Tool wrapper around the schedule guardrails, so the LLM can check a draft itself."""
    raise NotImplementedError
