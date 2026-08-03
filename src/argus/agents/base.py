"""Shared infrastructure for every LLM-backed review agent.

Each concrete agent (security, performance, architecture, quality, testing,
planner, risk, consensus) is thin: a system prompt plus a Pydantic output
schema. All of them share this base for structured-output binding, retries,
and logging, so adding a sixth reviewer is "write a prompt + a schema", not
"reimplement invocation plumbing".
"""

from __future__ import annotations

from typing import Generic, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from argus.services.logging import get_logger

logger = get_logger(__name__)

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class AgentExecutionError(RuntimeError):
    """Raised when an agent exhausts its retries without a valid structured response."""


class StructuredAgent(Generic[SchemaT]):
    """Binds a chat model to a Pydantic schema and invokes it with retries."""

    def __init__(
        self,
        name: str,
        chat_model: BaseChatModel,
        output_schema: type[SchemaT],
        system_prompt: str,
    ) -> None:
        self.name = name
        self._schema = output_schema
        self._system_prompt = system_prompt
        self._model = chat_model.with_structured_output(output_schema)

    def run(self, user_prompt: str) -> SchemaT:
        try:
            return self._invoke(user_prompt)
        except Exception as exc:  # noqa: BLE001 - surfaced as a typed error for the graph
            logger.error("agent_failed", agent=self.name, error=str(exc))
            raise AgentExecutionError(f"{self.name} failed: {exc}") from exc

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _invoke(self, user_prompt: str) -> SchemaT:
        logger.debug("agent_invoke", agent=self.name)
        messages = [SystemMessage(content=self._system_prompt), HumanMessage(content=user_prompt)]
        result = self._model.invoke(messages)
        if not isinstance(result, self._schema):
            raise AgentExecutionError(
                f"{self.name} returned {type(result)!r}, expected {self._schema!r}"
            )
        return result
