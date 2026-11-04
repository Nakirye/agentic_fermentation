def check_summary_numbers(summary: str, facts: dict[str, float], tolerance: float = 0.5) -> list[str]:
    """Every number in the LLM summary that looks like a quantity must match a tool fact.

    Returns the numbers that do not match (empty list = summary is consistent).
    """
    raise NotImplementedError
