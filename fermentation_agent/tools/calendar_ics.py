"""Minimal RFC 5545 writer. Times are written in UTC, so no VTIMEZONE block is needed."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from fermentation_agent.models import StepKind, Timeline, TimelineStep

PRODID = "-//fermentation-agent//Fermentation Planner//EN"
ALARM_MINUTES_BEFORE = 10
MAX_LINE_OCTETS = 75


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    """Split a content line into ≤ 75-octet pieces without breaking UTF-8 characters."""
    pieces, current = [], ""
    for char in line:
        if len((current + char).encode()) > MAX_LINE_OCTETS:
            pieces.append(current)
            current = " " + char
        else:
            current += char
    pieces.append(current)
    return pieces


def _utc(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _uid(timeline: Timeline, step: TimelineStep) -> str:
    key = f"{timeline.target_time.isoformat()}|{step.name}"
    return f"{hashlib.sha1(key.encode()).hexdigest()[:16]}@fermentation-agent"


def to_ics(timeline: Timeline, notes: str | None = None, dtstamp: datetime | None = None) -> str:
    """Render the timeline as an iCalendar string. `notes` (e.g. ingredients) go into the first event."""
    stamp = _utc(dtstamp or datetime.now(UTC))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    for i, step in enumerate(timeline.steps):
        description = step.description
        if i == 0 and notes:
            description = f"{description}\n\n{notes}" if description else notes
        lines += [
            "BEGIN:VEVENT",
            f"UID:{_uid(timeline, step)}",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{_utc(step.start)}",
            f"DTEND:{_utc(step.end)}",
            f"SUMMARY:{_escape('Pizza: ' + step.name)}",
            f"DESCRIPTION:{_escape(description)}",
            # Resting dough should not block the calendar; active steps should.
            f"TRANSP:{'OPAQUE' if step.kind is StepKind.ACTIVE else 'TRANSPARENT'}",
        ]
        if step.kind is StepKind.ACTIVE:
            lines += [
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                f"TRIGGER:-PT{ALARM_MINUTES_BEFORE}M",
                f"DESCRIPTION:{_escape(step.name)}",
                "END:VALARM",
            ]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "".join(piece + "\r\n" for line in lines for piece in _fold(line))


def create_calendar_events(timeline: Timeline, output_path: Path, notes: str | None = None) -> Path:
    """Write one VEVENT per timeline step to an .ics file.

    Stable UIDs derived from target_time + step name, so re-imports replace instead of duplicate.
    Only called by the agent loop after the user confirmed — never directly by the LLM.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(to_ics(timeline, notes).encode())
    return output_path
