"""Provider-independent model interface. Real adapters and the fake client implement it."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: str  # raw JSON from the model, validated by the dispatcher
    call_id: str


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    result: dict


@dataclass(frozen=True)
class ModelTurn:
    calls: tuple[ToolCall, ...] = ()
    answer: str = ""


class ModelClient(Protocol):
    """One client per conversation; implementations keep the provider history.

    Either a new user message (start, or the user's reply to a question) or the
    results of the pending tool calls cross this boundary – never both.
    """

    def respond(self, user_message: str | None, results: tuple[ToolResult, ...]) -> ModelTurn: ...


@dataclass
class FakeModelClient:
    """Replays scripted turns. Used in tests and for a reproducible demo without an API key."""

    turns: list[ModelTurn]
    received: list[tuple[str | None, tuple[ToolResult, ...]]] = field(default_factory=list)

    def respond(self, user_message: str | None, results: tuple[ToolResult, ...]) -> ModelTurn:
        self.received.append((user_message, results))
        if not self.turns:
            raise AssertionError("FakeModelClient ran out of scripted turns")
        return self.turns.pop(0)
