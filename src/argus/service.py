"""Runs a review. Used by the command line, the API and the evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from argus.agents import run_reviewer
from argus.config import Settings
from argus.git_diff import Repo
from argus.llm import get_chat_model
from argus.models import Category, Finding


@dataclass
class ReviewResult:
    findings: list[Finding]
    tokens: int


def review_repo(
    repo_path: str,
    base: str,
    head: str = "HEAD",
    *,
    settings: Settings | None = None,
    model: Any = None,
) -> ReviewResult:
    settings = settings or Settings()
    diff = Repo(repo_path).diff(base, head)
    if not diff.files:
        return ReviewResult([], 0)
    model = model or get_chat_model(settings)
    diff_text = diff.render(settings.max_diff_chars)

    findings: list[Finding] = []
    tokens = 0
    for category in Category:
        result = run_reviewer(model, category, diff_text, None)
        findings.extend(result.findings)
        tokens += result.tokens
    return ReviewResult(findings, tokens)
