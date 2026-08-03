"""Shared test doubles.

A minimal fake chat model whose ``with_structured_output`` returns a runnable
that ignores its input and returns a pre-registered instance of whichever
schema was requested. This lets tests exercise real LangGraph wiring and real
agent code paths — including the parallel reviewer fan-out, where call order
across branches is not guaranteed — without a network call or an API key.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel

#: Either a single instance (returned on every call) or a list consumed in
#: order (useful for schemas invoked more than once, e.g. RiskAssessment
#: across context-expansion loop iterations).
FakeResponse = BaseModel | list[BaseModel]


class FakeStructuredChatModel:
    """Drop-in stand-in for a LangChain ``BaseChatModel`` in tests."""

    def __init__(self, responses: dict[type[BaseModel], FakeResponse]):
        self._responses: dict[type[BaseModel], FakeResponse] = {
            schema: (list(value) if isinstance(value, list) else value)
            for schema, value in responses.items()
        }

    def with_structured_output(self, schema: type[BaseModel]) -> Runnable[Any, BaseModel]:
        def _respond(_messages: Any) -> BaseModel:
            value = self._responses.get(schema)
            if value is None:
                raise AssertionError(
                    f"FakeStructuredChatModel has no response registered for {schema}"
                )
            if isinstance(value, list):
                if not value:
                    raise AssertionError(
                        f"FakeStructuredChatModel exhausted responses for {schema}"
                    )
                return value.pop(0)
            return value

        return RunnableLambda(_respond)
