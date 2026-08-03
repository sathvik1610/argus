"""Planner agent: decides review depth and focus areas before any specialist runs."""

from __future__ import annotations

from argus.agents.base import ChatModelLike, StructuredAgent
from argus.models.diff import PullRequestDiff
from argus.models.review import ReviewStrategy
from argus.prompts.planning import PLANNER_SYSTEM_PROMPT
from argus.prompts.rendering import render_diff


def build_planner(chat_model: ChatModelLike) -> StructuredAgent[ReviewStrategy]:
    return StructuredAgent("planner", chat_model, ReviewStrategy, PLANNER_SYSTEM_PROMPT)


def run_planner(agent: StructuredAgent[ReviewStrategy], diff: PullRequestDiff) -> ReviewStrategy:
    return agent.run(render_diff(diff))
