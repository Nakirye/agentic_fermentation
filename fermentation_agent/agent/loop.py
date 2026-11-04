"""Agent loop: model ↔ tools, bounded by MAX_AGENT_TURNS per user message.

The calendar export is the only side effect. It is not a tool; it runs here, after
finish_plan was accepted and the user confirmed the plan.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from fermentation_agent import config
from fermentation_agent.agent.model import ModelClient, ToolResult
from fermentation_agent.agent.session import AgentSession
from fermentation_agent.agent.summary import ingredient_lines
from fermentation_agent.errors import GuardrailError
from fermentation_agent.guardrails.input import check_user_text
from fermentation_agent.models import DoughRequest, Ingredients, Timeline, WaterTempResult, YeastResult
from fermentation_agent.tools.calendar_ics import create_calendar_events

Status = Literal["planned", "answered", "rejected", "failed"]


@dataclass
class AgentResult:
    status: Status  # planned: plan accepted · answered: question/refusal · rejected: input guardrail
    message: str  # summary, question to the user, or error explanation
    request: DoughRequest | None = None
    ingredients: Ingredients | None = None
    yeast: YeastResult | None = None
    water: WaterTempResult | None = None
    timeline: Timeline | None = None
    summary_replaced: bool = False
    ics_path: Path | None = None
    trace: list[dict] = field(default_factory=list)  # every tool call + result, for the demo


def result_from_session(session: AgentSession, status: Status, message: str) -> AgentResult:
    return AgentResult(
        status=status, message=message, request=session.request, ingredients=session.ingredients,
        yeast=session.yeast, water=session.water, timeline=session.timeline,
        summary_replaced=session.summary_replaced, trace=session.trace,
    )


def export_if_confirmed(result: AgentResult, session: AgentSession,
                        confirm: Callable[[AgentResult], bool], output_path: Path) -> AgentResult:
    if confirm(result):
        notes = "Ingredients:\n" + "\n".join(ingredient_lines(session))
        result.ics_path = create_calendar_events(session.timeline, output_path, notes=notes)
    return result


class FermentationAgent:
    """One conversation that ends with one plan. send() may be called again after a question."""

    def __init__(self, client: ModelClient, now: datetime, confirm: Callable[[AgentResult], bool],
                 output_path: Path = Path("out/plan.ics")) -> None:
        self.client = client
        self.session = AgentSession(now=now)
        self.confirm = confirm
        self.output_path = output_path

    def send(self, user_text: str) -> AgentResult:
        if self.session.finished:
            raise RuntimeError("This conversation already produced a plan; start a new agent")
        try:
            message: str | None = check_user_text(user_text)
        except GuardrailError as error:
            return result_from_session(self.session, "rejected", f"{error} {error.hint}")

        results: tuple[ToolResult, ...] = ()
        for _ in range(config.MAX_AGENT_TURNS):
            turn = self.client.respond(message, results)
            message = None
            if not turn.calls:
                status: Status = "failed" if self.session.schedule_budget_exhausted else "answered"
                return result_from_session(self.session, status, turn.answer)
            results = tuple(self.session.dispatch(call) for call in turn.calls)
            if self.session.finished:
                result = result_from_session(self.session, "planned", self.session.summary)
                return export_if_confirmed(result, self.session, self.confirm, self.output_path)
        return result_from_session(
            self.session, "failed", f"Stopped after {config.MAX_AGENT_TURNS} model turns without a finished plan.")
