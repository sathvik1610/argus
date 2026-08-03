"""Assembles the Argus review graph.

Shape (see Architecture.md for the full rationale):

    START -> load_repository -> index_repository -> plan -> retrieve
          -> {security, performance, architecture, quality, testing}  (parallel fan-out)
          -> risk_estimation                                          (fan-in)
          -> [needs more context?] -> retrieve_more -> back to the reviewer fan-out
                                    -> consensus -> END

The five reviewers run as independent parallel branches rather than a
sequential chain: they don't depend on each other's output, LangGraph's
fan-out/fan-in is exactly the primitive for that, and it cuts wall-clock
latency roughly 5x relative to running them one after another. The
context-expansion loop is capped by ``settings.max_context_expansion_rounds``
so an LLM that is chronically unsatisfied with its context cannot loop
forever.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from argus.agents.consensus import build_consensus_agent
from argus.agents.planner import build_planner
from argus.agents.reviewers import REVIEWER_SPECS, build_reviewer
from argus.agents.risk import build_risk_agent
from argus.config import Settings
from argus.graph.nodes import (
    make_consensus_node,
    make_index_repository_node,
    make_load_repository_node,
    make_planner_node,
    make_retrieve_more_node,
    make_retrieve_node,
    make_reviewer_node,
    make_risk_node,
    route_after_risk,
)
from argus.graph.state import ReviewState
from argus.services.llm import build_chat_model

REVIEWER_NODE_NAMES = tuple(spec.key for spec in REVIEWER_SPECS)


def build_review_graph(
    settings: Settings, chat_model: object | None = None, embeddings: object | None = None
) -> CompiledStateGraph:
    """Construct and compile the review graph for the given configuration.

    ``chat_model``/``embeddings`` overrides exist so tests (and anything else
    that wants determinism) can inject fakes instead of hitting a real
    provider; production callers should leave them as None and let the
    factories in :mod:`argus.services.llm` build them from ``settings``.
    """
    model = chat_model or build_chat_model(settings)

    graph = StateGraph(ReviewState)

    graph.add_node("load_repository", make_load_repository_node())
    graph.add_node("index_repository", make_index_repository_node(settings, embeddings))
    graph.add_node("plan", make_planner_node(build_planner(model)))
    graph.add_node("retrieve", make_retrieve_node(settings))

    for spec in REVIEWER_SPECS:
        agent = build_reviewer(spec, model)
        graph.add_node(spec.key, make_reviewer_node(spec, agent))

    graph.add_node("risk_estimation", make_risk_node(build_risk_agent(model)))
    graph.add_node("retrieve_more", make_retrieve_more_node(settings))
    graph.add_node("consensus", make_consensus_node(build_consensus_agent(model)))

    graph.add_edge(START, "load_repository")
    graph.add_edge("load_repository", "index_repository")
    graph.add_edge("index_repository", "plan")
    graph.add_edge("plan", "retrieve")

    for name in REVIEWER_NODE_NAMES:
        graph.add_edge("retrieve", name)
        graph.add_edge(name, "risk_estimation")

    graph.add_conditional_edges(
        "risk_estimation",
        route_after_risk(settings),
        {"retrieve_more": "retrieve_more", "consensus": "consensus"},
    )

    for name in REVIEWER_NODE_NAMES:
        graph.add_edge("retrieve_more", name)

    graph.add_edge("consensus", END)

    return graph.compile()
