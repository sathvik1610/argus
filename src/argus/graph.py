"""The LangGraph workflow.

    START -> load_diff -> retrieve -> security    \\
                                   -> correctness  -> merge -> END
                                   -> performance /

The three reviewers do not depend on each other, so they run in parallel (fan-out)
and `merge` waits until all three have finished (fan-in).
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.embeddings import Embeddings
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from argus.agents import run_reviewer
from argus.config import Settings
from argus.git_diff import Diff, Repo
from argus.index import RepoIndex
from argus.merge import build_report
from argus.models import Category, Finding, Report, Snippet
from argus.retrieval import retrieve


class ReviewState(TypedDict, total=False):
    # inputs
    repo_path: str
    base: str
    head: str
    rag: bool
    # filled in by the nodes
    diff: Diff
    snippets: list[Snippet] | None  # None = RAG off
    security: list[Finding]
    correctness: list[Finding]
    performance: list[Finding]
    # Three nodes add to this at the same time, so it needs a "reducer" that says how
    # to combine their values. Without it LangGraph would refuse concurrent writes.
    tokens: Annotated[int, operator.add]
    report: Report


def build_graph(
    model: Any, settings: Settings, embeddings: Embeddings | None = None
) -> CompiledStateGraph[ReviewState]:
    """`model` is a chat model; `embeddings` is only needed when RAG is on."""

    def load_diff(state: ReviewState) -> dict[str, Any]:
        return {"diff": Repo(state["repo_path"]).diff(state["base"], state["head"])}

    def retrieve_context(state: ReviewState) -> dict[str, Any]:
        diff = state["diff"]
        if not state["rag"] or not diff.files:
            return {"snippets": None}
        from argus.llm import get_embeddings  # imported here so no-RAG runs need no embeddings

        repo = Repo(state["repo_path"])
        index = RepoIndex.build(
            repo, state["head"], settings, embeddings or get_embeddings(settings)
        )
        return {"snippets": retrieve(diff, index, settings.top_k)}

    def make_reviewer(category: Category) -> Any:
        def review(state: ReviewState) -> dict[str, Any]:
            diff = state["diff"]
            if not diff.files:
                return {category.value: [], "tokens": 0}
            result = run_reviewer(
                model, category, diff.render(settings.max_diff_chars), state.get("snippets")
            )
            return {category.value: result.findings, "tokens": result.tokens}

        return review

    def merge(state: ReviewState) -> dict[str, Any]:
        findings = (
            state.get("security", []) + state.get("correctness", []) + state.get("performance", [])
        )
        return {"report": build_report(findings, state.get("snippets"), state.get("tokens", 0))}

    graph = StateGraph(ReviewState)
    graph.add_node("load_diff", load_diff)
    graph.add_node("retrieve", retrieve_context)
    graph.add_node("merge", merge)
    graph.add_edge(START, "load_diff")
    graph.add_edge("load_diff", "retrieve")
    for category in Category:
        graph.add_node(category.value, make_reviewer(category))
        graph.add_edge("retrieve", category.value)  # fan-out
    graph.add_edge([c.value for c in Category], "merge")  # fan-in: wait for all three
    graph.add_edge("merge", END)
    return graph.compile()
