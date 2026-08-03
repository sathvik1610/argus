from __future__ import annotations

from pathlib import Path

from argus.config import Settings
from argus.graph.workflow import build_review_graph
from argus.models.review import (
    ArchitectureReview,
    CodeQualityReview,
    FinalReview,
    PerformanceReview,
    Recommendation,
    ReviewStrategy,
    RiskAssessment,
    SecurityReview,
    Severity,
    TestingReview,
)
from tests.conftest import FakeEmbeddings
from tests.fakes import FakeStructuredChatModel


def _fake_reviews() -> dict:
    return {
        ReviewStrategy: ReviewStrategy(
            summary="s",
            estimated_review_depth="standard",
            focus_areas=["performance"],
            rationale="r",
        ),
        SecurityReview: SecurityReview(
            summary="clean", overall_severity=Severity.LOW, confidence=0.9
        ),
        PerformanceReview: PerformanceReview(summary="nested loop found", confidence=0.8),
        ArchitectureReview: ArchitectureReview(
            summary="fine", coupling_notes="low", cohesion_notes="ok", confidence=0.8
        ),
        CodeQualityReview: CodeQualityReview(
            summary="ok", maintainability_score=8.0, confidence=0.8
        ),
        TestingReview: TestingReview(summary="needs tests", confidence=0.7),
    }


def test_full_review_graph_produces_final_report(temp_git_repo: Path, settings: Settings) -> None:
    responses = _fake_reviews()
    responses[RiskAssessment] = RiskAssessment(
        overall_risk=Severity.LOW, risk_score=15.0, rationale="low risk", needs_more_context=False
    )
    responses[FinalReview] = FinalReview(
        summary="looks good",
        recommendation=Recommendation.APPROVE,
        confidence_score=0.85,
        risk_assessment=responses[RiskAssessment],
        security=responses[SecurityReview],
        performance=responses[PerformanceReview],
        architecture=responses[ArchitectureReview],
        quality=responses[CodeQualityReview],
        testing=responses[TestingReview],
    )

    model = FakeStructuredChatModel(responses)
    graph = build_review_graph(settings, chat_model=model, embeddings=FakeEmbeddings())

    result = graph.invoke(
        {
            "repo_path": str(temp_git_repo),
            "base_ref": "HEAD~1",
            "head_ref": "HEAD",
            "context_expansion_rounds": 0,
            "errors": [],
        }
    )

    assert result["final_review"].recommendation == Recommendation.APPROVE
    assert result["risk_assessment"].overall_risk == Severity.LOW
    assert result["strategy"].estimated_review_depth == "standard"
    assert result["diff"].total_files_changed == 1
    assert result["retrieved_context"].touched_chunks


def test_context_expansion_loop_runs_when_risk_agent_requests_more(
    temp_git_repo: Path, settings: Settings
) -> None:
    responses = _fake_reviews()
    # First risk call asks for more context; the loop then re-runs the five
    # reviewers and risk a second time, which must return a second, distinct
    # RiskAssessment satisfied with what it has.
    responses[RiskAssessment] = [
        RiskAssessment(
            overall_risk=Severity.MEDIUM,
            risk_score=40.0,
            rationale="need more info",
            needs_more_context=True,
            follow_up_queries=["definition of helper"],
        ),
        RiskAssessment(
            overall_risk=Severity.LOW,
            risk_score=15.0,
            rationale="resolved",
            needs_more_context=False,
        ),
    ]
    responses[FinalReview] = FinalReview(
        summary="looks good after digging deeper",
        recommendation=Recommendation.APPROVE_WITH_COMMENTS,
        confidence_score=0.75,
        risk_assessment=responses[RiskAssessment][-1],
        security=responses[SecurityReview],
        performance=responses[PerformanceReview],
        architecture=responses[ArchitectureReview],
        quality=responses[CodeQualityReview],
        testing=responses[TestingReview],
    )
    # The reviewer schemas get invoked twice (fan-out ran twice) — register a
    # duplicate for each so the second pass doesn't raise "exhausted".
    for schema in (
        SecurityReview,
        PerformanceReview,
        ArchitectureReview,
        CodeQualityReview,
        TestingReview,
    ):
        responses[schema] = [responses[schema], responses[schema]]

    model = FakeStructuredChatModel(responses)
    graph = build_review_graph(settings, chat_model=model, embeddings=FakeEmbeddings())

    result = graph.invoke(
        {
            "repo_path": str(temp_git_repo),
            "base_ref": "HEAD~1",
            "head_ref": "HEAD",
            "context_expansion_rounds": 0,
            "errors": [],
        }
    )

    assert result["context_expansion_rounds"] == 1
    assert result["final_review"].recommendation == Recommendation.APPROVE_WITH_COMMENTS
