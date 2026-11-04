from datetime import datetime

from fermentation_agent.guardrails.schedule import check_feasibility, check_sleep_window
from fermentation_agent.models import ScheduleValidation, Timeline


def validate_schedule(timeline: Timeline, now: datetime) -> ScheduleValidation:
    """Tool wrapper around the schedule guardrails, so the LLM can check a draft itself."""
    violations = check_feasibility(timeline, now) + check_sleep_window(timeline)
    return ScheduleValidation(ok=not violations, violations=violations)
