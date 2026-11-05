"""OpenAI Responses API adapter (optional dependency `llm`). One instance per conversation."""

import json
from copy import deepcopy

from fermentation_agent.agent.model import ModelTurn, ToolCall, ToolResult


class OpenAIModelClient:
    def __init__(self, sdk_client: object, model_name: str, instructions: str, tools: list[dict],
                 max_output_tokens: int = 2000) -> None:
        if not model_name.strip():
            raise ValueError("A model name is required")
        self.model_name = model_name
        self._sdk = sdk_client
        self._instructions = instructions
        self._tools = deepcopy(tools)
        self._max_output_tokens = max_output_tokens
        self._history: list[dict] = []
        self._pending_ids: tuple[str, ...] = ()
        self.last_usage: dict[str, int] | None = None

    def respond(self, user_message: str | None, results: tuple[ToolResult, ...]) -> ModelTurn:
        if self._pending_ids:
            if user_message is not None:
                raise ValueError("Answer the pending tool calls before sending a new message")
            if tuple(result.call_id for result in results) != self._pending_ids:
                raise ValueError("Tool results must match pending call IDs")
        else:
            if results:
                raise ValueError("No tool calls are pending")
            if not user_message:
                raise ValueError("A user message is required")
        if user_message is not None:
            self._history.append({"role": "user", "content": user_message})
        for result in results:
            self._history.append({
                "type": "function_call_output",
                "call_id": result.call_id,
                "output": json.dumps(result.result, allow_nan=False, ensure_ascii=False),
            })

        response = self._sdk.responses.create(
            model=self.model_name,
            instructions=self._instructions,
            input=deepcopy(self._history),
            tools=deepcopy(self._tools),
            max_output_tokens=self._max_output_tokens,
            store=False,
            include=["reasoning.encrypted_content"],
        )
        if response.status != "completed":
            raise ValueError("Model response did not complete")
        calls = []
        for item in response.output:
            if item.type == "function_call":
                if not all(isinstance(value, str) for value in (item.name, item.arguments, item.call_id)):
                    raise ValueError("Invalid tool call fields")
                calls.append(ToolCall(item.name, item.arguments, item.call_id))
            elif item.type not in {"message", "reasoning"}:
                raise ValueError("Unsupported model output item")
            # Replay output in memory, including reasoning items required by reasoning models.
            self._history.append(item.model_dump(exclude_none=True))
        self._pending_ids = tuple(call.call_id for call in calls)
        usage = response.usage
        self.last_usage = None if usage is None else {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
        }
        return ModelTurn(calls=tuple(calls), answer=response.output_text)


OPENAI_BASE_URL = "https://api.openai.com/v1"


def create_openai_client(api_key: str, model_name: str, instructions: str, tools: list[dict],
                         base_url: str = OPENAI_BASE_URL) -> OpenAIModelClient:
    """Construct lazily so offline mode and tests do not need the SDK.

    `base_url` can point to any server with an OpenAI-compatible Responses API, e.g. Ollama
    (`http://localhost:11434/v1`). Local models load and generate slower, hence the longer timeout.
    """
    from openai import OpenAI

    timeout = 30.0 if base_url == OPENAI_BASE_URL else 300.0
    sdk = OpenAI(api_key=api_key, timeout=timeout, max_retries=2, base_url=base_url)
    return OpenAIModelClient(sdk, model_name, instructions, tools)
