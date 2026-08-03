"""Risk estimation agent: synthesizes the five specialist reviews into a single
risk verdict, and decides whether the context-expansion loop should run again.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from argus.agents.base import StructuredAgent
from argus.models.review import (
    ArchitectureReview,
    CodeQualityReview,
    PerformanceReview,
    RiskAssessment,
    SecurityReview,
    TestingReview,
)
from argus.prompts.planning import RISK_SYSTEM_PROMPT


def build_risk_agent(chat_model: BaseChatModel) -> StructuredAgent[RiskAssessment]:
    return StructuredAgent("risk", chat_model, RiskAssessment, RISK_SYSTEM_PROMPT)


def run_risk_agent(
    agent: StructuredAgent[RiskAssessment],
    security: SecurityReview,
    performance: PerformanceReview,
    architecture: ArchitectureReview,
    quality: CodeQualityReview,
    testing: TestingReview,
) -> RiskAssessment:
    prompt = "\n\n".join(
        [
            f"## Security review\n{security.model_dump_json(indent=2)}",
            f"## Performance review\n{performance.model_dump_json(indent=2)}",
            f"## Architecture review\n{architecture.model_dump_json(indent=2)}",
            f"## Code quality review\n{quality.model_dump_json(indent=2)}",
            f"## Testing review\n{testing.model_dump_json(indent=2)}",
        ]
    )
    return agent.run(prompt)
