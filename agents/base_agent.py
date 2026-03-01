"""Base agent: wraps Anthropic API with structured output, logging, and retry."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional, Type, TypeVar

import anthropic
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class AgentError(Exception):
    """Raised when an agent cannot produce a valid response."""


class BaseAgent:
    """
    Foundation for all specialized agents.

    Each subclass defines:
    - name: identifier for audit logs
    - system_prompt: instructions that define the agent's role
    """

    name: str = "base_agent"
    system_prompt: str = ""

    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _call(
        self,
        user_message: str,
        *,
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> str:
        """Make a raw API call and return the text response."""
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=self.system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text

    def _call_structured(
        self,
        user_message: str,
        schema: Type[T],
        *,
        max_tokens: int = 2048,
    ) -> T:
        """
        Call the model and parse the JSON response into a Pydantic schema.
        Automatically instructs the model to return valid JSON.
        """
        prompt = (
            f"{user_message}\n\n"
            f"Respond with a single valid JSON object matching this schema:\n"
            f"{json.dumps(schema.model_json_schema(), indent=2)}\n"
            f"Do not include markdown fences or explanatory text — JSON only."
        )
        raw = self._call(prompt, max_tokens=max_tokens)
        raw = raw.strip()
        # Strip markdown fences if model adds them despite instructions
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0].strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error(f"[{self.name}] JSON parse error: {exc}\nRaw: {raw[:500]}")
            raise AgentError(f"Agent {self.name} returned invalid JSON") from exc

        try:
            return schema.model_validate(data)
        except Exception as exc:
            logger.error(f"[{self.name}] Schema validation error: {exc}\nData: {data}")
            raise AgentError(f"Agent {self.name} schema validation failed") from exc

    def run(self, *args: Any, **kwargs: Any) -> Any:
        """Override in each subclass to define the agent's main task."""
        raise NotImplementedError
