"""OpenAI Responses API adapter (optional dependency `llm`)."""

from fermentation_agent.agent.model import ModelTurn, ToolResult


class OpenAIModelClient:
    def __init__(self, sdk_client: object, model_name: str) -> None:
        self.model_name = model_name
        self._sdk = sdk_client
        self._history: list[dict] = []

    def respond(self, user_text: str, results: tuple[ToolResult, ...]) -> ModelTurn:
        raise NotImplementedError


def create_openai_client(api_key: str, model_name: str) -> OpenAIModelClient:
    from openai import OpenAI

    return OpenAIModelClient(OpenAI(api_key=api_key, timeout=30.0, max_retries=0), model_name)
