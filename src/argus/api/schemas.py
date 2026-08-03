from __future__ import annotations

from pydantic import BaseModel, Field

from argus.models.review import FinalReview, ReviewStrategy, RiskAssessment


class ReviewRequest(BaseModel):
    repo_path: str = Field(description="Path to a local git repository accessible to the server")
    base_ref: str = Field(description="Base ref/branch/commit to diff against")
    head_ref: str = Field(default="HEAD", description="Head ref/branch/commit")


class ReviewResponse(BaseModel):
    final_review: FinalReview
    strategy: ReviewStrategy
    risk_assessment: RiskAssessment


class HealthResponse(BaseModel):
    status: str = "ok"


class GraphResponse(BaseModel):
    mermaid: str


class MetricsResponse(BaseModel):
    reviews_completed: int
    reviews_failed: int
