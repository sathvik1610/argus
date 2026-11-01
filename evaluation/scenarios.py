"""All evaluation scenarios, in one list."""

from __future__ import annotations

from evaluation.scenario import Scenario
from evaluation.scenarios_clean import CLEAN_SCENARIOS
from evaluation.scenarios_correctness import CORRECTNESS_SCENARIOS
from evaluation.scenarios_performance import PERFORMANCE_SCENARIOS
from evaluation.scenarios_security import SECURITY_SCENARIOS

ALL_SCENARIOS: list[Scenario] = [
    *SECURITY_SCENARIOS,
    *CORRECTNESS_SCENARIOS,
    *PERFORMANCE_SCENARIOS,
    *CLEAN_SCENARIOS,
]
