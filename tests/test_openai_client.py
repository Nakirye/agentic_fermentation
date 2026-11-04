import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from fermentation_agent.agent.model import ToolResult
from fermentation_agent.agent.openai_client import OpenAIModelClient, create_openai_client
from fermentation_agent.agent.registry import tool_schemas


class Item:
    def __init__(self, **fields):
        self.__dict__.update(fields)

    def model_dump(self, **kwargs):
        return dict(self.__dict__)


class FakeSDK:
    def __init__(self, responses):
        self.turns = iter(responses)
        self.requests = []
        self.responses = self

    def create(self, **kwargs):
        self.requests.append(deepcopy(kwargs))
        return next(self.turns)


def response(*items, text="", status="completed"):
    return SimpleNamespace(output=list(items), output_text=text, status=status,
                           usage=SimpleNamespace(input_tokens=100, output_tokens=20, total_tokens=120))


def function_call(call_id="call-1", name="submit_request"):
    return Item(type="function_call", name=name, arguments="{}", call_id=call_id, id=f"fc-{call_id}")


def adapter(sdk):
    return OpenAIModelClient(sdk, "test-model", "INSTRUCTIONS", tool_schemas())


def test_history_replay_and_call_ids():
    sdk = FakeSDK([response(function_call()), response(Item(type="message", role="assistant", content=[]), text="Fertig.")])
    client = adapter(sdk)
    assert client.respond("4 Pizzen", ()).calls[0].call_id == "call-1"
    assert client.respond(None, (ToolResult("call-1", {"ok": "ü"}),)).answer == "Fertig."
    second = sdk.requests[1]
    assert second["input"][1]["type"] == "function_call"
    assert second["input"][2] == {"type": "function_call_output", "call_id": "call-1", "output": '{"ok": "ü"}'}
    assert second["instructions"] == "INSTRUCTIONS"
    assert second["store"] is False
    assert len(second["tools"]) == 6
    assert len(sdk.requests[0]["input"]) == 1  # earlier snapshot unchanged
    assert client.last_usage["total_tokens"] == 120


def test_follow_up_message_after_answer():
    sdk = FakeSDK([response(text="Von Hand oder Maschine?"), response(function_call())])
    client = adapter(sdk)
    client.respond("4 Pizzen Samstag", ())
    client.respond("Von Hand", ())
    assert [m.get("content") for m in sdk.requests[1]["input"] if m.get("role") == "user"] == ["4 Pizzen Samstag", "Von Hand"]


def test_protocol_violations_are_rejected_before_api_call():
    sdk = FakeSDK([response(function_call("expected"))])
    client = adapter(sdk)
    client.respond("Start", ())
    with pytest.raises(ValueError, match="call IDs"):
        client.respond(None, (ToolResult("wrong", {}),))
    with pytest.raises(ValueError, match="pending"):
        client.respond("Neue Nachricht", ())
    assert len(sdk.requests) == 1


def test_results_without_pending_calls_rejected():
    with pytest.raises(ValueError, match="No tool calls"):
        adapter(FakeSDK([])).respond(None, (ToolResult("x", {}),))


@pytest.mark.parametrize("status", ["incomplete", "failed", "cancelled"])
def test_incomplete_responses_are_not_used(status):
    with pytest.raises(ValueError, match="did not complete"):
        adapter(FakeSDK([response(text="...", status=status)])).respond("Start", ())


def test_unsupported_output_item():
    with pytest.raises(ValueError, match="Unsupported"):
        adapter(FakeSDK([response(Item(type="web_search_call"))])).respond("Start", ())


def test_sdk_configuration_without_network(monkeypatch):
    captured = {}
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: captured.update(kwargs) or object())
    client = create_openai_client("test-only-key", "gpt-4.1-mini", "I", [])
    assert client.model_name == "gpt-4.1-mini"
    assert captured["timeout"] == 30 and captured["base_url"] == "https://api.openai.com/v1"


def test_installed_sdk_roundtrip_with_mock_http():
    """Real SDK serialization (incl. our tool schemas) and response parsing, without network."""
    import httpx
    from openai import OpenAI

    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        output = ([{"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "submit_request",
                    "arguments": '{"pizza_count": 4}', "status": "completed"}] if len(requests) == 1 else
                  [{"type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": "Plan fertig.", "annotations": []}]}])
        return httpx.Response(200, json={
            "id": "resp_1", "object": "response", "created_at": 1, "status": "completed", "model": "test-model",
            "output": output, "parallel_tool_calls": True, "tool_choice": "auto", "tools": body["tools"],
            "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = adapter(OpenAI(api_key="test-only-key", http_client=http, max_retries=0))
        assert client.respond("4 Pizzen", ()).calls[0].arguments == '{"pizza_count": 4}'
        assert client.respond(None, (ToolResult("call_1", {"ok": True}),)).answer == "Plan fertig."
    assert requests[0]["tools"][0]["name"] == "submit_request"
    assert requests[1]["input"][-1]["call_id"] == "call_1"
