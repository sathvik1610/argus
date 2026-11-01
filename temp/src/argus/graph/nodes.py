"""Node functions for the review graph.

Each ``make_*`` function is a factory that closes over its dependencies
(agents, settings) and returns a plain ``state -> partial state update``
callable — the shape LangGraph expects. Keeping construction (which needs
a chat model, settings, etc.) separate from invocation (which only needs
state) is what lets :mod:`argus.graph.workflow` wire the graph without every
node reaching back into global configuration.
"""

from __future__ import annotations

from typing import Any

from argus.agents.base import StructuredAgent
from argus.agents.consensus import run_consensus_agent
from argus.agents.planner import run_planner
from argus.agents.reviewers import ReviewerSpec, run_reviewer
from argus.agents.risk import run_risk_agent
from argus.config import Settings
from argus.graph.state import ReviewState
from argus.models.review import FinalReview, ReviewStrategy, RiskAssessment
from argus.retrieval.indexer import index_repository
from argus.retrieval.retriever import ContextRetriever
from argus.retrieval.vector_store import RepositoryIndex
from argus.services.logging import get_logger
from argus.tools.repository import RepositoryLoader

logger = get_logger(__name__)

_DEPTH_MULTIPLIER = {"quick": 0.5, "standard": 1.0, "deep": 1.75}


def make_load_repository_node() -> Any:
    def load_repository(state: ReviewState) -> dict[str, Any]:
        loader = RepositoryLoader(state["repo_path"])
        diff = loader.diff(state["base_ref"], state.get("head_ref", "HEAD"))
        logger.info("diff_loaded", files=diff.total_files_changed, additions=diff.total_additions)
        return {"diff": diff}

    return load_repository


def make_index_repository_node(settings: Settings, embeddings: Any | None = None) -> Any:
    def index_repository_node(state: ReviewState) -> dict[str, Any]:
        loader = RepositoryLoader(state["repo_path"])
        index = RepositoryIndex(settings, state["repo_path"], embeddings=embeddings)
        result = index_repository(loader, index, ref=state.get("head_ref", "HEAD"))
        return {
            "file_contents": result.file_contents,
            "import_graph": result.import_graph,
            "vector_index": index,
        }

    return index_repository_node


def make_planner_node(agent: StructuredAgent[ReviewStrategy]) -> Any:
    def plan(state: ReviewState) -> dict[str, Any]:
        strategy = run_planner(agent, state["diff"])
        logger.info(
            "review_planned", depth=strategy.estimated_review_depth, focus=strategy.focus_areas
        )
        return {"strategy": strategy}

    return plan


def make_retrieve_node(settings: Settings) -> Any:
    def retrieve(state: ReviewState) -> dict[str, Any]:
        depth_settings = _settings_for_depth(settings, state.get("strategy"))
        retriever = ContextRetriever(
            state["vector_index"], state["import_graph"], state["file_contents"], depth_settings
        )
        context = retriever.retrieve_for_diff(state["diff"])
        logger.info(
            "context_retrieved",
            ranked_files=len(context.ranked_files),
            touched_chunks=len(context.touched_chunks),
            related_chunks=len(context.related_chunks),
        )
        return {"retrieved_context": context}

    return retrieve


def make_retrieve_more_node(settings: Settings) -> Any:
    def retrieve_more(state: ReviewState) -> dict[str, Any]:
        retriever = ContextRetriever(
            state["vector_index"], state["import_graph"], state["file_contents"], settings
        )
        context = state["retrieved_context"]
        for query in state["risk_assessment"].follow_up_queries:
            context = retriever.expand(context, query)
        rounds = state.get("context_expansion_rounds", 0) + 1
        logger.info(
            "context_expanded", round=rounds, queries=state["risk_assessment"].follow_up_queries
        )
        return {"retrieved_context": context, "context_expansion_rounds": rounds}

    return retrieve_more


def make_reviewer_node(spec: ReviewerSpec, agent: StructuredAgent[Any]) -> Any:
    def review(state: ReviewState) -> dict[str, Any]:
        result = run_reviewer(
            agent, state["diff"], state["retrieved_context"], state.get("strategy")
        )
        return {spec.state_key: result}

    return review


def make_risk_node(agent: StructuredAgent[RiskAssessment]) -> Any:
    def risk(state: ReviewState) -> dict[str, Any]:
        assessment = run_risk_agent(
            agent,
            state["security_review"],
            state["performance_review"],
            state["architecture_review"],
            state["quality_review"],
            state["testing_review"],
        )
        logger.info(
            "risk_assessed",
            risk=assessment.overall_risk,
            score=assessment.risk_score,
            needs_more_context=assessment.needs_more_context,
        )
        return {"risk_assessment": assessment}

    return risk


def make_consensus_node(agent: StructuredAgent[FinalReview]) -> Any:
    def consensus(state: ReviewState) -> dict[str, Any]:
        final = run_consensus_agent(
            agent,
            state["security_review"],
            state["performance_review"],
            state["architecture_review"],
            state["quality_review"],
            state["testing_review"],
            state["risk_assessment"],
        )
        logger.info("review_finalized", recommendation=final.recommendation)
        return {"final_review": final}

    return consensus


def route_after_risk(settings: Settings) -> Any:
    def decide(state: ReviewState) -> str:
        assessment = state["risk_assessment"]
        rounds = state.get("context_expansion_rounds", 0)
        if assessment.needs_more_context and rounds < settings.max_context_expansion_rounds:
            return "retrieve_more"
        return "consensus"

    return decide


def _settings_for_depth(settings: Settings, strategy: ReviewStrategy | None) -> Settings:
    if strategy is None:
        return settings
    multiplier = _DEPTH_MULTIPLIER.get(strategy.estimated_review_depth, 1.0)
    return settings.model_copy(
        update={
            "retrieval_top_k": max(1, round(settings.retrieval_top_k * multiplier)),
            "max_files_per_review": max(1, round(settings.max_files_per_review * multiplier)),
        }
    )
