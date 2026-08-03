"""High-level entrypoint for running a review — shared by the CLI and the API
so neither has to know about graph construction or state initialization.
"""

from __future__ import annotations

from argus.config import Settings, get_settings
from argus.graph.state import ReviewState, initial_state
from argus.graph.workflow import build_review_graph


def run_review(
    repo_path: str,
    base_ref: str,
    head_ref: str = "HEAD",
    settings: Settings | None = None,
) -> ReviewState:
    """Run the full review graph and return the resulting state.

    The resulting state's ``final_review`` key holds the report; other keys
    (``risk_assessment``, individual reviewer outputs, ``strategy``) remain
    available for callers that want more than the merged report, e.g. a
    verbose CLI ``--format json`` dump.
    """
    resolved_settings = settings or get_settings()
    graph = build_review_graph(resolved_settings)
    state = initial_state(repo_path, base_ref, head_ref)
    result = graph.invoke(state)
    return result  # type: ignore[return-value]
