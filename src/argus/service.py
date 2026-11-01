"""Runs a review. Used by the command line, the API and the evaluation."""

from __future__ import annotations

from typing import Any

from langchain_core.embeddings import Embeddings

from argus.config import Settings
from argus.git_diff import Repo
from argus.graph import build_graph
from argus.llm import get_chat_model
from argus.models import Report


def review_repo(
    repo_path: str,
    base: str,
    head: str = "HEAD",
    *,
    rag: bool = True,
    settings: Settings | None = None,
    model: Any = None,
    embeddings: Embeddings | None = None,
) -> Report:
    """Review the diff between `base` and `head`. `model`/`embeddings` can be passed
    in (tests do this); otherwise they are built from the settings."""
    settings = settings or Settings()
    # Check the repository and refs first, so a typo is reported before any key problem.
    repo = Repo(repo_path)
    repo.resolve(base)
    repo.resolve(head)

    graph = build_graph(model or get_chat_model(settings), settings, embeddings)
    state = graph.invoke({"repo_path": repo_path, "base": base, "head": head, "rag": rag})
    report: Report = state["report"]
    return report
