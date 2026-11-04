from datetime import datetime

from fermentation_agent.models import DoughRequest


def validate_request(request: DoughRequest, now: datetime) -> None:
    """Plausibility: ranges from config, hydration per flour type, target_time in the future."""
    raise NotImplementedError
