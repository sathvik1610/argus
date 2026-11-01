"""Pydantic models. The LLM's answers are forced into these shapes."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Category(StrEnum):
    SECURITY = "security"
    CORRECTNESS = "correctness"
    PERFORMANCE = "performance"


class Finding(BaseModel):
    file: str = Field(description="Path of the file, exactly as shown in the diff")
    line: int | None = Field(
        default=None, description="Line number in the NEW version of the file, if identifiable"
    )
    category: Category
    severity: Severity
    description: str = Field(description="What is wrong and why it matters")
    suggested_fix: str = Field(description="A concrete fix")


class AgentOutput(BaseModel):
    """What one reviewer agent returns."""

    findings: list[Finding] = Field(default_factory=list)


class Snippet(BaseModel):
    """A piece of repository code retrieved by RAG. Keeps file and line info."""

    file: str
    start_line: int
    end_line: int
    name: str | None = None
    code: str


class Report(BaseModel):
    """The final merged review."""

    summary: str
    findings: list[Finding]
    severity_counts: dict[str, int]
    files_with_findings: list[str]
    retrieved_context: list[Snippet]
    rag_enabled: bool
    risk_score: int = 0  # 0-100, see merge.risk_score()
    risk_level: str = "none"  # none, low, medium, high or critical
    tokens_used: int = 0
