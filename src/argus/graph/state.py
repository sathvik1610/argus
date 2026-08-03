"""The shared state threaded through every node of the review graph.

A plain ``TypedDict`` rather than a Pydantic model, per LangGraph convention —
LangGraph's ``StateGraph`` diffs and merges partial updates key-by-key, which
is what lets five reviewer nodes run in parallel and write to the same state
object without stepping on each other: as long as two concurrently-running
nodes write to *different* keys (as our five reviewers do), no reducer is
needed. Keys that genuinely can be written by more than one node at the same
super-step (``errors``) use an ``Annotated`` reducer instead.

``import_graph`` intentionally holds a live ``networkx.DiGraph``, not a
serialized form — Argus runs the graph in-process and doesn't cross a
persistence boundary mid-run. A checkpointed/distributed deployment would need
to serialize it (e.g. node-link JSON); see Architecture.md for that tradeoff.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

import networkx as nx

from argus.models.context import RetrievedContext
from argus.models.diff import PullRequestDiff
from argus.models.review import (
    ArchitectureReview,
    CodeQualityReview,
    FinalReview,
    PerformanceReview,
    ReviewStrategy,
    RiskAssessment,
    SecurityReview,
    TestingReview,
)


class ReviewState(TypedDict, total=False):
    # Inputs
    repo_path: str
    base_ref: str
    head_ref: str

    # Repository Loader / Indexer outputs
    diff: PullRequestDiff
    file_contents: dict[str, str]
    import_graph: nx.DiGraph

    # Planner / Retrieval outputs
    strategy: ReviewStrategy
    retrieved_context: RetrievedContext

    # Reviewer outputs (each node owns exactly one key -> safe to run in parallel)
    security_review: SecurityReview
    performance_review: PerformanceReview
    architecture_review: ArchitectureReview
    quality_review: CodeQualityReview
    testing_review: TestingReview

    # Risk / context-expansion loop
    risk_assessment: RiskAssessment
    context_expansion_rounds: int

    # Final output
    final_review: FinalReview

    # Cross-cutting
    errors: Annotated[list[str], operator.add]


def initial_state(repo_path: str, base_ref: str, head_ref: str = "HEAD") -> ReviewState:
    return ReviewState(
        repo_path=repo_path,
        base_ref=base_ref,
        head_ref=head_ref,
        context_expansion_rounds=0,
        errors=[],
    )


# Re-exported for nodes that need to type a raw dict without the TypedDict machinery.
StateUpdate = dict[str, Any]
