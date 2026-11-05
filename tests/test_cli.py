import sys

import pytest

import cli

OFFLINE = ["--offline", "--pizzas", "4", "--room-temp", "22", "--mixing", "hand",
           "--target", "2026-11-07T19:00", "--now", "2026-11-05T18:00"]


def run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["cli.py", *argv])
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    return exit_info.value.code


def test_offline_plan_writes_calendar(monkeypatch, capsys, tmp_path):
    output = tmp_path / "plan.ics"
    assert run(monkeypatch, *OFFLINE, "-y", "--trace", "-o", str(output)) == 0
    printed = capsys.readouterr().out
    assert "✓ finish_plan" in printed
    assert "Flour (tipo_00): 610 g" in printed
    assert printed.count("Flour (tipo_00)") == 1  # plan printed once
    assert output.exists()


def test_offline_without_yes_and_without_terminal_writes_nothing(monkeypatch, capsys, tmp_path):
    output = tmp_path / "plan.ics"
    assert run(monkeypatch, *OFFLINE, "-o", str(output)) == 0
    assert "No calendar file written." in capsys.readouterr().out
    assert not output.exists()


def test_offline_guardrail_exit_code(monkeypatch, capsys):
    assert run(monkeypatch, *OFFLINE, "--hydration", "95") == 1
    assert "batter" in capsys.readouterr().out


def test_offline_requires_flags(monkeypatch):
    assert "--mixing" in run(monkeypatch, "--offline", "--pizzas", "4")


def test_llm_mode_requires_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    assert "OPENAI_API_KEY" in run(monkeypatch, "4 Pizzen")


class StopBeforeNetwork(Exception):
    pass


def capture_client(monkeypatch, env):
    """Run LLM mode up to client creation and return the factory arguments."""
    for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "FERMENTATION_MODEL"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    captured = {}

    def fake_factory(api_key, model, instructions, tools, base_url):
        captured.update(api_key=api_key, model=model, base_url=base_url)
        raise StopBeforeNetwork

    monkeypatch.setattr("fermentation_agent.agent.openai_client.create_openai_client", fake_factory)
    return captured


def test_llm_mode_local_server_needs_no_key(monkeypatch):
    captured = capture_client(monkeypatch, {"OPENAI_BASE_URL": "http://localhost:11434/v1",
                                            "FERMENTATION_MODEL": "llama3.2:3b"})
    monkeypatch.setattr(sys, "argv", ["cli.py", "4 Pizzen"])
    with pytest.raises(StopBeforeNetwork):
        cli.main()
    assert captured == {"api_key": "local", "model": "llama3.2:3b", "base_url": "http://localhost:11434/v1"}


def test_llm_mode_flags_override_env(monkeypatch):
    captured = capture_client(monkeypatch, {"OPENAI_API_KEY": "test-only-key", "FERMENTATION_MODEL": "from-env"})
    monkeypatch.setattr(sys, "argv", ["cli.py", "--model", "qwen3:14b", "--base-url", "http://gpu:11434/v1", "4 Pizzen"])
    with pytest.raises(StopBeforeNetwork):
        cli.main()
    assert captured == {"api_key": "test-only-key", "model": "qwen3:14b", "base_url": "http://gpu:11434/v1"}
