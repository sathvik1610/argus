from __future__ import annotations

from argus.config import Settings
from argus.graph.nodes import route_after_risk
from argus.models.review import RiskAssessment, Severity


def _state(needs_more_context: bool, rounds: int) -> dict:
    return {
        "risk_assessment": RiskAssessment(
            overall_risk=Severity.MEDIUM,
            risk_score=50.0,
            rationale="test",
            needs_more_context=needs_more_context,
        ),
        "context_expansion_rounds": rounds,
    }


def test_routes_to_consensus_when_no_more_context_needed() -> None:
    decide = route_after_risk(Settings(max_context_expansion_rounds=2))
    assert decide(_state(False, 0)) == "consensus"


def test_routes_to_retrieve_more_when_context_needed_and_under_cap() -> None:
    decide = route_after_risk(Settings(max_context_expansion_rounds=2))
    assert decide(_state(True, 0)) == "retrieve_more"
    assert decide(_state(True, 1)) == "retrieve_more"


def test_routes_to_consensus_once_expansion_cap_reached() -> None:
    decide = route_after_risk(Settings(max_context_expansion_rounds=2))
    assert decide(_state(True, 2)) == "consensus"
    assert decide(_state(True, 5)) == "consensus"
