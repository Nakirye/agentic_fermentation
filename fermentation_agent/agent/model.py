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
    def respond(self, user_text: str, results: tuple[ToolResult, ...]) -> ModelTurn: ...


@dataclass
class FakeModelClient:
    """Replays scripted turns. Used in tests and for a reproducible demo without an API key."""

    turns: list[ModelTurn]
    received: list[tuple[ToolResult, ...]] = field(default_factory=list)

    def respond(self, user_text: str, results: tuple[ToolResult, ...]) -> ModelTurn:
        self.received.append(results)
        return self.turns.pop(0)
