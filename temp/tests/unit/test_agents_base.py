from __future__ import annotations

import pytest
from pydantic import BaseModel

from argus.agents.base import AgentExecutionError, StructuredAgent
from tests.fakes import FakeStructuredChatModel


class _DummySchema(BaseModel):
    value: str


class _OtherSchema(BaseModel):
    other: int = 0


def test_structured_agent_returns_parsed_schema() -> None:
    model = FakeStructuredChatModel({_DummySchema: _DummySchema(value="ok")})
    agent = StructuredAgent("dummy", model, _DummySchema, "system prompt")
    result = agent.run("do the thing")
    assert isinstance(result, _DummySchema)
    assert result.value == "ok"


def test_structured_agent_raises_on_schema_mismatch() -> None:
    # Registers a response of the WRONG schema type to simulate a model that
    # fails to honor structured output — the agent must not silently pass
    # through a malformed result.
    model = FakeStructuredChatModel({_DummySchema: _OtherSchema(other=1)})
    agent = StructuredAgent("dummy", model, _DummySchema, "system prompt")
    with pytest.raises(AgentExecutionError):
        agent.run("do the thing")


def test_structured_agent_raises_when_no_response_registered() -> None:
    model = FakeStructuredChatModel({})
    agent = StructuredAgent("dummy", model, _DummySchema, "system prompt")
    with pytest.raises(AgentExecutionError):
        agent.run("do the thing")
