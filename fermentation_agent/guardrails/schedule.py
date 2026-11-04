from datetime import datetime

from fermentation_agent.models import ScheduleViolation, Timeline


def check_sleep_window(timeline: Timeline) -> list[ScheduleViolation]:
    """Active steps whose start or end falls in SLEEP_WINDOW. Passive steps may run overnight."""
    raise NotImplementedError


def check_feasibility(timeline: Timeline, now: datetime) -> list[ScheduleViolation]:
    """First step must start at least MIN_LEAD_TIME_MIN after now."""
    raise NotImplementedError
