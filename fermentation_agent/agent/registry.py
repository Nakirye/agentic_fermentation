"""Allowlist of tools the LLM may call: name → (Pydantic args model, function).

The dispatcher validates arguments, runs the tool and converts GuardrailError
into a structured error result the model can react to. create_calendar_events
is deliberately NOT registered; the loop calls it after user confirmation.
"""

from fermentation_agent.agent.model import ToolCall, ToolResult


def tool_schemas() -> list[dict]:
    """JSON schemas for the model, generated from the Pydantic argument models."""
    raise NotImplementedError


def dispatch(call: ToolCall) -> ToolResult:
    raise NotImplementedError
