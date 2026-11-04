import math
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, tzinfo

from fermentation_agent import config
from fermentation_agent.models import ScheduleViolation, StepKind, Timeline


def format_duration(delta: timedelta) -> str:
    """Rounded up to full minutes, e.g. '3 h 20 min'."""
    minutes = math.ceil(delta.total_seconds() / 60)
    hours, minutes = divmod(minutes, 60)
    return " ".join(part for part in (f"{hours} h" if hours else "", f"{minutes} min" if minutes else "") if part) or "0 min"


def _sleep_windows(start: datetime, end: datetime, tz: tzinfo) -> Iterator[tuple[datetime, datetime]]:
    """All sleep windows (in UTC) that could touch [start, end), built from local wall-clock times."""
    window_start, window_end = config.SLEEP_WINDOW
    day = start.astimezone(tz).date() - timedelta(days=1)
    while day <= end.astimezone(tz).date():
        end_day = day + timedelta(days=1) if window_end <= window_start else day
        yield (datetime.combine(day, window_start, tzinfo=tz).astimezone(UTC),
               datetime.combine(end_day, window_end, tzinfo=tz).astimezone(UTC))
        day += timedelta(days=1)


def check_sleep_window(timeline: Timeline) -> list[ScheduleViolation]:
    """Active steps that overlap SLEEP_WINDOW. Passive steps may run overnight.

    Steps ending at or after the bake time (preheat, bake) are tied to the time the
    user chose and are not checked – a late pizza night is the user's decision.
    """
    tz = timeline.target_time.tzinfo
    window_start, window_end = config.SLEEP_WINDOW
    violations = []
    for step in timeline.steps:
        if step.kind is not StepKind.ACTIVE or step.end >= timeline.target_time:
            continue
        start, end = step.start.astimezone(UTC), step.end.astimezone(UTC)
        for sleep_start, sleep_end in _sleep_windows(start, end, tz):
            if start < sleep_end and end > sleep_start:
                violations.append(ScheduleViolation(
                    step=step.name,
                    at=step.start,
                    rule="sleep_window",
                    message=(
                        f"'{step.name}' at {step.start.astimezone(tz):%a %H:%M} falls into the sleep "
                        f"window ({window_start:%H:%M}–{window_end:%H:%M}). It would need to move at least "
                        f"{format_duration(end - sleep_start)} earlier or {format_duration(sleep_end - start)} later."
                    ),
                ))
                break
    return violations


def _ceil_quarter_hour(dt: datetime) -> datetime:
    excess = timedelta(minutes=dt.minute % 15, seconds=dt.second, microseconds=dt.microsecond)
    return dt - excess + timedelta(minutes=15) if excess else dt


def check_feasibility(timeline: Timeline, now: datetime) -> list[ScheduleViolation]:
    """First step must start at least MIN_LEAD_TIME_MIN after now."""
    tz = timeline.target_time.tzinfo
    earliest_start = now + timedelta(minutes=config.MIN_LEAD_TIME_MIN)
    first = timeline.steps[0]
    if first.start >= earliest_start:
        return []
    missing = earliest_start - first.start
    earliest_bake = _ceil_quarter_hour((timeline.target_time + missing).astimezone(tz))
    return [ScheduleViolation(
        step=first.name,
        at=first.start,
        rule="too_soon",
        message=(
            f"The plan would have to start at {first.start.astimezone(tz):%a %H:%M}, but the earliest "
            f"possible start is {earliest_start.astimezone(tz):%a %H:%M}. Shorten the phases by at least "
            f"{format_duration(missing)}, or bake at {earliest_bake:%a %H:%M} or later."
        ),
    )]
