"""Consensus agent: merges all specialist reviews and the risk assessment into
the final, human-facing report.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from argus.agents.base import StructuredAgent
from argus.models.review import (
    ArchitectureReview,
    CodeQualityReview,
    FinalReview,
    PerformanceReview,
    RiskAssessment,
    SecurityReview,
    TestingReview,
)
from argus.prompts.consensus import CONSENSUS_SYSTEM_PROMPT


def build_consensus_agent(chat_model: BaseChatModel) -> StructuredAgent[FinalReview]:
    return StructuredAgent("consensus", chat_model, FinalReview, CONSENSUS_SYSTEM_PROMPT)


def run_consensus_agent(
    agent: StructuredAgent[FinalReview],
    security: SecurityReview,
    performance: PerformanceReview,
    architecture: ArchitectureReview,
    quality: CodeQualityReview,
    testing: TestingReview,
    risk: RiskAssessment,
) -> FinalReview:
    prompt = "\n\n".join(
        [
            f"## Security review\n{security.model_dump_json(indent=2)}",
            f"## Performance review\n{performance.model_dump_json(indent=2)}",
            f"## Architecture review\n{architecture.model_dump_json(indent=2)}",
            f"## Code quality review\n{quality.model_dump_json(indent=2)}",
            f"## Testing review\n{testing.model_dump_json(indent=2)}",
            f"## Risk assessment\n{risk.model_dump_json(indent=2)}",
        ]
    )
    return agent.run(prompt)
