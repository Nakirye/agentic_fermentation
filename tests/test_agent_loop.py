import pytest

from conftest import GOOD_SUMMARY, NOW, SUBMIT, TARGET, answer, call, happy_turns, phase_args, turn
from fermentation_agent import config
from fermentation_agent.agent.loop import FermentationAgent
from fermentation_agent.agent.model import FakeModelClient


def agent(turns, tmp_path, confirm=lambda result: True):
    client = FakeModelClient(list(turns))
    return FermentationAgent(client, NOW, confirm, tmp_path / "plan.ics"), client


def test_happy_path_writes_calendar_after_confirmation(tmp_path):
    confirmed = []
    bot, client = agent(happy_turns(), tmp_path, confirm=lambda r: confirmed.append(r) or True)
    result = bot.send("Samstag 19:00 vier Pizzen, 22 °C, kneten von Hand")
    assert result.status == "planned"
    assert result.message == GOOD_SUMMARY
    assert result.ingredients.flour_g == 610
    assert confirmed == [result]
    assert result.ics_path.read_text().count("BEGIN:VEVENT") == len(result.timeline.steps)
    assert "Flour (tipo_00): 610 g" in result.ics_path.read_text()
    assert [t["tool"] for t in result.trace][-1] == "finish_plan"
    # Tool results go back with the matching call IDs, and the user text is sent only once.
    assert client.received[0][0].startswith("Samstag")
    assert all(message is None for message, _ in client.received[1:])


def test_no_calendar_without_confirmation(tmp_path):
    bot, _ = agent(happy_turns(), tmp_path, confirm=lambda result: False)
    result = bot.send("Samstag 19:00 vier Pizzen, 22 °C, von Hand")
    assert result.status == "planned"
    assert result.ics_path is None
    assert not (tmp_path / "plan.ics").exists()


def test_sleep_violation_is_fixed_by_the_model(tmp_path):
    turns = happy_turns()
    turns.insert(1, turn(call("build_timeline", target_time=TARGET, phases=phase_args(33.75))))
    bot, client = agent(turns, tmp_path)
    result = bot.send("Samstag 19:00, 4 Pizzen, 22 °C, von Hand")
    assert result.status == "planned"
    builds = [t for t in result.trace if t["tool"] == "build_timeline"]
    assert [b["ok"] for b in builds] == [False, True]
    [(_, error_results)] = [r for r in client.received if r[1] and "error" in r[1][0].result]
    assert error_results[0].result["error"] == "schedule_violation"


def test_retry_budget_exhausted_ends_in_failure(tmp_path):
    night = lambda: turn(call("build_timeline", target_time=TARGET, phases=phase_args(33.75)))  # noqa: E731
    turns = [turn(call("submit_request", **SUBMIT)), *[night() for _ in range(config.MAX_SCHEDULE_RETRIES + 1)],
             answer("Leider passt kein Plan in den Tag. Wie wäre es mit Sonntag?")]
    bot, _ = agent(turns, tmp_path)
    result = bot.send("Samstag 19:00, 4 Pizzen, 22 °C, von Hand")
    assert result.status == "failed"
    assert result.trace[-1]["result"]["error"] == "retry_budget_exhausted"
    assert result.ics_path is None


def test_question_then_follow_up(tmp_path):
    bot, client = agent([answer("Knetest du von Hand oder mit der Küchenmaschine?"), *happy_turns()], tmp_path)
    first = bot.send("Samstag 19:00, 4 Pizzen, 22 °C")
    assert first.status == "answered"
    assert "Hand" in first.message
    second = bot.send("Von Hand")
    assert second.status == "planned"
    assert client.received[1][0] == "Von Hand"


def test_off_topic_request_gets_no_plan(tmp_path):
    bot, _ = agent([answer("Ich kann nur Pizzateig planen.")], tmp_path)
    result = bot.send("Schreib mir ein Gedicht über Steuern")
    assert result.status == "answered"
    assert result.trace == [] and result.ics_path is None


def test_empty_input_never_reaches_the_model(tmp_path):
    bot, client = agent([], tmp_path)
    result = bot.send("   ")
    assert result.status == "rejected"
    assert client.received == []


def test_turn_limit(tmp_path):
    bot, _ = agent([turn(call("calculate_bakers_math"))] * config.MAX_AGENT_TURNS, tmp_path)
    result = bot.send("Samstag 19:00, 4 Pizzen, 22 °C, von Hand")
    assert result.status == "failed"
    assert str(config.MAX_AGENT_TURNS) in result.message
    assert len(result.trace) == config.MAX_AGENT_TURNS


def test_hallucinated_summary_is_replaced(tmp_path):
    wrong = "600 g Mehl, Start 12:15."
    turns = happy_turns(summary=wrong) + [turn(call("finish_plan", summary=wrong))]
    bot, _ = agent(turns, tmp_path)
    result = bot.send("Samstag 19:00, 4 Pizzen, 22 °C, von Hand")
    assert result.status == "planned"
    assert result.summary_replaced
    assert "610 g" in result.message and "600 g" not in result.message


def test_conversation_ends_after_plan(tmp_path):
    bot, _ = agent(happy_turns(), tmp_path)
    bot.send("Samstag 19:00, 4 Pizzen, 22 °C, von Hand")
    with pytest.raises(RuntimeError):
        bot.send("Noch eine Frage")
