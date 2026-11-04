from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fermentation_agent.models import FermentationPhase, StepKind
from fermentation_agent.tools.calendar_ics import create_calendar_events, to_ics
from fermentation_agent.tools.timeline import build_timeline

SAT_19 = datetime(2026, 11, 7, 19, tzinfo=ZoneInfo("Europe/Vienna"))
PHASES = [
    FermentationPhase(name="bulk", temp_c=22, hours=2),
    FermentationPhase(name="cold retard", temp_c=4, hours=24),
    FermentationPhase(name="final proof", temp_c=22, hours=4),
]


def unfold(ics: str) -> list[str]:
    return ics.replace("\r\n ", "").split("\r\n")


def parse_events(ics: str) -> list[dict[str, str]]:
    """Tiny parser: top-level VEVENT properties only (VALARM contents are skipped)."""
    events, current, depth = [], None, 0
    for line in unfold(ics):
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT":
            events.append(current)
            current = None
        elif line == "BEGIN:VALARM":
            depth += 1
            current["HAS_ALARM"] = "1"
        elif line == "END:VALARM":
            depth -= 1
        elif current is not None and depth == 0 and ":" in line:
            key, value = line.split(":", 1)
            current[key] = value
    return events


def make_timeline():
    return build_timeline(SAT_19, PHASES)


def test_one_event_per_step():
    timeline = make_timeline()
    events = parse_events(to_ics(timeline))
    assert len(events) == len(timeline.steps)
    assert events[-1]["SUMMARY"] == "Pizza: Bake"
    assert events[-1]["DTSTART"] == "20261107T180000Z"  # 19:00 Vienna = 18:00 UTC


def test_calendar_envelope_and_crlf():
    ics = to_ics(make_timeline())
    assert ics.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n")
    assert ics.endswith("END:VCALENDAR\r\n")
    assert "\n" not in ics.replace("\r\n", "")


def test_uids_stable_across_runs():
    first = [e["UID"] for e in parse_events(to_ics(make_timeline(), dtstamp=datetime(2026, 1, 1, tzinfo=UTC)))]
    second = [e["UID"] for e in parse_events(to_ics(make_timeline(), dtstamp=datetime(2026, 6, 1, tzinfo=UTC)))]
    assert first == second
    assert len(set(first)) == len(first)


def test_alarms_and_transparency_follow_step_kind():
    timeline = make_timeline()
    for step, event in zip(timeline.steps, parse_events(to_ics(timeline))):
        active = step.kind is StepKind.ACTIVE
        assert ("HAS_ALARM" in event) == active
        assert event["TRANSP"] == ("OPAQUE" if active else "TRANSPARENT")


def test_lines_folded_to_75_octets():
    notes = "Ingredients: " + "Mehl, Wasser, Salz; Hefe – ünd Ümlaute. " * 10
    ics = to_ics(make_timeline(), notes=notes)
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))


def test_notes_escaped_in_first_event():
    events = parse_events(to_ics(make_timeline(), notes="Flour 610 g, water 397 g;\nsalt 17 g"))
    assert events[0]["DESCRIPTION"].endswith(r"Flour 610 g\, water 397 g\;\nsalt 17 g")
    assert "Flour" not in events[1]["DESCRIPTION"]


def test_writes_file(tmp_path):
    path = create_calendar_events(make_timeline(), tmp_path / "sub" / "plan.ics")
    assert path.exists()
    assert path.read_bytes().startswith(b"BEGIN:VCALENDAR\r\n")
