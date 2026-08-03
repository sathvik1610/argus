"""The five specialist reviewer agents.

All five share the exact same execution path (:class:`StructuredAgent.run`)
because running "an LLM call bound to a schema" is not a place where the
reviewers should differ — what differs between them is domain expertise,
which lives entirely in their prompts (see :mod:`argus.prompts.reviewers`)
and in their output schema (see :mod:`argus.models.review`). This module is
the registry that pairs each reviewer's prompt/schema with its state key.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from argus.agents.base import ChatModelLike, StructuredAgent
from argus.models.context import RetrievedContext
from argus.models.diff import PullRequestDiff
from argus.models.review import (
    ArchitectureReview,
    CodeQualityReview,
    PerformanceReview,
    ReviewStrategy,
    SecurityReview,
    TestingReview,
)
from argus.prompts.rendering import render_review_prompt
from argus.prompts.reviewers import (
    ARCHITECTURE_SYSTEM_PROMPT,
    PERFORMANCE_SYSTEM_PROMPT,
    QUALITY_SYSTEM_PROMPT,
    SECURITY_SYSTEM_PROMPT,
    TESTING_SYSTEM_PROMPT,
)


@dataclass(frozen=True)
class ReviewerSpec:
    key: str
    """The ReviewState field this reviewer's output is written to."""
    state_key: str
    schema: type[BaseModel]
    system_prompt: str


REVIEWER_SPECS: tuple[ReviewerSpec, ...] = (
    ReviewerSpec("security", "security_review", SecurityReview, SECURITY_SYSTEM_PROMPT),
    ReviewerSpec("performance", "performance_review", PerformanceReview, PERFORMANCE_SYSTEM_PROMPT),
    ReviewerSpec("architecture", "architecture_review", ArchitectureReview, ARCHITECTURE_SYSTEM_PROMPT),
    ReviewerSpec("quality", "quality_review", CodeQualityReview, QUALITY_SYSTEM_PROMPT),
    ReviewerSpec("testing", "testing_review", TestingReview, TESTING_SYSTEM_PROMPT),
)


def build_reviewer(spec: ReviewerSpec, chat_model: ChatModelLike) -> StructuredAgent[BaseModel]:
    return StructuredAgent(spec.key, chat_model, spec.schema, spec.system_prompt)


def run_reviewer(
    agent: StructuredAgent[BaseModel],
    diff: PullRequestDiff,
    context: RetrievedContext,
    strategy: ReviewStrategy | None,
) -> BaseModel:
    prompt = render_review_prompt(diff, context)
    if strategy is not None:
        prompt += (
            f"\n\n## Planner guidance\nEstimated depth: {strategy.estimated_review_depth}. "
            f"Focus areas flagged for this PR: {', '.join(strategy.focus_areas) or 'none specified'}."
        )
    return agent.run(prompt)
