from pathlib import Path

from fermentation_agent.models import Timeline


def create_calendar_events(timeline: Timeline, output_path: Path) -> Path:
    """Write one VEVENT per active step (passive phases as one event each) to an .ics file.

    Stable UIDs derived from target_time + step name, so re-imports replace instead of duplicate.
    Only called by the agent loop after the user confirmed — never directly by the LLM.
    """
    raise NotImplementedError
