"""Fake LLM and fake embeddings so tests never need an API key or network."""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from argus.models import AgentOutput, Category, Finding


class FakeChatModel:
    """Looks like a chat model to Argus. `respond` gets the system prompt and
    user prompt and returns the AgentOutput the 'LLM' should produce."""

    def __init__(self, respond: Callable[[str, str], AgentOutput], tokens: int = 10) -> None:
        self.respond = respond
        self.tokens = tokens
        self.calls: list[tuple[str, str]] = []  # (system, user) of every call

    def with_structured_output(self, schema: Any, include_raw: bool = False) -> Any:
        def _call(messages: list[Any]) -> dict[str, Any]:
            system, user = messages[0].content, messages[1].content
            self.calls.append((system, user))
            parsed = self.respond(system, user)
            raw = AIMessage(
                content="",
                usage_metadata={
                    "input_tokens": self.tokens,
                    "output_tokens": 0,
                    "total_tokens": self.tokens,
                },
            )
            return {"raw": raw, "parsed": parsed, "parsing_error": None}

        return RunnableLambda(_call)


def category_of(system_prompt: str) -> Category:
    for category in Category:
        if f"the {category.value} reviewer" in system_prompt:
            return category
    raise AssertionError("unknown reviewer in system prompt")


def by_category(findings: dict[Category, list[Finding]]) -> Callable[[str, str], AgentOutput]:
    """Return a responder that gives each reviewer its own canned findings."""

    def respond(system: str, user: str) -> AgentOutput:
        return AgentOutput(findings=findings.get(category_of(system), []))

    return respond


class FakeEmbeddings:
    """Hashes words into a small vector, so texts that share words are close.
    Good enough to test retrieval deterministically without a real model."""

    DIM = 64

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.DIM
        for word in re.findall(r"[a-z_]{3,}", text.lower()):
            vec[sum(ord(c) for c in word) % self.DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)
