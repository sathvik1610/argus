"""Structured outputs produced by each review agent.

Every agent returns one of these Pydantic models via LangChain structured
output (``.with_structured_output``) rather than free text — that's what lets
the Consensus stage merge five independent opinions programmatically instead
of asking yet another LLM call to "please summarize these paragraphs".
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Recommendation(StrEnum):
    APPROVE = "approve"
    APPROVE_WITH_COMMENTS = "approve_with_comments"
    REQUEST_CHANGES = "request_changes"
    BLOCK = "block"


class SecurityFinding(BaseModel):
    title: str
    description: str
    severity: Severity
    file_path: str
    line_start: int | None = None
    line_end: int | None = None
    cwe_id: str | None = Field(default=None, description="e.g. CWE-89 for SQL injection")
    suggested_fix: str


class SecurityReview(BaseModel):
    summary: str
    vulnerabilities: list[SecurityFinding] = Field(default_factory=list)
    overall_severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)


class PerformanceIssue(BaseModel):
    title: str
    description: str
    file_path: str
    complexity_estimate: str | None = Field(default=None, description="e.g. O(n^2)")
    memory_concern: str | None = None
    suggested_fix: str


class PerformanceReview(BaseModel):
    summary: str
    bottlenecks: list[PerformanceIssue] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class ArchitectureConcern(BaseModel):
    title: str
    description: str
    file_path: str
    principle: str | None = Field(default=None, description="e.g. SRP, OCP, DIP")
    severity: Severity


class ArchitectureReview(BaseModel):
    summary: str
    coupling_notes: str
    cohesion_notes: str
    solid_violations: list[ArchitectureConcern] = Field(default_factory=list)
    layering_concerns: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class QualityIssue(BaseModel):
    title: str
    description: str
    file_path: str
    category: str = Field(description="naming | duplication | complexity | style | documentation")
    severity: Severity


class CodeQualityReview(BaseModel):
    summary: str
    issues: list[QualityIssue] = Field(default_factory=list)
    maintainability_score: float = Field(ge=0.0, le=10.0)
    confidence: float = Field(ge=0.0, le=1.0)


class MissingTest(BaseModel):
    file_path: str
    function_name: str | None = None
    reason: str
    risk_if_untested: str


class TestingReview(BaseModel):
    summary: str
    missing_tests: list[MissingTest] = Field(default_factory=list)
    integration_risks: list[str] = Field(default_factory=list)
    edge_cases: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class RiskAssessment(BaseModel):
    overall_risk: Severity
    risk_score: float = Field(ge=0.0, le=100.0)
    rationale: str
    files_requiring_manual_review: list[str] = Field(default_factory=list)
    needs_more_context: bool = False
    follow_up_queries: list[str] = Field(default_factory=list)


class ReviewStrategy(BaseModel):
    """The Planner agent's output: how deep/broad this review should go."""

    summary: str
    estimated_review_depth: str = Field(description="quick | standard | deep")
    focus_areas: list[str] = Field(
        default_factory=list, description="e.g. ['security', 'performance']"
    )
    rationale: str


class FinalReview(BaseModel):
    """The Consensus agent's merged, human-facing report."""

    summary: str
    recommendation: Recommendation
    confidence_score: float = Field(ge=0.0, le=1.0)
    risk_assessment: RiskAssessment
    security: SecurityReview
    performance: PerformanceReview
    architecture: ArchitectureReview
    quality: CodeQualityReview
    testing: TestingReview
    files_requiring_manual_review: list[str] = Field(default_factory=list)
    suggested_improvements: list[str] = Field(default_factory=list)
