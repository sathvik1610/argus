from __future__ import annotations

from argus.models.review import (
    ArchitectureReview,
    CodeQualityReview,
    FinalReview,
    PerformanceIssue,
    PerformanceReview,
    Recommendation,
    RiskAssessment,
    SecurityFinding,
    SecurityReview,
    Severity,
    TestingReview,
)
from argus.services.report import render_markdown


def _sample_review() -> FinalReview:
    risk = RiskAssessment(
        overall_risk=Severity.HIGH,
        risk_score=72.0,
        rationale="A SQL injection vector was introduced in the new query builder.",
        files_requiring_manual_review=["app/db/query.py"],
    )
    security = SecurityReview(
        summary="One high-severity injection vulnerability found.",
        vulnerabilities=[
            SecurityFinding(
                title="SQL injection via unescaped user input",
                description="User-controlled `name` is interpolated directly into the query.",
                severity=Severity.HIGH,
                file_path="app/db/query.py",
                line_start=42,
                cwe_id="CWE-89",
                suggested_fix="Use a parameterized query instead of string formatting.",
            )
        ],
        overall_severity=Severity.HIGH,
        confidence=0.9,
    )
    performance = PerformanceReview(
        summary="No significant bottlenecks.",
        bottlenecks=[
            PerformanceIssue(
                title="Nested loop over request items",
                description="O(n^2) scan on every request.",
                file_path="app/db/query.py",
                complexity_estimate="O(n^2)",
                suggested_fix="Use a set for membership checks.",
            )
        ],
        confidence=0.8,
    )
    architecture = ArchitectureReview(
        summary="Coupling is acceptable.", coupling_notes="low", cohesion_notes="ok", confidence=0.8
    )
    quality = CodeQualityReview(summary="Fine.", maintainability_score=7.5, confidence=0.8)
    testing = TestingReview(summary="Missing coverage for the new query path.", confidence=0.6)

    return FinalReview(
        summary="This PR introduces a SQL injection vulnerability that must be fixed before merge.",
        recommendation=Recommendation.BLOCK,
        confidence_score=0.85,
        risk_assessment=risk,
        security=security,
        performance=performance,
        architecture=architecture,
        quality=quality,
        testing=testing,
        files_requiring_manual_review=["app/db/query.py"],
        suggested_improvements=["Parameterize the query in app/db/query.py"],
    )


def test_render_markdown_includes_recommendation_and_key_findings() -> None:
    markdown = render_markdown(_sample_review())

    assert "`block`" in markdown
    assert "SQL injection via unescaped user input" in markdown
    assert "CWE-89" in markdown
    assert "app/db/query.py" in markdown
    assert "O(n^2)" in markdown
    assert "Parameterize the query in app/db/query.py" in markdown


def test_render_markdown_omits_empty_sections_gracefully() -> None:
    review = _sample_review()
    review = review.model_copy(
        update={
            "security": SecurityReview(summary="Clean.", overall_severity=Severity.LOW, confidence=0.95),
            "suggested_improvements": [],
        }
    )
    markdown = render_markdown(review)
    assert "## Security" in markdown
    assert "Clean." in markdown
