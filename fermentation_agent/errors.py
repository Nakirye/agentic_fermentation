"""Guardrail failures. The dispatcher returns these to the LLM as structured tool errors."""


class GuardrailError(ValueError):
    def __init__(self, rule: str, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.rule = rule
        self.hint = hint  # what the LLM could change to fix it

    def to_dict(self) -> dict:
        return {"error": self.rule, "message": str(self), "hint": self.hint}
