from conftest import GOOD_SUMMARY, NOW, SUBMIT, TARGET, call, happy_turns, phase_args
from fermentation_agent import config
from fermentation_agent.agent.model import ToolCall
from fermentation_agent.agent.session import AgentSession


def run(session: AgentSession, *calls):
    return [session.dispatch(c).result for c in calls]


def planned_session() -> AgentSession:
    session = AgentSession(now=NOW)
    for model_turn in happy_turns()[:-1]:
        run(session, *model_turn.calls)
    return session


def test_unknown_tool_is_refused():
    session = AgentSession(now=NOW)
    [result] = run(session, call("create_calendar_events", path="/etc/passwd"))
    assert result["error"] == "unknown_tool"
    assert session.trace[0]["ok"] is False


def test_invalid_json_and_schema_errors():
    session = AgentSession(now=NOW)
    bad_json = session.dispatch(ToolCall("submit_request", "{not json", "c1")).result
    assert bad_json["error"] == "invalid_arguments"
    [missing] = run(session, call("submit_request", pizza_count=4))
    assert missing["error"] == "invalid_arguments"
    assert "mixing" in missing["message"]


def test_tools_need_a_request_first():
    [result] = run(AgentSession(now=NOW), call("calculate_yeast_percentage", phases=phase_args(), yeast_type="fresh"))
    assert result["error"] == "missing_request"


def test_submit_reports_defaults():
    session = AgentSession(now=NOW)
    [result] = run(session, call("submit_request", **SUBMIT))
    assert "hydration_pct" in result["defaults_used"]
    assert "mixing" not in result["defaults_used"]
    assert session.request.pizza_count == 4


def test_submit_runs_input_guardrail():
    session = AgentSession(now=NOW)
    [result] = run(session, call("submit_request", **SUBMIT, hydration_pct=95))
    assert result["error"] == "hydration_out_of_range"
    assert session.request is None


def test_schedule_violations_count_until_budget_exhausted():
    session = AgentSession(now=NOW)
    run(session, call("submit_request", **SUBMIT))
    night = call("build_timeline", target_time=TARGET, phases=phase_args(33.75))
    results = run(session, *[night] * (config.MAX_SCHEDULE_RETRIES + 1))
    assert [r["error"] for r in results] == ["schedule_violation"] * 3 + ["retry_budget_exhausted"]
    assert "Attempts left: 2" in results[0]["hint"]
    assert "03:30" in results[0]["message"]
    assert session.timeline is None


def test_finish_requires_consistent_plan():
    session = planned_session()
    run(session, call("calculate_yeast_percentage", phases=phase_args(48), yeast_type="fresh"))
    [result] = run(session, call("finish_plan", summary=GOOD_SUMMARY))
    assert result["error"] == "inconsistent_plan"
    assert "different phases" in result["message"]
    assert "different yeast percentage" in result["message"]
    assert not session.finished


def test_finish_without_anything():
    [result] = run(AgentSession(now=NOW), call("finish_plan", summary="Fertig!"))
    assert result["error"] == "inconsistent_plan"


def test_summary_mismatch_then_template_fallback():
    session = planned_session()
    wrong = "Nimm 600 g Mehl und 3 g Hefe, Start um 12:15."
    first, second = run(session, call("finish_plan", summary=wrong), call("finish_plan", summary=wrong))
    assert first["error"] == "summary_mismatch"
    assert "600 g" in first["message"] and "12:15" in first["message"]
    assert second == {"status": "accepted_with_template"}
    assert session.summary_replaced and session.summary.startswith("Plan for 4 pizzas")


def test_discarded_attempts_are_not_facts():
    session = AgentSession(now=NOW)
    run(session, call("submit_request", **SUBMIT), call("build_timeline", target_time=TARGET, phases=phase_args(33.75)))
    for model_turn in happy_turns()[1:-1]:
        run(session, *model_turn.calls)
    [result] = run(session, call("finish_plan", summary=GOOD_SUMMARY + " Fast wäre es 33.75 h geworden."))
    assert result["error"] == "summary_mismatch"


def test_good_summary_accepted():
    session = planned_session()
    [result] = run(session, call("finish_plan", summary=GOOD_SUMMARY))
    assert result == {"status": "accepted"}
    assert session.finished and session.summary == GOOD_SUMMARY
